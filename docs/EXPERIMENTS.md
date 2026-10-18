# Experiment log

Every change that moves a metric gets a row. A change with no measurement is
not an improvement, it is a guess. Dates are the day the experiment was run.

Harness: `amin bench`. Unless stated, provider is `echo` — a deterministic
lexical extractor with **no language model** — so these numbers measure the
**pipeline**, not model quality.

| id | date | change | items | result |
|---|---|---|---|---|
| E0 | 2026-10-04 | first end-to-end run | 30 | baseline: g_acc 0.412, halluc 0.500 |
| E1 | 2026-10-04 | fix: echo provider swallowed the question block into the last passage | 30 | bug, not a result |
| E2 | 2026-10-04 | **evidence gate moved from RRF score to IDF-weighted query coverage** | 30 | enabled E3 |
| E3 | 2026-10-04 | `evidence_floor` swept 0.00 → 0.70, default set to 0.45 | 30 | halluc 0.500 → 0.125 |
| E4 | 2026-10-04 | **eval set 30 → 173 items, corpus 6 → 13 documents; added Wilson CIs and paired tests** | 173 | CI half-width on answerable 18.9pp → 9.1pp |
| E5 | 2026-10-04 | **ablation study: bare vs naive RAG vs Amin** | 173 | the headline result, below |
| E6 | 2026-10-04 | fix: paired tests were comparing across mixed item kinds | 173 | invalidated E5's first p-values; rerun |
| E7 | 2026-10-04 | **conflict detection built in code**; supersession; 14th document | 237 | 5/6 conflict items; no metric moved — see below |
| E8 | 2026-10-04 | **unanswerable slice 38 → 99 items** | 237 | hallucination CI ±15.2pp → ±9.0pp |
| E9 | 2026-10-04 | fix: monetary figures were split on the comma | 237 | prerequisite for E7 |
| E10 | 2026-10-04 | document relatedness via declared `about:` subjects | 237 | 4 false conflicts → 0 |
| E11 | 2026-10-04 | conflict coverage band swept against the whole eval set | 237 | **adopted 0.70** |
| E12 | 2026-10-04 | **indexing document titles — tested and rejected** | 237 | +2.7pp facts, **+13.1pp hallucination** |

---

## E4 — the eval set was too small to compare anything

Before comparing systems, the measuring instrument had to be checked. On the
original 30-item set:

| slice | n | metric | 95% CI | half-width |
|---|---|---|---|---|
| answerable | 17 | grounded accuracy 23.5% | [9.6%, 47.3%] | **±18.9pp** |
| unanswerable | 8 | hallucination 12.5% | [2.2%, 47.1%] | **±22.4pp** |

A ±19-point interval cannot distinguish a good system from a mediocre one. Any
"Amin beats X" claim built on that set would have been noise presented as a
finding — and the first question a competent reviewer asks is "what's your
confidence interval?".

Worst-case sample sizes (p=0.5, 95%): **97 items** for ±10pp, **385** for ±5pp.

Eval set rebuilt to 173 items over 13 synthetic documents:

| slice | n | worst-case half-width |
|---|---|---|
| answerable | 113 | ±9.1pp |
| unanswerable | 38 | ±15.2pp |
| out-of-scope | 22 | ±19.3pp |

**The unanswerable slice is still the weak one, and it carries the headline
metric.** ±15pp is enough to detect "naive RAG hallucinates 100% vs Amin 26%"
and nowhere near enough to detect a 10-point difference. Any future change that
claims to improve hallucination by a few points needs that slice at 97+ items
first. This is the project's most important outstanding limitation.

The set is generated from `scripts/build_eval_set.py` rather than hand-edited,
so proportions, id uniqueness and the existence of every `expect_doc` are
validated on every build.

## E5 — the ablation: does the pipeline earn its complexity?

Three systems, same retriever, same model, same 173 items, same grader:

- **bare** — the model alone, no retrieval. Measures priors.
- **naive** — retrieve top-k, stuff into a conventional RAG prompt, return the
  answer. No scope routing, no evidence gate, no citation verification. Written
  as a competent engineer would write it, not weakened: a strawman baseline
  produces a number that cannot be defended.
- **amin** — the full pipeline.

