"""Three systems on one interface, so a benchmark can compare them fairly.

    bare    the model alone, no retrieval. Measures what the weights already
            know. On a synthetic corpus the correct score is near zero on
            answerable items - and whatever it scores on *unanswerable* items is
            pure fabrication, which is the interesting number.

    naive   retrieve top-k, stuff the passages into a conventional RAG prompt,
            return whatever comes back. No scope routing, no evidence gate, no
            citation verification. This is the baseline almost every RAG
            tutorial produces, and it is the system Amin has to beat to justify
            its own complexity.

    amin    the full pipeline.

Keeping all three in one module, behind one `answer(question) -> Answer` call,
is what makes the ablation honest: they share the same retriever, the same
model, the same eval set and the same grader. The only thing that varies is the
machinery under test.
"""

from __future__ import annotations

import time
from typing import Protocol

from .answer import Amin
from .config import settings
from .covenant import Covenant
from .prompts import NAIVE_RAG_SYSTEM, PLAIN_SYSTEM, format_passages, looks_like_refusal
from .providers import Provider, get_provider
from .schema import Answer, Claim, Outcome, Verdict
from .store import Store
from .verifier import Verifier, split_sentences


class System(Protocol):
    name: str
    cites: bool  # whether this system is capable of producing citations at all

    def answer(self, question: str) -> Answer: ...


# ---------------------------------------------------------------------------


class BareSystem:
    """The model with no retrieval. Upper bound on priors, and a fabrication meter."""

    name = "bare"
    cites = False

    def __init__(self, provider: Provider | None = None):
        self.provider = provider or get_provider()

    def answer(self, question: str) -> Answer:
        started = time.perf_counter()
        try:
            text = self.provider.complete(question, system=PLAIN_SYSTEM).strip()
        except Exception as exc:
            text = ""
            note = f"{type(exc).__name__}: {exc}"
        else:
            note = ""

        claims = [
            Claim(text=s, verdict=Verdict.UNCITED, verifier_note="no retrieval in this system")
            for s in split_sentences(text)
        ]
        # A bare model has no notion of "no source", so the only refusal it can
        # express is a verbal one. Detect the common phrasings rather than
        # crediting it with a refusal it did not make.
        refused = looks_like_refusal(text)
        return Answer(
            question=question,
            outcome=Outcome.REFUSED_NO_EVIDENCE if refused or not text else Outcome.ANSWERED,
            claims=[] if refused or not text else claims,
            refusal_reason=text if refused else note,
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=f"{self.provider.name}:{settings.answer_model}",
        )


class NaiveRagSystem:
    """Conventional RAG: retrieve, stuff, answer. No gates, no verification."""

    name = "naive"
    cites = False

    def __init__(self, store: Store | None = None, provider: Provider | None = None):
        self.store = store or Store()
        self.provider = provider or get_provider()

    def answer(self, question: str) -> Answer:
        started = time.perf_counter()
        try:
            qvec = self.provider.embed([question])[0]
        except Exception:
            qvec = None
        retrieved = self.store.search(question, qvec)

        passages, _ = format_passages(retrieved)
        prompt = f"{passages}\n\n<question>{question}</question>"
        try:
            text = self.provider.complete(prompt, system=NAIVE_RAG_SYSTEM).strip()
        except Exception as exc:
            text = ""
            note = f"{type(exc).__name__}: {exc}"
        else:
            note = ""

        refused = looks_like_refusal(text)
        claims = [
            Claim(text=s, verdict=Verdict.UNCITED, verifier_note="no verification in this system")
            for s in split_sentences(text)
        ]
        return Answer(
            question=question,
            outcome=Outcome.REFUSED_NO_EVIDENCE if refused or not text else Outcome.ANSWERED,
            claims=[] if refused or not text else claims,
            refusal_reason=text if refused else note,
            retrieved=retrieved,
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=f"{self.provider.name}:{settings.answer_model}",
        )


class AminSystem:
    """The full pipeline, wrapped to match the benchmark interface."""

    name = "amin"
    cites = True

    def __init__(
        self,
        store: Store | None = None,
        provider: Provider | None = None,
        verifier: Verifier | None = None,
        covenant: Covenant | None = None,
    ):
        prov = provider or get_provider()
        self.engine = Amin(
            store=store,
            provider=prov,
            covenant=covenant,
            verifier=verifier or Verifier(prov),
        )

    def answer(self, question: str) -> Answer:
        return self.engine.ask(question)


# ---------------------------------------------------------------------------

SYSTEMS = {"bare": BareSystem, "naive": NaiveRagSystem, "amin": AminSystem}


def build_system(
    kind: str,
    store: Store | None = None,
    provider: Provider | None = None,
    verifier_mode: str | None = None,
) -> System:
    kind = kind.lower()
    if kind not in SYSTEMS:
        raise ValueError(f"unknown system {kind!r} (expected {', '.join(SYSTEMS)})")
    prov = provider or get_provider()
    if kind == "bare":
        return BareSystem(provider=prov)
    if kind == "naive":
        return NaiveRagSystem(store=store or Store(), provider=prov)
    return AminSystem(
        store=store or Store(),
        provider=prov,
        verifier=Verifier(prov, mode=verifier_mode),
    )
