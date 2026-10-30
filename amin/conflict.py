"""Structural conflict detection.

The problem this solves: when two approved sources disagree, the pipeline as
built would retrieve both, hand both to the model, and let the model pick one.
It would then cite that one and look completely confident. Silently resolving a
disagreement is the most dangerous thing a "trustworthy" system can do, because
the citation makes the arbitrary choice look sourced.

Relying on the model to notice and say "CONFLICT" is not a fix: it is unverifiable
and fails silently. So conflict detection happens *before* generation, in code,
on the retrieved passages.

The signal is numeric disagreement in answer position. Two chunks conflict when:

  1. both substantially cover the question (so both are really about it),
  2. they come from different documents,
  3. they are topically similar to each other (so we are not comparing a rent
     clause with a tariff table that merely share a word), and
  4. the numbers sitting next to the question's own terms differ.

Condition 4 is the discriminating one. "What is the coursework weighting?" puts
`30` next to `coursework` in the 2026 handbook and `40` in the 2025 one. "What
is the pass mark?" puts `40` next to `pass mark` in both, so it is not a
conflict - the documents genuinely agree there, and flagging it would be a false
alarm that trains the reader to ignore the warning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import settings
from .providers import content_tokens
from .schema import Retrieved

# One token = a whole number (thousands separators and decimals included) or a
# word. Splitting on the comma first turned "AED 3,900" into "3" and "900" and
# "AED 1,000" into "1" and "000" -> "0", so every monetary figure in the corpus
# was compared as nonsense and no conflict could ever be found.
NUMBER = re.compile(r"\d[\d,.]*\d|\d")
TOKEN = re.compile(r"\d[\d,.]*\d|\d|[A-Za-z؀-ۿഀ-ൿ]+")

# Numbers that identify a provision rather than answer a question. "Clause 11.1"
# is not a competing value for "what is the deposit".
REFERENCE_WORDS = frozenset(
    {"clause", "section", "article", "paragraph", "item", "no", "number", "unit", "phy", "part"}
)


@dataclass(frozen=True)
class Position:
    """One source's answer-position values for a question."""

    doc_id: str
    heading: str
    chunk_id: str
    values: frozenset[str]
    superseded: bool
    text: str
    subject: str = ""

    def label(self) -> str:
        return f"{self.doc_id}{' §' + self.heading if self.heading else ''}"


@dataclass(frozen=True)
class Conflict:
    question: str
    positions: list[Position]

    @property
    def current(self) -> list[Position]:
        return [p for p in self.positions if not p.superseded]

    @property
    def superseded(self) -> list[Position]:
        return [p for p in self.positions if p.superseded]

    @property
    def is_version_skew(self) -> bool:
        """A current source disagreeing only with a superseded one.

        Not a real conflict for the reader: the current document wins and the
        old one is worth a footnote, not a refusal to answer.
        """
        return len(self.current) == 1 and len(self.superseded) >= 1

    def describe(self) -> list[str]:
        return [f"{p.label()} says {', '.join(sorted(p.values))}" for p in self.positions]


def _normalise_number(raw: str) -> str:
    """3,900 -> 3900; 11.1 -> 11.1; 0.50 -> 0.50.

    Thousands separators go, the decimal point stays: 11.1 (a clause) must not
    collapse onto 11, and 0.50 (a per-MB rate) must not become 050.
    """
    cleaned = raw.replace(",", "").strip(".")
    if "." in cleaned:
        whole, _, frac = cleaned.partition(".")
        whole = whole.lstrip("0") or "0"
        return f"{whole}.{frac}"
    return cleaned.lstrip("0") or "0"


SENTENCE = re.compile(r"(?<=[.!?؟۔])\s+|\n+")


