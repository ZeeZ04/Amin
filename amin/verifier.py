"""Sentence-level citation verification.

This is the module that distinguishes Amin from a weekend RAG demo. A normal
RAG pipeline stops once the model has produced text that *looks* sourced. Here,
every sentence of the draft is checked against the passage it actually cited,
and sentences that fail are either dropped or demoted to visibly unverified
reasoning.

Two backends:
  - `lexical`: content-word overlap plus strict numeric agreement. Fast, no
    model call, catches the common failure (model invents a figure).
  - `llm`: asks the small utility model whether the passage states the claim.
    Catches paraphrase and negation failures the lexical check misses.

The LLM backend falls back to lexical on any transport error, so a dead model
server degrades the verifier instead of crashing the answer.
"""

from __future__ import annotations

import re

from .config import settings
from .prompts import VERIFY_SYSTEM, verify_prompt
from .providers import Provider, content_tokens
from .schema import Claim, Verdict

CITE_RE = re.compile(r"\[(S\d+)\]")
SENT_SPLIT = re.compile(r"(?<=[.!?؟۔])\s+(?=[A-Z؀-ۿ\[])|\n+")
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
# Models place the tag either side of the full stop. Normalise to one form
# before splitting, or a trailing tag detaches and its sentence loses its
# citation - which would show up as a fabricated "uncited" claim.
TRAILING_CITE = re.compile(r"([.!?؟۔])(\s*)((?:\[S\d+\])+)")


def normalise_citations(text: str) -> str:
    return TRAILING_CITE.sub(lambda m: f"{m.group(3)}{m.group(1)}", text)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT.split(normalise_citations(text).strip()) if s.strip()]


def content_words(text: str) -> set[str]:
    return content_tokens(text)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUM_RE.findall(text)}


def lexical_support(claim: str, passage: str) -> tuple[bool, str]:
    """True if the passage plausibly states the claim.

    Numeric agreement is checked separately and strictly: a claim containing a
    figure absent from the passage is rejected regardless of word overlap. That
    single rule catches most fabricated specifics.
    """
    claim_nums, passage_nums = _numbers(claim), _numbers(passage)
    if missing := claim_nums - passage_nums:
        return False, f"figure(s) not in passage: {', '.join(sorted(missing))}"

    cw = content_words(claim)
    if not cw:
        return False, "no content words to check"
    overlap = len(cw & content_words(passage)) / len(cw)
    if overlap < settings.lexical_overlap_floor:
        return False, f"overlap {overlap:.2f} < floor {settings.lexical_overlap_floor:.2f}"
    return True, f"overlap {overlap:.2f}"


class Verifier:
    def __init__(self, provider: Provider, mode: str | None = None):
        self.provider = provider
        self.mode = (mode or settings.verifier).lower()

    def _llm_support(self, claim: str, passage: str) -> tuple[bool, str]:
        try:
            raw = self.provider.complete(
                verify_prompt(claim, passage),
                model=settings.utility_model,
                system=VERIFY_SYSTEM,
            )
        except Exception as exc:  # transport, timeout, model missing
            ok, note = lexical_support(claim, passage)
            return ok, f"llm unavailable ({type(exc).__name__}); lexical: {note}"
        verdict = raw.strip().upper()
        # Strip any reasoning preamble a chatty model prepends.
        yes = verdict.startswith("YES") or verdict.endswith("YES")
        no = verdict.startswith("NO") or verdict.endswith("NO")
        if not (yes or no):
            ok, note = lexical_support(claim, passage)
            return ok, f"llm reply unparsed {raw[:40]!r}; lexical: {note}"
        return yes, f"llm: {'YES' if yes else 'NO'}"

    def supports(self, claim: str, passage: str) -> tuple[bool, str]:
        if self.mode == "off":
            return True, "verification disabled"
        if self.mode == "lexical":
            return lexical_support(claim, passage)
        # Cheap check first: if the numbers are wrong, no model call is needed.
        ok, note = lexical_support(claim, passage)
        if not ok and "figure(s) not in passage" in note:
            return False, note
        return self._llm_support(claim, passage)

    def verify_draft(
        self, draft: str, tag_map: dict[str, str], passages: dict[str, str]
    ) -> list[Claim]:
        """Turn raw model output into checked claims.

        `tag_map` maps S-tags to chunk ids; `passages` maps chunk ids to text.
        """
        claims: list[Claim] = []
        for sentence in split_sentences(draft):
            tags = CITE_RE.findall(sentence)
            clean = CITE_RE.sub("", sentence).strip()
            clean = re.sub(r"\s+([.,;:])", r"\1", clean)
            if not clean or clean in {".", "-"}:
                continue

            chunk_ids = [tag_map[t] for t in dict.fromkeys(tags) if t in tag_map]
            if not chunk_ids:
                # A sentence with no citation. If it asserts nothing checkable
                # (e.g. "Here is what the policy says") we drop it; if it does
                # assert something, we keep it and mark it plainly.
                if len(content_words(clean)) < 3:
                    continue
                claims.append(
                    Claim(text=clean, verdict=Verdict.UNCITED, verifier_note="no citation given")
                )
                continue

            notes = []
            supported = False
            for cid in chunk_ids:
                ok, note = self.supports(clean, passages.get(cid, ""))
                notes.append(f"{cid}: {note}")
                if ok:
                    supported = True
                    break
            claims.append(
                Claim(
                    text=clean,
                    cited_chunk_ids=chunk_ids,
                    verdict=Verdict.SUPPORTED if supported else Verdict.UNSUPPORTED,
                    verifier_note="; ".join(notes),
                )
            )
        return claims