| metric | bare | naive | amin | direction |
|---|---|---|---|---|
| fact accuracy | 0.0% ±2% | **31.0% ±8%** | 23.0% ±8% | higher |
| grounded accuracy | 0.0% | 0.0% | **23.0% ±8%** | higher |
| correct refusal | 100.0% ±5% | 0.0% ±5% | 73.7% ±14% | higher |
| hallucination rate | **0.0% ±5%** | 100.0% ±5% | 26.3% ±14% | LOWER |
| citation precision | 0.0% | 0.0% | **100.0%** | higher |
| routing accuracy | 0.0% | 0.0% | **95.5% ±10%** | higher |
| trust score | +0.000 | −3.000 | −0.559 | higher |

Paired tests (McNemar on identical items, per slice):

| comparison | metric | A only | B only | delta (95% CI) | p |
|---|---|---|---|---|---|
| bare vs naive | fact accuracy | 0 | 35 | −31.0% [−39.8%, −22.1%] | <0.0001 |
| bare vs naive | correct refusal | 38 | 0 | +100.0% [+100%, +100%] | <0.0001 |
| bare vs amin | fact accuracy | 0 | 26 | −23.0% [−31.0%, −15.0%] | <0.0001 |
| bare vs amin | correct refusal | 10 | 0 | +26.3% [+13.2%, +39.5%] | 0.002 |
| naive vs amin | fact accuracy | 9 | 0 | **+8.0% [+3.5%, +13.3%]** | 0.004 |
| naive vs amin | correct refusal | 0 | 28 | **−73.7% [−86.8%, −60.5%]** | <0.0001 |

### What this actually says

**Amin trades 8 points of fact accuracy for 74 points of correct refusal.**
Both differences are statistically significant and neither interval crosses
zero. That trade is the entire thesis of the project expressed as two numbers,
and it is the result to lead with — not a claim of dominance, which the data
does not support.

Two honest readings of the table that are easy to get wrong:

**`bare` scoring 0% fact accuracy and 0% hallucination is not a good result.**
With the echo provider, a bare system with no passages has nothing to extract
and abstains on everything. It is a system that always says "I don't know": a
perfect refusal rate and useless. This is exactly why `correct_refusal` cannot
be read without `fact_accuracy` beside it, and why `trust_score` exists.

**`naive` hallucinating on 100% of unanswerable items is the finding.** Given
top-k passages and no gate, the extractor always produces something — the
retriever always returns *its best* chunk, however irrelevant, and nothing
downstream asks whether that chunk actually covers the question. This is the
default behaviour of a RAG pipeline built from a tutorial, and it is the
behaviour the evidence gate and verifier exist to prevent.

## E6 — the paired tests were wrong, and the fix changed the conclusion's basis

The first version of `compare_runs` ran McNemar on `fact_ok` across the whole
eval set. But `fact_ok` means "the expected fact appeared" on an answerable item
and "refused correctly" on an unanswerable one. Testing across both averaged two
opposite effects into one number, and produced `bare vs naive: p=0.815,
inconclusive` — when in truth naive is dramatically better at finding facts and
dramatically worse at refusing. The aggregate had cancelled them out.

Fixed by slicing before testing: `fact_accuracy` on answerable items only,
`correct_refusal` on unanswerable items only. Same data, correct conclusion.

Lesson, and it is the same one as E3: **an aggregate metric can hide the entire
behaviour of the system.** Twice now in this project, averaging across kinds
produced a number that looked fine and meant nothing.

---

## E7 — a documented capability that did not exist

The README advertised conflict mode. The implementation was one line: if the
model's draft happened to begin with the word `CONFLICT`, believe it. The
deterministic test provider never says it, no eval item tested it, and a real
model would say it unreliably. Asked "what is the coursework weighting for
PHY-104?" with two handbooks giving 30% and 40%, Amin retrieved **both at
coverage 1.00** and answered "30 percent" with a clean citation.

That is the worst output this system can produce. The citation is what makes
the arbitrary choice look sourced.

Conflict detection now runs in `amin/conflict.py`, **before** generation, on the
retrieved passages. Two sources conflict when they both substantially cover the
question, come from different documents, are *about the same thing*, and put
different numbers next to the question's own terms. Two shapes are handled
differently on purpose:

- **version skew** — one live source contradicted only by a `status: superseded`
  one. Answer from the current source, append the old one as a visible note.
  Refusing here would make Amin useless every time a contract was renewed.
- **genuine conflict** — two live sources disagree. Show both, pick neither.

**The headline result of E7 is that no metric moved at all.** Fact accuracy,
refusal, hallucination, routing: identical to three decimal places. The
capability did not exist, was built, and the scoreboard did not notice — because
nothing measured it. That is the clearest demonstration in this project of why
the eval set is the instrument and not the paperwork. Six conflict items were
then written, and the path scores 5/6.

