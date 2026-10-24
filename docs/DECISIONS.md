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


## ADR-009 — Conflicts are detected in code, not delegated to the model
**Status:** accepted · **Date:** 2026-10-04

The original implementation trusted the model to begin its draft with the word
`CONFLICT`. That is unverifiable, untestable without a model, and fails
silently. Measured: asked for the PHY-104 coursework weighting with two
handbooks giving 30% and 40%, Amin retrieved both at coverage 1.00 and answered
"30 percent" with a clean citation.

**Decision:** detect disagreement in `amin/conflict.py`, before generation, from
the retrieved passages. Version skew (one live source vs a superseded one)
answers from the current source and surfaces the old one; a genuine conflict
between live sources shows both and picks neither.

**Consequence:** conflict detection is testable without a model and cannot be
silently lost by a prompt change. It also needs its own machinery — number
tokenisation, answer-position scoping, document relatedness — each of which is
an experiment in its own right (E9–E11).

## ADR-010 — Document relatedness is declared, not inferred
**Status:** accepted · **Date:** 2026-10-04

Only comparable documents can contradict each other. A tenancy contract and an
electricity tariff both have a section headed "Security deposit" with different
figures; they are about different deposits. Chunk-level vocabulary overlap was
measured as a discriminator and **failed**: the false pair scored 0.172 against
the real pair's 0.167.

**Decision:** documents declare `about: <subject>` in front matter, and only
documents sharing a subject can conflict. Document-level vocabulary overlap at
0.15 is the fallback for undeclared documents.

**Consequence:** curation work — someone must say what a document is about. That
is the same kind of work the project already requires for `tier:`, and it is
reliable in a way the inferred version demonstrably is not. The fallback's
threshold is a property of this 14-document corpus, and that is written down
where the threshold lives.

## ADR-011 — A change that improves accuracy and worsens refusal is a regression
**Status:** accepted · **Date:** 2026-10-04

Indexing document titles raises fact accuracy by 2.7pp and fixes a failing
conflict item. It also raises hallucination by 13.1pp, because every chunk
inherits its document's name, so a question naming a document scores high
coverage against chunks that do not contain the answer — and the evidence gate,
whose entire job is to ask "does anything here actually cover this?", waves them
through.

**Decision:** rejected. Changes are judged on `trust_score`
(`grounded_accuracy − 3 × hallucination_rate`), which makes this −0.366.

**Consequence:** `c001` remains a failing eval item, and that failure is the
honest record of a real limitation rather than a number bought by weakening the
safety property. Any future change that moves accuracy and hallucination in the
same direction gets this treatment.

## ADR-012 — Post-train a student once the eval can judge it
**Status:** accepted · **Date:** 2026-10-18 · amends ADR-004

ADR-004 said: no fine-tuning until the eval set says what is broken. It now
does. E16–E20 put `qwen3.6:27b` at 98.2% fact accuracy and 7.1% hallucination,
at a p50 of 5.6 s. The native-app plan names that latency as a risk for phone
use, and the residual hallucination is something no pipeline change has moved.

**Decision:** post-train a smaller Qwen (Qwen3-8B) into Amin's own model in
two stages, on Apple silicon with MLX:

1. *Distillation (SFT, LoRA).* The 27B runs the real pipeline over a synthetic
   training corpus. Only exchanges `evaluate.grade()` passes become examples.
2. *Preference tuning (DPO).* The student is sampled; its graded failures are
   the `rejected` side of pairs whose `chosen` side is the teacher's reply to
   the same prompt.

Facts never go into the weights; only behaviour does. Every example is a
passage-grounded `answer_prompt()`, the same one used at inference, so retrieval
and citations stay and new documents need no retraining. Training a model on
the household's own papers was considered and rejected: it loses citations,
cannot take a new document, and puts private data inside a model file.

**Guardrails:**
- The training corpus (`amin/train/corpus.py`) shares no document, question,
  8-gram of text or eval entity name with `data/corpus` or the eval set.
  `tests/test_train.py` checks this on every commit.
- **Ship gate.** On the 237-item bench, hallucination ≤ 7.1%, fact accuracy
  not significantly below the teacher (paired McNemar, ADR-006), and p50
  latency ≤ 2.5 s. An adapter that misses any of the three is discarded, as
  ADR-004 always required.

**Consequence:** the `mlx` provider becomes a first-class path. Its
embeddings come from Ollama, not the hash embedder, so a student bench
compares models rather than retrievers. Every training run is an experiment
row (E23 onward). The workflow is in `docs/TRAINING.md`.

## ADR-013 — General by default, documents by project, sharing by permission
**Status:** accepted · **Date:** 2026-10-20 · amends ADR-002's refusal stance

Amin used to refuse anything its documents did not state, including "When
did the Berlin Wall fall?". The owner wants an assistant that answers what
any good model knows, plus documents that it answers from with citations. A
refusal on general knowledge is not a safety property. It is a missing
feature, and it pushed people to other tools for ordinary questions.

