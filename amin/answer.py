"""The answer pipeline.

    question
      -> covenant scope check        (refuse out-of-scope before retrieving)
      -> retrieve (hybrid)           (dense + BM25, RRF-fused, tier-adjusted)
      -> evidence floor              (refuse rather than answer from nothing)
      -> generate draft              (answer only from passages, tag each sentence)
      -> verify every sentence       (against the chunk it actually cited)
      -> assemble or refuse          (drop/demote failures; refuse if too many)

The order matters. Most RAG systems generate first and bolt a confidence score
on afterwards; here the two refusal gates sit on either side of generation, so
the model never gets the chance to be fluent about nothing.
"""

from __future__ import annotations

import re
import time

import numpy as np

from .config import settings
from .conflict import Conflict
from .conflict import detect as detect_conflict
from .covenant import Covenant
from .prompts import (
    ANSWER_SYSTEM,
    GENERAL_SYSTEM,
    answer_prompt,
    general_prompt,
    looks_like_refusal,
)
from .providers import Provider, get_provider
from .schema import Answer, Claim, Outcome, Retrieved, Verdict
from .store import Store
from .verifier import Verifier

_TAG_RE = re.compile(r"\s*\[S\d+\]")


class Amin:
    def __init__(
        self,
        store: Store | None = None,
        provider: Provider | None = None,
        covenant: Covenant | None = None,
        verifier: Verifier | None = None,
        fallback: bool | None = None,
    ):
        self.store = store or Store()
        self.provider = provider or get_provider()
        self.covenant = covenant or Covenant()
        self.verifier = verifier or Verifier(self.provider)
        # Strict (False): no source, no answer - the behaviour every benchmark
        # before ADR-013 measured. Fallback (True): no source, so answer from
        # general knowledge, labelled as such and never cited.
        self.fallback = settings.general_fallback if fallback is None else fallback

    # -- retrieval -----------------------------------------------------------

    def embed_query(self, question: str) -> np.ndarray | None:
        try:
            return self.provider.embed([question])[0]
        except Exception:
            # Dense arm unavailable (no embed model pulled, server down).
            # Lexical retrieval still works, so degrade instead of failing.
            return None

    def retrieve(self, question: str, limit: int | None = None) -> list[Retrieved]:
        return self.store.search(question, self.embed_query(question), limit=limit)

    # -- answering -----------------------------------------------------------

    def ask(self, question: str) -> Answer:
        started = time.perf_counter()
        question = question.strip()

        def finish(ans: Answer) -> Answer:
            ans.latency_ms = int((time.perf_counter() - started) * 1000)
            ans.model = f"{self.provider.name}:{getattr(self.provider, 'model_label', settings.answer_model)}"
            return ans

        # Gate 1 — scope. Checked before retrieval so an out-of-scope question
        # never produces a synthesised answer even if the corpus has material.
        decision = self.covenant.check(question)
        if not decision.allowed and decision.route:
            route = decision.route
            return finish(
                Answer(
                    question=question,
                    outcome=Outcome.REFUSED_OUT_OF_SCOPE,
                    refusal_reason=f"{route.message.strip()} Please ask {route.refer_to}.",
                    routed_to=route.name,
                    retrieved=self.retrieve(question),
                )
            )

        # Nothing indexed here (a general chat with no library): nothing to
        # retrieve, so go straight to general knowledge.
        if self.fallback and not self.store.doc_ids():
            return finish(self._general(question, [], searched=False))

        # One retrieval, two depths: the top-k goes to the model, the wider pool
        # goes to conflict detection.
        pool = self.retrieve(question, limit=settings.top_k_conflict)
        retrieved = pool[: settings.top_k_final]

        # Gate 2 — evidence. The single most important line in the project.
        if not self.covenant.has_evidence(retrieved):
            return finish(self._no_evidence(question, retrieved))

        # Gate 2b — identity. Evidence about a sibling product is not evidence.
        if settings.identifier_gate and (
            missing := self.covenant.missing_identifiers(question, pool)
        ):
            return finish(
                self._no_evidence(
                    question,
                    retrieved,
                    self.covenant.refusal_template.strip()
                    + f" (No document mentions {', '.join(missing)}.)",
                )
            )

        # Gate 3 — disagreement, detected in code before the model ever sees the
        # passages. Left to the model, a contradiction between two sources gets
        # silently resolved and then confidently cited, which is the worst thing
        # this system could do: the citation makes an arbitrary choice look
        # sourced. See amin/conflict.py.
        #
        # Two shapes, handled differently on purpose:
        #   version skew  - one live source contradicted only by a superseded
        #                   one. Answer normally from the live sources, then
        #                   append the note. Refusing here would make Amin
        #                   useless every time a contract was renewed.
        #   genuine clash - two live sources disagree. Show both, pick neither.
        skew_note: Conflict | None = None
        all_retrieved = pool
        if (clash := detect_conflict(question, pool, related=self.store.are_related)) is not None:
            if not clash.is_version_skew:
                return finish(self._conflict_answer(question, clash, pool))
            skew_note = clash
            live = [r for r in pool[: settings.top_k_final] if not r.chunk.superseded]
            if live:
                retrieved = live

        prompt, tag_map = answer_prompt(question, retrieved)
        draft = self.provider.complete(prompt, system=ANSWER_SYSTEM).strip()

        # The model's own abstention signal.
        # Also the paraphrased one ("the passages do not contain…"): E19, u076.
        if draft.upper().startswith("NO_EVIDENCE") or not draft or looks_like_refusal(draft):
            return finish(self._no_evidence(question, retrieved))

        conflict = draft.upper().startswith("CONFLICT")
        if conflict:
            draft = draft.split(":", 1)[-1].strip()

        passages = {r.chunk_id: r.chunk.text for r in retrieved}
        claims = self.verifier.verify_draft(draft, tag_map, passages)

        if not claims:
            return finish(self._no_evidence(question, retrieved))

        kept = self._apply_verification(claims)
        if not kept:
            return finish(
                self._no_evidence(
                    question,
                    retrieved,
                    "I drafted an answer but could not verify it against my sources, "
                    "so I'm not going to show it.",
                )
            )

        answer = Answer(
            question=question,
            outcome=Outcome.CONFLICT if conflict else Outcome.ANSWERED,
            claims=kept,
            retrieved=retrieved,
            conflicts=[c.text for c in kept] if conflict else [],
        )

        # Last gate: if most of what survived is unverified, refuse rather than
        # hand over something that merely looks sourced.
        if answer.citation_precision < settings.min_citation_precision and not conflict:
            return finish(
                self._no_evidence(
                    question,
                    retrieved,
                    "My draft answer failed its own citation check "
                    f"({answer.citation_precision:.0%} of claims verified), so I'm withholding it.",
                )
            )

        # The superseded source is appended after the gates, so an outdated
        # document can never cause a good answer to be withheld - but it is
        # always shown, never dropped.
        if skew_note is not None:
            for old in skew_note.superseded:
                answer.claims.append(
                    Claim(
                        text=(
                            f"An older, superseded source disagrees: {old.label()} gives "
                            f"{', '.join(sorted(old.values))}."
                        ),
                        cited_chunk_ids=[old.chunk_id],
                        verdict=Verdict.SUPPORTED,
                        verifier_note="superseded source, surfaced not silenced",
                    )
                )
            answer.conflicts = skew_note.describe()
            # Restore the unfiltered list so the superseded chunk the note cites
            # can still be resolved by Answer.sources().
            answer.retrieved = all_retrieved
        return finish(answer)

    def _no_evidence(self, question: str, retrieved: list[Retrieved], reason: str = "") -> Answer:
        """No document supports an answer: refuse (strict) or answer generally."""
        if self.fallback:
            return self._general(question, retrieved)
        return Answer(
            question=question,
            outcome=Outcome.REFUSED_NO_EVIDENCE,
            refusal_reason=reason or self.covenant.refusal_template.strip(),
            retrieved=retrieved,
        )

    def _general(self, question: str, retrieved: list[Retrieved], searched: bool = True) -> Answer:
        """Answer from the model's own knowledge, labelled and uncited.

        The passages are deliberately not shown to the model here: they were
        judged not to answer the question, and a general answer stitched from
        near-miss passages is the adjacent-fact hallucination in a new coat.
        """
        draft = self.provider.complete(general_prompt(question, searched), system=GENERAL_SYSTEM).strip()
        draft = _TAG_RE.sub("", draft).strip()  # nothing here may look cited
        if not draft or draft.upper().startswith("NO_EVIDENCE"):
            return Answer(
                question=question,
                outcome=Outcome.REFUSED_NO_EVIDENCE,
                refusal_reason=self.covenant.refusal_template.strip(),
                retrieved=retrieved,
            )
        return Answer(
            question=question,
            outcome=Outcome.GENERAL,
            claims=[Claim(text=draft, verdict=Verdict.UNCITED, verifier_note="general knowledge")],
            retrieved=retrieved,
        )

    def _conflict_answer(
        self, question: str, clash: Conflict, retrieved: list[Retrieved]
    ) -> Answer:
        """Render a disagreement instead of resolving it.

        Two shapes, because they mean different things to a reader:

        *Version skew* - one current source contradicted only by a superseded
        one. The current document is the answer; the old one is a footnote. A
        system that refused here would be useless every time a contract was
        renewed.

        *Genuine conflict* - two live sources disagree. Amin does not pick. It
        shows both positions, each with its own citation, and stops.
        """
        claims: list[Claim] = []
        if clash.is_version_skew:
            current = clash.current[0]
            claims.append(
                Claim(
                    text=current.text.strip(),
                    cited_chunk_ids=[current.chunk_id],
                    verdict=Verdict.SUPPORTED,
                    verifier_note="current version; quoted verbatim",
                )
            )
            for old in clash.superseded:
                claims.append(
                    Claim(
                        text=(
                            f"A superseded source disagrees: {old.label()} gives "
                            f"{', '.join(sorted(old.values))}."
                        ),
                        cited_chunk_ids=[old.chunk_id],
                        verdict=Verdict.SUPPORTED,
                        verifier_note="superseded source, surfaced not silenced",
                    )
                )
        else:
            for position in clash.positions:
                claims.append(
                    Claim(
                        text=f"{position.label()}: {position.text.strip()}",
                        cited_chunk_ids=[position.chunk_id],
                        verdict=Verdict.SUPPORTED,
                        verifier_note="quoted verbatim; not resolved",
                    )
                )

        return Answer(
            question=question,
            outcome=Outcome.CONFLICT,
            claims=claims,
            retrieved=retrieved,
            conflicts=clash.describe(),
            refusal_reason=(
                ""
                if clash.is_version_skew
                else "My sources disagree and I will not pick one for you."
            ),
        )

    @staticmethod
    def _apply_verification(claims: list[Claim]) -> list[Claim]:
        """Drop claims that cited a passage and failed; keep uncited ones labelled.

        An UNSUPPORTED claim cited a specific passage and that passage does not
        state it — that is a fabrication with a false footnote, the worst output
        the system can produce, so it is removed outright. An UNCITED claim is
        model reasoning; it is kept but rendered differently so the reader can
        see the difference.
        """
        return [c for c in claims if c.verdict != Verdict.UNSUPPORTED]