## E9 — every monetary figure in the corpus was nonsense

Detection kept returning nothing. The tokeniser was `[A-Za-z0-9]+`, which splits
on the comma:

```
"AED 3,900"  ->  "3", "900"
"AED 1,000"  ->  "1", "000"   -> normalised -> "1", "0"
"AED 82,000" ->  "82", "000"
```

So the contract's 3,900 and the agency sheet's 4,100 were being compared as
`{3, 900}` against `{4, 100}` — disjoint, but meaninglessly so, and the real
figures never entered the comparison at all. Fixed by tokenising a number as a
unit, keeping decimals (`11.1` must not collapse onto `11`) while dropping
thousands separators.

Two related fixes fell out: numbers appearing in the *question* are excluded
(`PHY-104` put `104` in every passage and made contradictory handbooks look like
they agreed), and values are scoped to the **sentence** rather than a five-word
window (which missed "...for this unit is AED 4,100" by one word).

## E10 — vocabulary overlap cannot tell a conflict from a coincidence

First attempt gated conflicts on chunk-level word overlap: two passages must be
similar to each other before their disagreement counts. Measured on the real
pair and the obvious false pair:

| pair | chunk overlap |
|---|---|
| tenancy contract vs agency summary (**real conflict**) | 0.167 |
| tenancy contract vs electricity tariff (**false**) | **0.172** |

The false pair scored *higher*. Both documents have a section headed "Security
deposit" with different figures; they are about different deposits. No threshold
on this signal can work.

Document-level overlap separates cleanly (0.19 and 0.24 for the two genuinely
related pairs, ≤0.12 for every unrelated pair) — but a threshold tuned on
fourteen documents is not a law. So relatedness is **declared**: documents carry
`about: <subject>` in front matter, and only documents sharing a subject can
contradict each other. Document-level overlap at 0.15 is the fallback for
undeclared documents, with its failure mode written down.

## E11 — tuning the conflict band against the whole eval set

The coverage band decides which retrieved chunks enter the comparison. Tuned by
counting *false* conflicts on answerable items, not by maximising conflict-item
passes — which would reward over-firing:

| relative floor | conflict items passed | false conflicts on 110 answerable |
|---|---|---|
| 0.90 | 4/6 | 0 |
| 0.80 | 4/6 | 0 |
| **0.70** | **5/6** | **0** |
| 0.60 | 5/6 | 4 |
| 0.50 | 5/6 | 6 |

Adopted 0.70. All four false positives at 0.60 were inspected and all four were
spurious — in one, neither cited document was the one holding the answer.

**Known limitation, not fixed.** The detector compares *numbers in answer
position*, not *typed quantities*. Two sections of the same subject that discuss
different quantities can still look like a contradiction — at 0.60 the fridge
manual's error codes were "contradicted" by the Arabic summary's warranty
period. Tightening the band suppresses this; it does not solve it. A real fix
needs the quantity's type (a currency, a duration, a percentage), not just its
digits.

## E12 — indexing document titles: an obvious improvement that is a regression

`c001` ("the annual rent on the **Al Noor Tower** unit") fails because document
titles are not indexed: "Al Noor Tower" appears in the front matter, not in any
chunk body, so coverage is low and the evidence gate refuses. Indexing titles
looks like a free win. Measured:

| metric | without titles | with titles | delta |
|---|---|---|---|
| fact accuracy | 0.227 | 0.255 | **+2.7pp** |
| conflict items passed | 5/6 | **6/6** | +1 |
| correct refusal | 0.707 | 0.576 | −13.1pp |
| **hallucination rate** | 0.293 | **0.424** | **+13.1pp** |

Under the project's stated objective (`grounded_accuracy − 3 × hallucination`)
that is **−0.366**: a clear loss.

The mechanism is worth understanding, because it generalises. Adding the title
to every chunk's searchable text means *every* chunk of a document inherits the
document's name. A question that names the document then scores high coverage
against chunks that do not contain the answer, and the evidence gate — which
exists precisely to ask "does anything here actually cover this?" — waves them
through. The fix broke the gate it was supposed to help.

**Rejected.** `c001` stays failing, and that failure is now the honest record of
a real limitation rather than a number improved by weakening the safety
property.

---

## E16 — first real-model run (qwen3.6:27b via Ollama)

