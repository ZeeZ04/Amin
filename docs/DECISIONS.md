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

## ADR-006 — Every comparison carries an interval and a paired test
**Status:** accepted · **Date:** 2026-10-04

A table of percentages is not a result. On the original 30-item eval set,
grounded accuracy of 23.5% had a 95% interval of [9.6%, 47.3%] — a half-width of
19 points. Two systems 10 points apart were indistinguishable, and any "we beat
X" claim would have been noise presented as a finding.

**Decision:** every reported proportion carries a Wilson interval, and every
system-vs-system claim carries a McNemar paired test plus a paired bootstrap CI
on the difference. A difference whose interval crosses zero is reported as
inconclusive, not rounded away.

**Consequences:** Wilson rather than the normal approximation, because these
metrics live near 0 and 1 where the normal interval produces bounds outside
[0,1]. McNemar rather than a two-proportion z-test, because the systems answer
identical questions and treating them as independent samples discards the
pairing and inflates the p-value. The eval set grew from 30 to 173 items to make
the intervals usable; `required_n()` prints what any target precision costs.

## ADR-007 — Baselines are written to be strong, and graded on what they can do
**Status:** accepted · **Date:** 2026-10-04

Two ways to fake a win in an ablation: weaken the baseline's prompt, or grade it
on a capability it does not have. A bare model scored on `grounded_accuracy` is
guaranteed zero, which proves nothing.

**Decision:** baseline prompts in `amin/prompts.py` are written as a competent
engineer would write them for that architecture, including an instruction to
abstain. Grading splits into `fact_accuracy` (any system) and
`grounded_accuracy` (citing systems only), and cross-system claims are made only
on metrics every system can earn. The verbal-refusal detector is applied
identically to all three systems.

**Consequence:** the honest result is a trade, not a sweep — Amin gives up 8
points of fact accuracy (p=0.004) to gain 74 points of correct refusal
(p<0.0001). That is a more defensible claim than dominance, and it is the one
the data supports.

## ADR-008 — Aggregate metrics are not allowed to stand alone
**Status:** accepted · **Date:** 2026-10-04

This project has now been misled twice by an average. `overall_pass` stayed flat
at 0.533 across an evidence-floor range where hallucination went from 75% to
12.5% (E3). Then a paired test run across mixed item kinds reported `bare vs
naive: p=0.815, inconclusive` when naive was dramatically better at finding
facts and dramatically worse at refusing — the two effects cancelled (E6).

**Decision:** metrics are computed and tested per item kind. `overall_pass` is
reported but never optimised, and no paired test may run across slices.

**Consequence:** more columns, more p-values, and a report that cannot be
summarised in one number — which is the point. The cost asymmetry is made
explicit in `trust_score` instead, with its weight stated as a judgement.