def answer_position_values(question: str, text: str) -> frozenset[str]:
    """Numbers appearing within `window` words of one of the question's own terms.

    Restricting to answer position is what keeps this from firing on every
    document that happens to contain different numbers. A tariff table and a
    tenancy clause both contain numbers; only the ones sitting beside the words
    the question actually used are candidate answers to it.

    Scope is the sentence, not a fixed word window. A five-word window missed
    "The refundable security deposit for this unit is AED 4,100" because the
    figure sits six words after "deposit"; widening the window arbitrarily just
    moves the failure. A sentence is the unit in which a document actually makes
    a claim, so it is the right scope.

    Numbers that appear in the question are excluded: "PHY-104" puts `104` in
    every passage about that module, and counting it as a shared value made two
    flatly contradictory handbooks look like they agreed.
    """
    terms = content_tokens(question)
    if not terms:
        return frozenset()
    asked = {_normalise_number(n) for n in NUMBER.findall(question)}

    found: set[str] = set()
    for sentence in SENTENCE.split(text):
        words = TOKEN.findall(sentence)
        lowered = [w.lower() for w in words]
        if not any(w in terms for w in lowered):
            continue
        for i, word in enumerate(words):
            if not NUMBER.fullmatch(word):
                continue
            if i > 0 and lowered[i - 1] in REFERENCE_WORDS:
                continue  # "Clause 11.1" identifies a provision, not an answer
            value = _normalise_number(word)
            if value not in asked:
                found.add(value)
    return frozenset(found)


def _topical_overlap(a: str, b: str) -> float:
    ta, tb = content_tokens(a), content_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def detect(
    question: str,
    retrieved: list[Retrieved],
    coverage_floor: float | None = None,
    relative_floor: float | None = None,
    topical_floor: float = 0.2,
    related=None,
    one_work=None,
) -> Conflict | None:
    """Find a genuine disagreement among the retrieved passages, or None.

    Candidates are chunks whose coverage is close to the *best* coverage seen,
    not above a fixed threshold. An absolute floor silently drops the second
    position whenever the question contains terms that appear in neither source
    - "in the 2026/27 handbook" pushed both handbook chunks below 0.6 and the
    contradiction went undetected. What matters is that the two passages are
    equally good answers to the question, which is a relative property.

    `one_work(subject)` says a subject names a reference work, such as a
    knowledge pack's textbook. The conflict warning is for a person's own
    records disagreeing (two leases, two handbooks). Textbook pages discuss
    different quantities on different pages, so two of them, from one book or
    two, are never flagged against each other; a pack passage against one of
    the person's own documents still is.

    `related(doc_a, doc_b)` decides whether two documents are about the same
    thing, and should be `Store.are_related`. Without it this falls back to
    chunk-level vocabulary overlap, which was measured and found unable to tell
    a real conflict (tenancy contract vs agency sheet, 0.167) from a false one
    (tenancy contract vs electricity tariff, 0.172) - the false pair scored
    higher. Pass `related` in production; the fallback exists only so this
    function stays usable on its own.
    """
    if not retrieved:
        return None
    best = max(r.coverage for r in retrieved)
    if best <= 0:
        return None
    if coverage_floor is None:
        coverage_floor = settings.conflict_min_coverage
    if relative_floor is None:
        relative_floor = settings.conflict_relative_floor
    floor = max(coverage_floor, best * relative_floor)
    candidates = [r for r in retrieved if r.coverage >= floor]
    if len(candidates) < 2:
        return None

    positions: list[Position] = []
    seen_docs: set[str] = set()
    for r in candidates:
        if r.chunk.doc_id in seen_docs:
            continue  # one position per document: the best-covering chunk
        values = answer_position_values(question, f"{r.chunk.heading} {r.chunk.text}")
        if not values:
            continue
        seen_docs.add(r.chunk.doc_id)
        positions.append(
            Position(
                doc_id=r.chunk.doc_id,
                heading=r.chunk.heading,
                chunk_id=r.chunk_id,
                values=values,
                superseded=bool(r.chunk.superseded),
                text=r.chunk.text,
                subject=r.chunk.subject,
            )
        )

    if len(positions) < 2:
        return None

    # Compare every pair; a single genuine disagreement is enough.
    conflicting: list[Position] = []
    for i, a in enumerate(positions):
        for b in positions[i + 1 :]:
            # A contradiction needs disagreement in BOTH directions. If A says
            # {30, 70} and B says {30}, B is simply less complete - that is not
            # a conflict, and flagging it would train the reader to ignore the
            # warning. If A says {30, 70} and B says {40}, each asserts a value
            # the other denies, and that is.
            if not (a.values - b.values) or not (b.values - a.values):
                continue
            if one_work is not None and one_work(a.subject) and one_work(b.subject):
                continue
            if related is not None:
                if not related(a.doc_id, b.doc_id):
                    continue
            elif _topical_overlap(a.text, b.text) < topical_floor:
                continue
            for p in (a, b):
                if p not in conflicting:
                    conflicting.append(p)

    if len(conflicting) < 2:
        return None
    return Conflict(question=question, positions=conflicting)
