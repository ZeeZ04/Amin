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

## Still open, in priority order

1. **E7 — attach a real local model.** `ollama pull qwen3.6:27b`, then
   `amin bench --provider ollama`. Everything above measures the pipeline with
   no language model; the ablation's *shape* should hold but every absolute
   number will change. **The evidence floor must be re-swept** (`make sweep`) —
   0.45 is tuned for an extractor that cannot abstain, and a real model abstains
   on its own, so the floor should come down. Expectation to test: Amin's fact
   accuracy > 0.80 and hallucination < 0.10; naive RAG's hallucination stays
   high. If naive's hallucination collapses too, the verifier is not earning its
   latency and should be cut.
2. **E8 — grow the unanswerable slice to 97+ items.** The headline metric
   currently has a ±15pp interval. Nothing else on this list matters as much.
3. **E9 — LLM verifier vs lexical** (`AMIN_VERIFIER=llm`). Should catch
   paraphrase and negation failures. Measure latency, not just accuracy: it is
   one small-model call per sentence.
4. **E10 — chunk size sweep** (`chunk_chars` 600 / 900 / 1400). Chunk
   boundaries decide whether a citation points at the right clause.
5. **E11 — the near-miss hole.** Items tagged `near-miss` (FR-550 vs FR-440,
   V16 vs V14, Freedom 300 vs 150) are where lexical coverage cannot help: the
   distinctive terms *are* present, only the model number differs. Candidate
   fixes: an entity-agreement check on the retrieved chunk, or trusting the
   model's own abstention more. This is the known design hole.
6. **E12 — the conflict path.** The two handbook versions disagree on coursework
   weighting and no eval item tests it. Write the items, then measure.
7. **E13 — a frontier row.** `amin/hosted.py` is ready; needs an API key. Note
   the corpus is synthetic, so no hosted model has it memorised — which makes
   this a fair test of grounding rather than of recall, and the right comparison
   is against `naive` with the same retriever, not against the bare API.
