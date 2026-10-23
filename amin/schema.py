"""Typed objects that move through the Amin pipeline.

Everything the user eventually sees is built from these. The important design
decision lives in `Claim`: an answer is not a blob of text, it is a list of
claims each of which either carries a verified citation or is explicitly
marked as unverified model reasoning.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Tier(int, Enum):
    """Source quality tier. Lower is better. Used for ranking and for display."""

    PRIMARY = 1  # official/authoritative: the actual contract, manual, statute, handbook
    REFERENCE = 2  # established reference works
    SECONDARY = 3  # reputable secondary reporting
    UNVERIFIED = 4  # ingested but not vouched for

    @property
    def label(self) -> str:
        return {1: "primary", 2: "reference", 3: "secondary", 4: "unverified"}[self.value]


class Document(BaseModel):
    doc_id: str
    title: str
    path: str
    tier: Tier = Tier.UNVERIFIED
    lang: str = "en"
    # What the document is ABOUT, declared in front matter as `about:`. Two
    # documents sharing a subject are comparable, so a disagreement between
    # them is a real contradiction rather than a coincidence of vocabulary.
    subject: str = ""
    # A document explicitly marked `status: superseded` in its front matter.
    # Kept in the corpus on purpose - an old contract or handbook is still the
    # right answer to "what did it say last year" - but it must never win a
    # disagreement with the current version silently.
    superseded: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    ordinal: int
    text: str
    heading: str = ""
    tier: Tier = Tier.UNVERIFIED
    subject: str = ""
    superseded: bool = False

    def label(self) -> str:
        """Short human-facing citation label, e.g. 'fridge-manual §Warranty'."""
        return f"{self.doc_id}{' §' + self.heading if self.heading else ''}"


class Retrieved(BaseModel):
    chunk: Chunk
    score: float
    # Fraction of the question's distinctive vocabulary this chunk contains,
    # IDF-weighted. Unlike the fused score this is absolute, which is why the
    # refusal gate reads this and not `score`.
    coverage: float = 0.0
    dense_rank: int | None = None
    lexical_rank: int | None = None

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id


class Verdict(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNCITED = "uncited"  # the model made a factual-looking claim with no citation at all


class Claim(BaseModel):
    """One sentence of the answer, plus what happened when we checked it."""

    text: str
    cited_chunk_ids: list[str] = Field(default_factory=list)
    verdict: Verdict = Verdict.UNCITED
    verifier_note: str = ""

    @property
    def is_trustworthy(self) -> bool:
        return self.verdict == Verdict.SUPPORTED


class Outcome(str, Enum):
    ANSWERED = "answered"
    REFUSED_NO_EVIDENCE = "refused_no_evidence"
    REFUSED_OUT_OF_SCOPE = "refused_out_of_scope"
    CONFLICT = "conflict"
    # Answered from the model's own knowledge, not from any document. Shown
    # labelled as such and never carries a citation (ADR-013).
    GENERAL = "general"


class Answer(BaseModel):
    question: str
    outcome: Outcome
    claims: list[Claim] = Field(default_factory=list)
    retrieved: list[Retrieved] = Field(default_factory=list)
    refusal_reason: str = ""
    routed_to: str = ""
    conflicts: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    model: str = ""
    # A follow-up rewritten to stand on its own ("and when does it end?" ->
    # "When does the tenancy agreement end?"). Empty when asked as written.
    asked_as: str = ""

    # -- derived views -------------------------------------------------------

    @property
    def text(self) -> str:
        return " ".join(c.text for c in self.claims).strip() or self.refusal_reason

    @property
    def asserted(self) -> bool:
        """Did Amin make any factual assertion at all? Core signal for the eval."""
        return self.outcome in (Outcome.ANSWERED, Outcome.CONFLICT) and bool(self.claims)

    @property
    def refused(self) -> bool:
        return self.outcome in (Outcome.REFUSED_NO_EVIDENCE, Outcome.REFUSED_OUT_OF_SCOPE)

    @property
    def citation_precision(self) -> float:
        """Of the claims that cited something, how many actually checked out."""
        cited = [c for c in self.claims if c.cited_chunk_ids]
        if not cited:
            return 0.0
        return sum(c.is_trustworthy for c in cited) / len(cited)

    @property
    def unsupported_claims(self) -> list[Claim]:
        return [c for c in self.claims if not c.is_trustworthy]

    def sources(self) -> list[dict[str, Any]]:
        by_id = {r.chunk_id: r for r in self.retrieved}
        used, seen = [], set()
        for claim in self.claims:
            for cid in claim.cited_chunk_ids:
                if cid in seen or cid not in by_id:
                    continue
                seen.add(cid)
                ch = by_id[cid].chunk
                used.append(
                    {
                        "chunk_id": cid,
                        "doc_id": ch.doc_id,
                        "heading": ch.heading,
                        "tier": ch.tier.label,
                        "text": ch.text,
                    }
                )
        return used
