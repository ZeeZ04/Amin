# Experiment log

Every change that moves a metric gets a row. A change with no measurement is
not an improvement, it is a guess. Dates are the day the experiment was run.

Harness: `amin eval`, 30 items (17 answerable / 8 unanswerable / 5 out-of-scope).
Unless stated, provider is `echo` (no language model) with the lexical verifier,
so these numbers measure the **pipeline**, not model quality.

| id | date | change | g_acc | refusal | halluc | cite_prec | verdict |
|---|---|---|---|---|---|---|---|
| E0 | 2026-10-04 | first end-to-end run | 0.412 | 0.500 | 0.500 | 1.000 | baseline |
| E1 | 2026-10-04 | fix: echo provider was swallowing the question block into the last passage | — | — | — | — | bug, not a result |
| E2 | 2026-10-04 | **evidence gate moved from RRF score to IDF-weighted query coverage** | 0.412 | 0.500 | 0.500 | 1.000 | enabled E3 |
| E3 | 2026-10-04 | `evidence_floor` swept 0.00 → 0.70, default set to 0.45 | 0.235 | 0.875 | **0.125** | 1.000 | **adopted** |

---

## E1 — the bug that made the first baseline meaningless

The `echo` provider parsed passages with a regex ending in `\Z`, so the final
passage's body absorbed the `<question>` block that followed it. Overlap against
the question was therefore 1.0 for the last passage every time, and the provider
always picked it regardless of content. Two tests failed in a way that looked
like a retrieval problem and was not.

Lesson worth keeping: when a test fails, check the test harness before changing
the system. I nearly re-tuned retrieval to fix a bug in the fake model.

## E2 — the evidence gate was decorative

The refusal gate compared the top fused retrieval score against a floor. It
could never have worked. Reciprocal Rank Fusion produces scores from *ranks*:

```
score(top hit) ≈ 1/(k+1) = 1/61 ≈ 0.0164
```

for a perfect match and for pure noise alike. Observed, across two questions:

```
"part number for the fridge water filter cartridge"  top score 0.03643
"what is the capital of Burkina Faso"                top score 0.03614
```

A 0.8% difference between a question the corpus answers precisely and one it
knows nothing about. Any floor placed there either refuses everything or refuses
nothing. The system was answering "what is the capital of Burkina Faso?" from
the refrigerator manual's warranty section.

**Replacement.** Gate on IDF-weighted coverage: of the question's distinctive
terms (content words, function words removed), what share does the best
retrieved chunk actually contain, weighted so rare terms dominate? A term the
corpus has never seen gets the maximum weight — otherwise a question about
something absent scores well on the terms that happen to overlap.

```
coverage(q, c) = Σ idf(t) for t in content(q) ∩ content(c)
                 ─────────────────────────────────────────
                 Σ idf(t) for t in content(q)
```

Burkina Faso → coverage 0.00 (none of `capital`, `burkina`, `faso` is in the
corpus). Water filter → coverage 0.79. That is a signal you can put a floor on.

Coverage also went into ranking as a multiplier, `score × (1 + 1.5·cov)`, because
RRF is nearly flat across the candidate set and coverage reorders it usefully.

## E3 — choosing the floor, and why `overall_pass` is the wrong objective

Sweep of `evidence_floor` (echo provider, lexical verifier, 30 items):

| floor | grounded acc | correct refusal | hallucination | overall_pass |
|---|---|---|---|---|
| 0.00 | 0.529 | 0.000 | 1.000 | 0.467 |
| 0.15 | 0.529 | 0.125 | 0.875 | 0.500 |
| 0.25 | 0.529 | 0.250 | 0.750 | 0.533 |
| 0.34 | 0.412 | 0.500 | 0.500 | 0.533 |
| 0.38 | 0.412 | 0.750 | 0.250 | 0.533 |
| 0.45 | 0.235 | 0.875 | 0.125 | 0.533 |
| 0.55 | 0.176 | 0.875 | 0.125 | 0.500 |
| 0.70 | 0.118 | 0.875 | 0.125 | 0.467 |

`overall_pass` is **flat at 0.533 from 0.25 to 0.45** while the system's actual
behaviour changes completely underneath it — from hallucinating on 75% of
unanswerable questions to hallucinating on 12.5%. A single aggregate pass rate
is useless for this decision, and if this project reported only that number it
would look identical at both ends of a range where one end is dangerous.

So the objective has to be stated. For an assistant whose users trust it *more*
because it is home-built, a confident wrong answer costs more than an
unnecessary refusal. Weighting a hallucination at 3× a missed answer:

```
trust = grounded_accuracy − 3 × hallucination_rate
```

| floor | 0.25 | 0.34 | 0.38 | 0.40 | 0.45 | 0.50 |
|---|---|---|---|---|---|---|
| trust | −1.721 | −1.088 | −0.338 | −0.397 | **−0.140** | −0.140 |

**Adopted: 0.45.** The 3× weight is a judgement, not a measurement, and it is
written down here so it can be argued with rather than buried in a constant.

Note the absolute numbers are all negative. With no language model, every
question the extractor can answer is one it answers badly. That is the floor
this project starts from, not the ceiling.

---

## Next experiments, in order

1. **E4 — attach Qwen3.6-27B** (`amin eval --provider ollama`). The model's own
   `NO_EVIDENCE` abstention should do most of the refusing, which means the
   evidence floor can almost certainly come *down* from 0.45 without
   hallucination rising. **The floor must be re-swept after this; the current
   value is tuned for an extractor, not a model.** Expectation to test:
   grounded accuracy > 0.80, hallucination < 0.10.
2. **E5 — LLM verifier vs lexical** (`AMIN_VERIFIER=llm`). Should catch
   paraphrase and negation failures the lexical check misses. Cost: one
   small-model call per sentence. Measure the latency, not just the accuracy.
3. **E6 — chunk size sweep** (`chunk_chars` 600 / 900 / 1400). Chunk boundaries
   determine whether a citation points at the right clause; a1–a17 cite specific
   clauses, so this should move grounded accuracy measurably.
4. **E7 — item `u01` (FR-550 vs FR-440)**. Lexical coverage cannot distinguish
   two model numbers from the same product family. Candidate fixes: an entity
   check on the retrieved chunk, or trusting the model's abstention more. This
   is the honest known hole in the design.
5. **E8 — the conflict path.** The two handbook versions disagree on coursework
   weighting and no eval item tests it yet. Write the items, then measure.
6. **E9 — Arabic.** Only two items (a17, u07) are in Arabic. Expand to ~15
   before claiming anything bilingual works.