**Decision:**
1. **General chat answers anything** from the model's own knowledge. If no
   document backs the answer, it is labelled "General knowledge · not from
   your documents" and carries no citation. Any `[S…]` tag the model emits is
   stripped. The general prompt tells the model to decline personal details
   it cannot know ("my landlord's name") instead of guessing.
2. **Projects** hold their own documents, indexed on upload, never trained
   into weights. In a project, answers come from its documents with
   citations first. Where they don't cover the question, the labelled
   general answer is used. The general answer never sees the near-miss
   passages, because stitching them in is the adjacent-fact hallucination
   in a new coat.
3. **Every crossing between memories is a permission, off by default**
   (`amin/spaces.py`): a project may read the owner's private library, a
   project may read the household library, general chat may use a project,
   and a project may be shared with named household members. The person's
   own libraries feed their own chat by default and can be switched off.
   Documents are copied into each index the permissions allow, so revoking
   a permission deletes them. Granting the private library to a shared
   project warns first.
4. **Unchanged:** the conflict detector and the evidence and identifier
   gates still decide *whether documents answer*. Medical, legal, financial
   and crisis routing still refer the person on. Loosening those is a
   separate decision.

**Measurement.** `Amin(fallback=False)` is the strict pipeline every earlier
benchmark measured, and it stays the `amin` row. The app's behaviour is the
new `hybrid` row. The 12 prior-leak probes gained `expect_general` (their
true answers). A strict system still passes them by refusing. A hybrid
system passes only with the right fact, and on personal-detail
unanswerables only by declining. `hallucination` therefore keeps its
meaning: a fabricated document claim, or an invented personal detail.

**Consequences:** "refuses out loud when it has no source" now reads
"labels out loud when it has no source". Model training targets change with
it. amin-2 must keep general answering intact, and preference pairs must
not teach "refuse" where the product now wants "answer generally".

## ADR-014 — Public, on-device, and Malayalam decide the next base model
**Status:** proposed · **Date:** 2026-10-22

Amin is to be released to the public as a private assistant that runs fully on
each person's own devices: iPhone, iPad, Mac, Apple Watch, Vision Pro, Apple
TV, Apple's home hub, and Android phones and tablets. Malayalam joins English
and Arabic, and has to be accurate. Each person's data, including their
conversation history (`amin/history.py`, one SQLite file per person), stays in
their own store.

E32 showed that Qwen3, amin-3's base, spends 4.7× the tokens on Malayalam that
it spends on English. On a phone, that cost is paid in seconds and battery.

**Decision (proposed):** train the next student on the base that does best on
E32's Malayalam sets, with tokenizer cost and on-device size weighed in.
Gemma 4 E4B is the leading candidate (2.94 characters per token on Malayalam,
designed for phones). It still has to pass the same comparative gate amin-3
passed (E31): not significantly worse than the teacher on the main set, slice
m and the Malayalam test slice, so English and Arabic cannot regress.

**Rejected:** fine-tuning Malayalam into amin-3, which keeps the tokenizer
cost; LangChain, which would replace the measured pipeline with an
unmeasured one; and hosted classifiers such as Jev, which are API-only and so
break "nothing leaves the device". The single-pass classification idea behind
Jev can run locally on Amin's own model.

## ADR-015 — Owners teach Amin through memory, not through its weights
**Status:** accepted · **Date:** 2026-10-24 · extends ADR-012

The owner's goal is an assistant people can trust *and teach*. "Teach" could
mean fine-tuning each person's facts into the model on their device. It does
not, for the same reasons ADR-012 kept household documents out of the
weights:

- **Trust needs a source.** A fact in the weights cannot be cited. A fact in
  memory is cited like any document ("Your memory · Told on 24 October 2026").
- **Forgetting must be real.** Deleting a memory removes it from every index
  at once (`tests/test_app.py::test_memory_edits_reach_the_index_not_just_the_file`).
  Getting a fact out of weights needs retraining, and even then nothing proves it is gone.
- **Private data stays out of model files.** A weights file is easy to copy,
  share or ship in a backup. Memory is a JSON file in the person's own folder.
- **It works immediately.** No training run, no GPU, no gate.

**Decision.** "Remember that …", and the Arabic and Malayalam equivalents
(`amin/memory.py`), or Settings › Memory, saves a fact to
`data/users/<name>/memory.json`. It is rendered as `memory.md` in the
person's private library, with one section per fact, so each fact is its own
citation. Only an explicit request saves anything. The private-library
permissions (ADR-013) decide where memory is read.

**What training is for.** Behaviour across everyone: citing, declining,
languages, routing. It never carries one person's facts. Accuracy and
hallucination are improved by training on the model's own graded failures
(E24, E35 onward), not by memorising answers.