**Run 1 (discarded).** Full set, thinking on. bare and naive completed (6.1 h and
4.2 h); amin died on a 180 s `ReadTimeout`. The 27B at ~9 tok/s spent its
budget reasoning before answering. Fix: `think: false` for all calls
(`AMIN_THINK=1` to re-enable), timeout 600 s, and `amin bench` now exits
non-zero on a partial run (setup_mac.sh had printed "done" over it).
Discarded rather than reported: its bare/naive rows used thinking, so they are
not comparable with any amin row run without it.

**Run 2 — smoke, 31 items, thinking off.** 10 min total.

| | bare | naive | amin |
|---|---|---|---|
| fact accuracy | 28.6% | 100% | 71.4% |
| correct refusal | 23.1% | 100% | 100% |
| hallucination | 76.9% | 0% | 0% |

All four items amin missed and naive got were refused in ~12 ms by the
evidence floor (0.45) before any model call. The floor was tuned on the echo
stub. Naive's 0% hallucination is the first evidence for the kill criterion;
the sample is too small to decide it (no naive-vs-amin delta is significant).

**Floor sweep, full set (237), real model, weight 3.**

| floor | grounded | refusal | halluc | trust |
|---|---|---|---|---|
| 0.15 | 0.936 | 0.929 | 0.071 | 0.724 |
| 0.25 | 0.891 | 0.929 | 0.071 | 0.679 |
| 0.34 | 0.782 | 0.949 | 0.051 | 0.630 |
| 0.38 | 0.782 | 0.960 | 0.040 | 0.661 |
| 0.45 | 0.755 | 0.980 | 0.020 | 0.694 |

Reading it honestly:
- 0.25 and 0.34 are dominated (by 0.15 and 0.38). The real choice is 0.15 vs 0.45.
- 0.15 buys +18 pts grounded accuracy for +5 pts hallucination (2% → 7%).
- The winner is decided by the weight, not the data: 0.15 wins at weight 3
  (0.724 vs 0.694), 0.45 wins above weight ≈ 3.6. A 0.03 trust gap is inside
  the noise of a 237-item set.
- 0.15 is the edge of the grid; the optimum may be lower and is untested.
- Tuned on the same set it will be reported on — a mild optimistic bias.

**Why the floor cannot fix this (model-free diagnosis).** Max coverage per
item, lexical arm only:

| slice | p10 | p25 | median | p75 | p90 |
|---|---|---|---|---|---|
| answerable (110) | 0.27 | 0.47 | 0.58 | 0.76 | 1.00 |
| unanswerable (99) | 0.00 | 0.18 | 0.30 | 0.46 | 0.63 |

The distributions overlap across the whole useful range. At 0.15, 82/99
unanswerables pass the gate, yet hallucination is only 7%: **the model, not
the floor, is doing most of the refusing.** At 0.45 the floor blocks 23
answerables to stop a handful of unanswerables the model would mostly have
refused anyway. 12 of 14 near-miss items sit above 0.34 — no floor catches them.

**Fix: an identifier gate (Gate 2b).** If the question names an identifier
(FR-550, PHY-205, Freedom 300) that no chunk in the retrieval pool contains,
refuse. Offline on the full set: flags 13/99 unanswerables (9 of 14 near-miss)
and **0/110 answerables**. Caveat: the pattern was written while looking at
this eval set; the zero false positives need confirming on new questions.
Next: re-sweep the floor with the gate on — it should let the floor drop.

**Re-sweep with the identifier gate on.**

| floor | grounded | refusal | halluc | trust |
|---|---|---|---|---|
| 0.05 | 0.936 | 0.939 | 0.061 | 0.755 |
| 0.15 | 0.927 | 0.939 | 0.061 | 0.745 |
| 0.25 | 0.891 | 0.939 | 0.061 | 0.709 |
| 0.45 | 0.755 | 0.980 | 0.020 | 0.694 |

The gate moved hallucination at 0.15 from 7.1% to 6.1% — **one item**, not the
13 it flags offline. The model was already refusing nearly all of those; the
gate makes those refusals deterministic and instant but buys little accuracy.
Grounded at 0.15 fell 0.936 → 0.927 (one item): either the gate's first false
positive or run-to-run noise. Below 0.15 the floor no longer matters.

**Decision:** floor → 0.15. The remaining ~6 hallucinations at 0.15 are not
near-misses and are unexplained; the sweep does not save per-item results.
Next: a full three-system bench at 0.15, which both settles the naive-vs-amin
kill criterion and names the six items.

