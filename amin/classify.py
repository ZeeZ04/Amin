"""Single-pass classification: Jev's idea, run on Amin's own model.

Jev (Typesafe AI) picks from a list of options in one forward pass and
returns a probability for each, instead of generating text. Jev itself is a
hosted API, which would send every question off the device (ADR-014), so the
same trick runs here on the local model: the options become letters, the
model emits one token, and the next-token distribution over those letters is
the answer with its probabilities. It costs one prefill and one token.

Routing is the first use: medical, legal, financial and crisis questions in
any language. The keyword patterns in policy.yaml are English and Arabic only,
and the crisis one is English only, so before this a Malayalam message about
suicide got an ordinary answer.

A failed call returns no decision, never a guess, and the patterns still
apply. The router only adds routes; it never overrides a pattern match.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import httpx

from .config import settings

_LETTER = re.compile(r"^\s*([A-Z])\b")


@dataclass(frozen=True)
class Choice:
    label: str | None  # None: no option cleared its threshold
    probs: dict[str, float]  # option name -> probability; "none" included


def _system(options: list[tuple[str, str]]) -> str:
    lines = [f"{chr(65 + i)}: {desc}" for i, (_, desc) in enumerate(options)]
    return (
        "Classify the user's message. It may be in any language. "
        "Reply with one letter only.\n" + "\n".join(lines)
    )


class Classifier:
    """Scores a fixed list of options against one input, in one call."""

    def __init__(self, host: str | None = None, timeout: float = 4.0):
        self.host = (host or settings.mlx_host).rstrip("/")
        self.timeout = timeout

    def scores(self, text: str, options: list[tuple[str, str]]) -> dict[str, float] | None:
        """{option name: probability} renormalised over the options, or None on failure."""
        try:
            r = httpx.post(
                f"{self.host}/v1/chat/completions",
                timeout=self.timeout,
                json={
                    "model": "default_model",
                    "max_tokens": 1,
                    "temperature": 0,
                    "logprobs": True,
                    "top_logprobs": max(10, len(options) + 4),
                    "messages": [
                        {"role": "system", "content": _system(options)},
                        {"role": "user", "content": text},
                    ],
                },
            )
            r.raise_for_status()
            top = r.json()["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return None
        mass = {name: 0.0 for name, _ in options}
        for t in top:
            m = _LETTER.match(t.get("token", ""))
            i = ord(m.group(1)) - 65 if m else -1
            if 0 <= i < len(options):
                mass[options[i][0]] += math.exp(t["logprob"])
        total = sum(mass.values())
        if total <= 0:
            return None
        return {k: v / total for k, v in mass.items()}


class Router:
    """Routes a question to a covenant route, or to none."""

    def __init__(self, routes: list[tuple[str, str, float]], classifier: Classifier | None = None):
        # (name, description, threshold), in policy order
        self.routes = routes
        self.options = [(n, d) for n, d, _ in routes] + [("none", "none of these: an ordinary question")]
        self.thresholds = {n: t for n, _, t in routes}
        self.classifier = classifier or Classifier()

    def route(self, question: str) -> Choice:
        probs = self.classifier.scores(question, self.options)
        if probs is None:
            return Choice(None, {})
        # Most cautious first: the lowest threshold (self_harm) wins a tie.
        for name in sorted(self.thresholds, key=self.thresholds.get):
            if probs.get(name, 0.0) >= self.thresholds[name]:
                return Choice(name, probs)
        return Choice(None, probs)
