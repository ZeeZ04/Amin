# Decision records

## ADR-001 — Do not pretrain. Assemble and ground instead.
**Status:** accepted · **Date:** 2026-10-04

Pretraining cost is roughly `C ≈ 6ND` FLOPs. A toy 1B model on 1T tokens is
~6×10²¹ FLOPs — about 4,000 H100-hours, $8–12k at commodity rates — and produces
something worse than open 8B weights. A 27B model on 15T tokens is ~2.4×10²⁴
FLOPs, ~1.7M H100-hours, millions of dollars.

More importantly, it would not deliver the goal. A model trained exclusively on
true statements still fabricates fluently: pretraining teaches next-token
prediction, and facts are compressed lossily across billions of weights with no
lookup table to keep pure. Corpus curation is the expensive lever with the
weakest effect on truthfulness.

**Decision:** use open weights (Apache 2.0: Qwen3.6, Gemma 4) and spend all
effort at inference time — retrieval, citation, verification, refusal.

**Consequence:** the project's novelty must live in the layers around the model.
That is where the eval harness and verifier came from, and they are the parts
worth showing anyone.

## ADR-002 — Verifiability, not correctness, is the design target
**Status:** accepted · **Date:** 2026-10-04

A curation rule of "sources I already trust" does not remove bias, it
concentrates it — and wraps it in an interface people trust *more* because it is
home-built. That is a worse failure than the one it set out to fix.

**Decision:** Amin is never the authority. Its job is to hand over the actual
passage so a person can be the authority. Every feature is judged by whether it
makes a claim easier to check, not by whether it makes Amin sound right.

**Consequence:** citations are a first-class part of the data model, not a
rendering concern; source tier is stored and displayed; conflicting sources are
surfaced rather than resolved.

## ADR-003 — Gate refusal on IDF coverage, not on the retrieval score
**Status:** accepted · **Date:** 2026-10-04 · supersedes the original gate

RRF scores derive from ranks, so the top hit scores ~1/(k+1) regardless of
quality. Measured spread between a precisely-answerable question and one the
corpus knows nothing about: 0.03643 vs 0.03614. No usable floor exists there.

**Decision:** gate on the IDF-weighted share of the question's distinctive terms
present in the best retrieved chunk, with unseen terms carrying maximum weight.

**Consequence:** one more pass over the chunk table to build a DF table, cached
per `Store` and invalidated on write. Full working in EXPERIMENTS E2/E3.

## ADR-004 — No fine-tuning until the eval set says what is broken
**Status:** accepted · **Date:** 2026-10-04

Fine-tuning to inject knowledge is the standard beginner mistake: it degrades
the base model and retrieval does the job better while staying updatable.

**Decision:** no LoRA until there are months of real logs and eval failures that
retrieval demonstrably cannot fix. Then tune only style, refusal phrasing,
Arabic register and citation format — never facts. An adapter that does not beat
the base model on the eval set gets discarded; that is what the harness is for.

## ADR-005 — Deterministic no-model provider is part of the product
**Status:** accepted · **Date:** 2026-10-04

**Decision:** ship `EchoProvider`, a lexical extractor implementing the same
interface, as the default for tests and CI.

**Consequence:** 38 behaviour tests and the full 30-item eval run offline in
under a second, so trust properties are regression-tested on every commit rather
than spot-checked by hand. Cost: the published baseline numbers are poor and
must be labelled clearly, every time, as plumbing rather than quality.
