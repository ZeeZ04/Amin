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

import time

import numpy as np

from .config import settings
from .covenant import Covenant
from .prompts import ANSWER_SYSTEM, answer_prompt
from .providers import Provider, get_provider
from .schema import Answer, Claim, Outcome, Retrieved, Verdict
from .store import Store
from .verifier import Verifier


class Amin:
    def __init__(
        self,
        store: Store | None = None,
        provider: Provider | None = None,
        covenant: Covenant | None = None,
        verifier: Verifier | None = None,
    ):
        self.store = store or Store()
        self.provider = provider or get_provider()
        self.covenant = covenant or Covenant()
        self.verifier = verifier or Verifier(self.provider)

    # -- retrieval -----------------------------------------------------------

    def embed_query(self, question: str) -> np.ndarray | None:
        try:
            return self.provider.embed([question])[0]
        except Exception:
            # Dense arm unavailable (no embed model pulled, server down).
            # Lexical retrieval still works, so degrade instead of failing.
            return None

    def retrieve(self, question: str) -> list[Retrieved]:
        return self.store.search(question, self.embed_query(question))

    # -- answering -----------------------------------------------------------

    def ask(self, question: str) -> Answer:
        started = time.perf_counter()
        question = question.strip()

        def finish(ans: Answer) -> Answer:
            ans.latency_ms = int((time.perf_counter() - started) * 1000)
            ans.model = f"{self.provider.name}:{settings.answer_model}"
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

        retrieved = self.retrieve(question)

        # Gate 2 — evidence. The single most important line in the project.
        if not self.covenant.has_evidence(retrieved):
            return finish(
                Answer(
                    question=question,
                    outcome=Outcome.REFUSED_NO_EVIDENCE,
                    refusal_reason=self.covenant.refusal_template.strip(),
                    retrieved=retrieved,
                )
            )

        prompt, tag_map = answer_prompt(question, retrieved)
        draft = self.provider.complete(prompt, system=ANSWER_SYSTEM).strip()

        # The model's own abstention signal.
        if draft.upper().startswith("NO_EVIDENCE") or not draft:
            return finish(
                Answer(
                    question=question,
                    outcome=Outcome.REFUSED_NO_EVIDENCE,
                    refusal_reason=self.covenant.refusal_template.strip(),
                    retrieved=retrieved,
                )
            )

        conflict = draft.upper().startswith("CONFLICT")
        if conflict:
            draft = draft.split(":", 1)[-1].strip()

        passages = {r.chunk_id: r.chunk.text for r in retrieved}
        claims = self.verifier.verify_draft(draft, tag_map, passages)

        if not claims:
            return finish(
                Answer(
                    question=question,
                    outcome=Outcome.REFUSED_NO_EVIDENCE,
                    refusal_reason=self.covenant.refusal_template.strip(),
                    retrieved=retrieved,
                )
            )

        kept = self._apply_verification(claims)
        if not kept:
            return finish(
                Answer(
                    question=question,
                    outcome=Outcome.REFUSED_NO_EVIDENCE,
                    refusal_reason=(
                        "I drafted an answer but could not verify it against my sources, "
                        "so I'm not going to show it."
                    ),
                    retrieved=retrieved,
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
                Answer(
                    question=question,
                    outcome=Outcome.REFUSED_NO_EVIDENCE,
                    refusal_reason=(
                        "My draft answer failed its own citation check "
                        f"({answer.citation_precision:.0%} of claims verified), so I'm withholding it."
                    ),
                    retrieved=retrieved,
                )
            )
        return finish(answer)

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