**Run 3 — full set, floor 0.15, identifier gate on** (`bench-20261010T231911`).

| | bare | naive | amin |
|---|---|---|---|
| fact accuracy | 14.5% | **99.1%** | 92.7% |
| correct refusal | 25.3% | 92.9% | 93.9% |
| hallucination | 74.7% | 7.1% | 6.1% |
| citation precision | — | — | 100% |
| routing | — | — | 95.5% |

Paired: naive beats amin on fact accuracy, **+6.4 pts, p = 0.039, significant**.
Hallucination: amin 6.1% vs naive 7.1%, 3 vs 4 discordant items, p = 1.0 —
**no measurable safety gain.** By the criterion written before the run, the
gates and verifier are not earning their cost as a safety mechanism.

Where amin's 8 losses come from:
- 3 × verifier rejected a correct draft ("could not verify") — a028, a029, a053
- 2 × evidence/identifier gate — a015, a048
- 1 × router false positive: "Vertex **diagnostic** cost" → medical (a074).
  Fixed: pattern narrowed to diagnose/diagnosis forms.
- 2 × partial answer — gave the AED 50 cap but not the AED 2/day rate (a081)

Amin's 6 hallucinations: 4 silent, 1 near-miss (u045, not caught — no
identifier in the question). u076 is a mis-graded abstention ("the passages do
not contain…") emitted as an answer; u009 is a conflict raised on an
unanswerable. Naive got 3 of the 6 right.

What amin has that naive does not: 100% citation precision, routing, 100%
Arabic pass (naive 88.9%). That is the case for the pipeline now — not safety.

Next: E19 — the same run with `--verifier off`, to measure the verifier
directly instead of inferring it.

## E19 — the verifier, measured directly

Same set, same model, floor 0.15, `--verifier off` (also includes the router
fix). `bench-20261011T021943`.

| | verifier on (E16 run 3) | verifier off |
|---|---|---|
| fact / grounded accuracy | 92.7% | **98.2%** |
| hallucination | 6.1% | 7.1% |
| citation precision | 100% | 100% |
| p50 latency | 6448 ms | 5573 ms |

Item level: 6 fixed, 1 broken. Fixed — a028, a029, a053 (verifier refused a
correct draft), a075, a081 (verifier stripped claims, leaving a fragment that
missed the fact), a074 (router fix, not the verifier). Broken — u083, one
inference stated as fact. So the verifier traded **5 correct answers for 1
prevented hallucination**. McNemar 6 vs 1, p ≈ 0.13: direction clear,
not significant on its own.

**Decision: verifier off by default**, as the E5 criterion said. Citation
precision does not depend on it. Amin now matches naive RAG on accuracy
(98.2% vs 99.1%) and hallucination (7.1% vs 7.1%) while citing every claim,
routing out-of-scope questions, and passing all Arabic items.

**What remains unsolved:** ~7% hallucination on unanswerable questions, in
both pipelines. Nothing in the current design reduces it. That is the next
real problem.

## E20 — what the 7% hallucination actually is

The 7 unanswerables amin "hallucinated" on in E19, read against the corpus:

| id | what happened | verdict |
|---|---|---|
| u045 | computed 2,000 kWh @ 23 + 500 kWh @ 28 from the slab table | correct inference — answer key wrong? |
| u072 | "short-loan items cannot be renewed" — corpus says exactly that | correct — answer key wrong? |
| u083 | "no, rooms need a minimum of 3 occupants" — corpus says exactly that | correct inference — answer key wrong? |
| u087 | commission "non-refundable" applied to a failed let | arguable over-reach |
| u065 | reasoned about accidental damage; corpus never mentions it | **real hallucination** |
| u076 | "the passages do not contain…" — an abstention, scored as an answer | **pipeline bug, fixed** |
| u009 | conflict path fired on an unanswerable question | **real bug, open** |

Fixed: amin's draft stage now uses the same abstention detector as the
baselines (`prompts.looks_like_refusal`). Its docstring already claimed this;
the code did not do it — the E7 pattern again. Added "not provide" / "not
specify" markers (naive u047, u064 were the same miss). Zero answerable items
match the new markers in either saved run.

Not changed: the eval labels. u045/u072/u083 look mislabelled, but relabelling
after seeing results is exactly how a benchmark gets tuned to its system.
Decide on the labels on their own merits, then re-run.

## E23 — distil qwen3.6:27b into Qwen3-8B (SFT) — *not yet run*

Setup (ADR-012, `docs/TRAINING.md`): 401 synthetic training documents,
3,955 graded items (2,868 answerable, 1,087 unanswerable, 545 Arabic). Split
by document, 1 in 10 held out. Teacher = the full pipeline on `qwen3.6:27b`.
Only grader-passed exchanges are kept, and gate refusals are capped at 35% of
the set. LoRA rank 16 on every layer, lr 1e-4, about 2 epochs
(`amin/train/sft.yaml`).

Measure on the 237-item bench, same retriever: the stock 8B, amin-1-sft and the
27B teacher. Report fact accuracy, hallucination and p50 latency, with paired
tests against the teacher.

**Smoke test, 2026-10-18 (teacher only, before any training).** The first
corpus put all 401 documents in one index, and the teacher passed only 2 of
21 answerable items. The cause was not the model. Sixty tenancy contracts in
one index, and a contract's rent clause never repeats its unit number, so no
retriever can tell sixty rent clauses apart. The corpus is now split into 90
households, each with at most one document of a kind in one language, each
indexed separately (`tests/test_train.py` enforces it). On every 80th item
(50 items, every family) the teacher then passed 42/50 at 7.6 s/item, so
the full teacher pass is about 8.4 h and should yield about 3,300 examples.
Of the 8 failures, 6 are "tenancy start date" refusals, where the date clause
and the unit number sit in different chunks. That is the E18 near-miss shape,
and the grader keeps those exchanges out of the training set.

Prediction, written before the run: the student matches the teacher within
the interval on fact accuracy, roughly halves latency, and its hallucination is
no better than the teacher's. SFT copies the teacher; it does not exceed it.

## E24 — DPO on the student's own failures — *not yet run*

The amin-1-sft student, sampled 4× at T=0.7 per training item. Graded failures
are paired with the teacher's reply to the byte-identical prompt.
Unanswerable and Arabic pairs are weighted ×2 each. β = 0.1, lr 5e-6
(`amin/train/dpo.yaml`).

Prediction: hallucination falls below the teacher's 7.1%. This is the only
stage that trains against failure rather than copying success. Watch correct
refusal on *answerable* items: a DPO run that buys lower hallucination with
more refusals of answerable questions is the ADR-011 trade, and gets rejected.

## Still open, in priority order

1. **E16 — attach a real local model.** `./scripts/setup_mac.sh` once Ollama is
   serving. Everything above measures the pipeline with no language model; the
   ablation's *shape* should hold but every absolute number will change.
   **The evidence floor must be re-swept** (`make sweep`) — 0.45 is tuned for an
   extractor that cannot abstain, and a real model abstains on its own, so the
   floor should come down. Expectation to test: Amin's fact accuracy > 0.80 and
   hallucination < 0.10; naive RAG's hallucination stays high. If naive's
   hallucination collapses too, the verifier is not earning its latency and
   should be cut.
2. **E17 — typed quantities in conflict detection.** The E11 limitation: compare
   `AED 3,900` with `AED 4,100` as currencies, and refuse to compare a currency
   with a duration. Removes the false-positive class that the coverage band is
   currently suppressing by brute force.
3. **E18 — the near-miss hole.** Items tagged `near-miss` (FR-550 vs FR-440,
   V16 vs V14, Freedom 300 vs 150) are where lexical coverage cannot help: the
   distinctive terms *are* present, only the model number differs. Candidate
   fixes: an entity-agreement check on the retrieved chunk, or trusting the
   model's own abstention more. This is the known design hole, and the
   `near-miss` tag makes its cost visible in every run.
4. **E19 — LLM verifier vs lexical** (`AMIN_VERIFIER=llm`). Should catch
   paraphrase and negation failures. Measure latency, not just accuracy: it is
   one small-model call per sentence.
5. **E20 — chunk size sweep** (`chunk_chars` 600 / 900 / 1400). Chunk
   boundaries decide whether a citation points at the right clause.
6. **E21 — grow the conflict slice.** Six items is a capability check, not a
   rate. 30+ would make conflict handling a measurable metric; it needs more
   genuinely-disagreeing document pairs in the corpus.
7. **E22 — a frontier row.** `amin/hosted.py` is ready; needs an API key. The
   corpus is synthetic, so no hosted model has it memorised — which makes this a
   fair test of grounding rather than of recall, and the right comparison is
   against `naive` with the same retriever, not against the bare API.
