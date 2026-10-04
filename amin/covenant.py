"""The covenant: rules Amin is held to, loaded from policy.yaml and enforced in code.

The name means trustworthy, so the trust properties are a specification with a
test suite rather than a line in the README. Two jobs here:

  - route questions that must not be answered from a document corpus at all
    (medical, legal, financial decisions) to a quote-and-refer response
  - decide whether the retrieved evidence is strong enough to answer

Both are pure functions over config, so tests/test_covenant.py can pin them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import settings
from .schema import Retrieved


@dataclass(frozen=True)
class Route:
    name: str
    message: str
    refer_to: str


@dataclass(frozen=True)
class Decision:
    allowed: bool
    route: Route | None = None


class Covenant:
    def __init__(self, policy_path: Path | None = None):
        path = Path(policy_path or settings.policy_path)
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self.version: str = str(raw.get("version", "0"))
        self.refusal_template: str = raw.get(
            "refusal_template", "I don't have a source for that, so I won't guess."
        )
        self._routes: list[tuple[re.Pattern, Route]] = []
        for entry in raw.get("routes", []):
            patterns = entry.get("patterns", [])
            if not patterns:
                continue
            compiled = re.compile("|".join(patterns), re.I | re.U)
            self._routes.append(
                (
                    compiled,
                    Route(
                        name=entry["name"],
                        message=entry["message"],
                        refer_to=entry.get("refer_to", ""),
                    ),
                )
            )

    # -- scope ---------------------------------------------------------------

    def check(self, question: str) -> Decision:
        for pattern, route in self._routes:
            if pattern.search(question):
                return Decision(allowed=False, route=route)
        return Decision(allowed=True)

    # -- evidence ------------------------------------------------------------

    def has_evidence(self, retrieved: list[Retrieved]) -> bool:
        """Is there a chunk that actually covers what was asked?

        Reads `coverage`, not `score`: the fused retrieval score is rank-derived
        and almost constant at the top of the list, so gating on it lets a
        question the corpus knows nothing about through. Coverage is absolute.
        """
        if not retrieved:
            return False
        return max(r.coverage for r in retrieved) >= settings.evidence_floor

    def evidence_note(self, retrieved: list[Retrieved]) -> str:
        if not retrieved:
            return "nothing in the corpus matched the question"
        best = max(r.coverage for r in retrieved)
        return (
            f"best chunk covered {best:.0%} of the question's distinctive terms, "
            f"below the floor of {settings.evidence_floor:.0%}"
        )
