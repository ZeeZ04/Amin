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

# A token with both a letter and a digit (FR-550, PHY-205, V16, 5G), or a
# capitalised word followed by a number (Freedom 300, Unit 1024).
_ID = re.compile(r"\b(?=[A-Za-z0-9-]*\d)(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b")
_NAME_NUM = re.compile(r"\b([A-Z][a-z]+)\s+(\d{2,})\b")


def question_identifiers(question: str) -> set[str]:
    out = {m.group(0).lower() for m in _ID.finditer(question)}
    out |= {f"{a} {b}".lower() for a, b in _NAME_NUM.findall(question)}
    return out


_ML = re.compile(r"[ഀ-ൿ]")
_AR = re.compile(r"[؀-ۿ]")


def script_lang(text: str) -> str:
    """ml, ar or en, by which script the text is mostly written in."""
    ml, ar = len(_ML.findall(text)), len(_AR.findall(text))
    return "ml" if ml and ml >= ar else "ar" if ar else "en"


@dataclass(frozen=True)
class Route:
    name: str
    message: str
    refer_to: str
    describe: str = ""
    threshold: float = 0.6
    localized: tuple[tuple[str, str], ...] = ()

    def reply(self, question: str) -> str:
        """The referral, in the language the question was written in."""
        local = dict(self.localized).get(script_lang(question))
        return " ".join(local.split()) if local else f"{self.message.strip()} Please ask {self.refer_to}."


@dataclass(frozen=True)
class Decision:
    allowed: bool
    route: Route | None = None
    by: str = ""  # "pattern" or "router": which one decided


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
                        describe=entry.get("describe", ""),
                        threshold=float(entry.get("threshold", 0.6)),
                        localized=tuple(sorted((entry.get("localized") or {}).items())),
                    ),
                )
            )

    # -- scope ---------------------------------------------------------------

    @property
    def routes(self) -> list[Route]:
        return [r for _, r in self._routes]

    def check(self, question: str, router=None) -> Decision:
        """Patterns first; then, if given, the router (amin/classify.py), which
        reads every language. The router can only add a route, never lift one."""
        for pattern, route in self._routes:
            if pattern.search(question):
                return Decision(allowed=False, route=route, by="pattern")
        if router is not None:
            choice = router.route(question)
            route = next((r for r in self.routes if r.name == choice.label), None)
            if route is not None:
                return Decision(allowed=False, route=route, by="router")
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

    def missing_identifiers(self, question: str, retrieved: list[Retrieved]) -> list[str]:
        """Identifiers the question names that no retrieved chunk contains.

        The near-miss hole (E18): "warranty on the FR-550" retrieves the FR-440
        manual at high coverage, because every distinctive word matches except
        the one that matters. Coverage cannot see that; an exact check on the
        model number can. Non-empty means the corpus is about a sibling of the
        thing asked, so answering would cite the wrong product correctly.
        """
        wanted = question_identifiers(question)
        if not wanted:
            return []
        seen = " ".join(
            f"{r.chunk.heading} {r.chunk.text}".lower() for r in retrieved
        )
        seen = re.sub(r"\s+", " ", seen)
        return sorted(w for w in wanted if w not in seen)

    def evidence_note(self, retrieved: list[Retrieved]) -> str:
        if not retrieved:
            return "nothing in the corpus matched the question"
        best = max(r.coverage for r in retrieved)
        return (
            f"best chunk covered {best:.0%} of the question's distinctive terms, "
            f"below the floor of {settings.evidence_floor:.0%}"
        )
