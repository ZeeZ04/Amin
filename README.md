# Amin

A locally-run assistant that answers only from documents you have approved, cites
the passage behind every sentence it says, and refuses out loud when it has no
source. `أمين` means trustworthy.

The thesis of this project is that **truthfulness is not a property of training
data — it is a property of inference**. A model trained exclusively on true
statements still fabricates fluently, because pretraining teaches next-token
prediction, not fact storage. So Amin spends nothing on corpus purity and
everything on four things: retrieve, cite, verify, refuse.

Everything runs on one laptop. No API keys, no services, nothing leaves the machine.

---

## Measured behaviour

The claim is not that a 27B local model beats a frontier model. It is that
**a small model inside this pipeline refuses when it should, and a conventional
RAG pipeline does not** — measured, with intervals, on identical items.

Three systems, same retriever, same model, same 237-item eval set, same grader:

| metric | bare | naive RAG | **Amin** | direction |
|---|---|---|---|---|
| fact accuracy | 0.0% ±2% | **30.0% ±8%** | 22.7% ±8% | higher |
| grounded accuracy | — | — | **22.7% ±8%** | higher |
| correct refusal | 100.0% ±2% | 1.0% ±3% | 70.7% ±9% | higher |
| **hallucination rate** | 0.0% ±2% | **99.0% ±3%** | **29.3% ±9%** | **lower** |
| citation precision | — | — | **100.0%** | higher |
| routing accuracy | — | — | **95.5% ±10%** | higher |
| conflict handling | 0/6 | 0/6 | **5/6** | higher |

Paired McNemar tests on the same items, sliced by question kind:

| comparison | metric | delta (95% CI) | p |
|---|---|---|---|
| Amin vs naive | fact accuracy | **−7.3%** [−12.7%, −2.7%] | 0.008 |
| Amin vs naive | correct refusal | **+69.7%** [+60.6%, +78.8%] | <0.0001 |

**Amin trades 7 points of fact accuracy for 70 points of correct refusal.** Both
significant, neither interval crossing zero. That trade is the thesis, stated as
two numbers — not dominance, which the data does not support.

> **Read the caveats, they are not decoration.**
>
> 1. These are `echo`-provider numbers — a deterministic lexical extractor with
>    **no language model at all**, so the pipeline is testable offline in CI.
>    They measure plumbing, not quality. 23% fact accuracy is bad.
>    `docs/EXPERIMENTS.md` E16 is where real-model numbers go.
> 2. `bare` scoring 0% hallucination is not a win — with no passages it abstains
>    on everything. A system that always says "I don't know" has a perfect
>    refusal rate and no use. That is why refusal is never reported without
>    accuracy beside it.
> 3. Conflict handling is 6 items: a capability check, not a rate. It is
>    reported as passed/total for exactly that reason.

Reproduce all of it with no model and no network:

```bash
amin ingest --reset --provider echo
amin bench --provider echo --verifier lexical
```

## Quickstart

```bash
git clone <this repo> && cd Amin
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 1. Works immediately, no model, no download:
amin ingest --reset --provider echo
amin eval --provider echo

# 2. With a real local model:
brew install ollama && ollama serve          # separate terminal
ollama pull qwen3.6:27b                      # ~18 GB, the answer model
ollama pull qwen3:8b                         # ~5 GB, verifier + query rewriting
ollama pull nomic-embed-text                 # ~275 MB, embeddings
amin doctor                                  # confirms all three are present
amin ingest --reset
amin ask "How much notice must I give before the tenancy expires?"
amin eval
```

`amin ask` on the sample corpus:

```
╭─ answer ─────────────────────────────────────────────────────────────╮
│ Either party must give not less than 90 days written notice before   │
│ expiry of their intention not to renew [tenancy-agreement]           │
╰──────────────────────────────────────────────────────────────────────╯
sources
  tenancy-agreement  Notice and renewal  primary  Clause 7.1 — Either party…
answered · 412 ms · ollama:qwen3.6:27b · citation precision 100%
```

Ask it something the corpus does not cover and it says so:

```
╭─ no evidence ────────────────────────────────────────────────────────╮
│ I don't have a source for that in my library, so I won't guess.      │
│ Add a document that covers it and ask me again.                      │
╰──────────────────────────────────────────────────────────────────────╯
```

---

## How it works

```
question
  ├─ 1. covenant scope check ──── refuse BEFORE retrieving (medical/legal/financial)
  ├─ 2. hybrid retrieve ───────── dense + BM25, RRF-fused, IDF coverage, tier-adjusted
  ├─ 3. evidence gate ─────────── refuse rather than answer from nothing
  ├─ 4. generate ──────────────── answer only from passages, tag every sentence
  ├─ 5. verify each sentence ──── against the chunk it actually cited
  └─ 6. assemble or refuse ────── drop fabrications, label uncited reasoning
```

Three design decisions worth defending in an interview:

**The refusal gates sit on either side of generation.** Most RAG systems generate
first and bolt a confidence score on afterwards, which gives the model a chance
to be fluent about nothing. Here it never gets that chance.

**The evidence gate reads IDF-weighted query coverage, not the retrieval score.**
RRF scores are rank-derived: the top hit scores ~1/(k+1) whether it is a perfect
match or pure noise. Gating on them is decorative. Coverage — *how much of the
question's distinctive vocabulary does any retrieved chunk actually contain* — is
absolute, and it is what makes "what is the capital of Burkina Faso?" a refusal
instead of a confident answer sourced from a refrigerator manual. This bug was
real, it shipped, and the eval harness caught it; see `docs/EXPERIMENTS.md` E2.

**Disagreement is detected in code, before generation.** Retrieve two sources
that contradict each other, hand both to a model, and it will pick one and cite
it — a silently resolved contradiction wearing a citation. Relying on the model
to announce the conflict is unverifiable and fails quietly, so `conflict.py`
compares the numbers each source puts next to the question's own terms, and only
between documents declared to be about the same subject. `docs/EXPERIMENTS.md`
E7–E11 is how that was built and why the obvious version of it does not work.

**A sentence that cites a passage which does not support it is deleted, not
flagged.** A fabrication with a correct-looking footnote is the worst output this
system can produce — worse than no answer, because the footnote is what buys the
reader's trust. Uncited model reasoning is kept but rendered differently, so the
reader can always tell the two apart.

---

## Commands

| command | what it does |
|---|---|
| `amin ingest [path] [--private] [--reset]` | load → chunk → embed → index |
| `amin ask "…" [--debug] [--retrieved]` | one grounded answer with sources |
| `amin eval [--failures] [--system amin\|naive\|bare]` | run the eval set, print metrics with CIs |
| `amin bench [--systems bare,naive,amin]` | the ablation: compare systems with paired tests |
| `make build-eval` | regenerate and validate the eval set |
| `amin stats` | what is in the index |
| `amin doctor` | is the model server up, are the models pulled |
| `make serve` | FastAPI on :8000 — `/ask`, `/chunks/{id}`, `/metrics` |

## Layout

```
amin/
  schema.py      typed objects; an answer is a list of checked claims, not a blob
  providers.py   Ollama · MLX · echo (offline, deterministic, for CI)
  ingest.py      loaders + structure-aware chunking (chunks never straddle headings)
  store.py       SQLite + FTS5 + numpy vectors, RRF fusion, IDF coverage
  verifier.py    sentence-level citation checking; strict on numbers
  covenant.py    the trust rules, loaded from policy.yaml
  answer.py      the pipeline above
  evaluate.py    the eval harness and its metrics
  api.py         FastAPI
  cli.py         typer
  conflict.py    structural disagreement detection, before generation
  stats.py       Wilson intervals, McNemar paired tests, paired bootstrap
  systems.py     the three comparable systems: bare, naive RAG, amin
  benchmark.py   multi-system runner, significance tests, markdown report
  hosted.py      OpenAI-compatible + Anthropic adapters with cost accounting
data/corpus/     14 synthetic source documents, exact ground truth
data/eval/       237 items: 110 answerable, 99 unanswerable, 22 out-of-scope, 6 conflict
docs/            ARCHITECTURE · EVAL · EXPERIMENTS · DECISIONS
private/         gitignored. Real documents go here and never into a commit.
```

## The data wall

`private/` and `data/index/` are gitignored. The committed corpus is thirteen
**synthetic** documents — a tenancy contract, an appliance manual, two versions
of a module handbook, an insurance schedule, an electricity tariff, a phone
plan, a laptop warranty, library regulations, a fee schedule and three Arabic
summaries — written for this repository. That gives two things a scraped corpus cannot: ground truth
that is exact by construction, and a repo anyone can clone and run without
inheriting someone's private paperwork.

The two handbook versions disagree with each other on coursework weighting, on
purpose. That is what the conflict-detection path is tested against.

## Comparing against other models

The corpus is synthetic, so no hosted model has it memorised. That makes this
eval set a test of **grounding**, not of recall — which is the only fair way to
compare a small local pipeline against a large API, and why the honest
comparison is Amin against *the same retriever with a different generator*,
never against a bare API call.

`amin/hosted.py` has OpenAI-compatible and Anthropic adapters with token and
cost accounting, so adding a hosted row is a key and a flag:

```bash
AMIN_PROVIDER=openai AMIN_ANSWER_MODEL=gpt-4o-mini OPENAI_API_KEY=... amin bench
```

Embeddings deliberately stay local even on a hosted run: swapping the retriever
and the generator at once would change two variables and measure neither.

## Amin's own model

Amin can run on its own post-trained model, Qwen3-8B distilled from the 27B
teacher and then preference-tuned on its own graded failures. All of it runs
on this Mac with MLX. Only behaviour goes into the weights (citing, refusing,
Arabic register); your documents stay in the index. A trained model ships
only if it passes the bench gate in ADR-012. The runbook, with timings, is in
[`docs/TRAINING.md`](docs/TRAINING.md).

amin-1 (Qwen3-8B → SFT → DPO, 8-bit) passed the gate on 2026-10-20, on the same
237 items, retriever and pipeline:

| | fact accuracy | hallucination | p50 latency |
|---|---|---|---|
| qwen3.6:27b (teacher) | 98.2% ±3% | 6.1% ±5% | 6.7 s |
| **amin-1** | 94.5% ±4% | **1.0% ±3%** | **1.3 s** |

Neither difference is significant on its own (p=0.22 and p=0.06, paired). The
hallucination gain comes from training aimed at a failure category this
benchmark exposed, so it awaits a fresh eval slice; see EXPERIMENTS E24.

## Limits, stated plainly

- A 27B model is far from frontier on hard multi-step reasoning. It is close
  enough on retrieval-grounded question answering, which is the only thing Amin
  does. Pushing it outside that lane is how you make it look broken.
- Coverage gating is lexical. It cannot tell that "FR-550" is a different
  appliance from "FR-440": the distinctive terms are all present and only the
  model number differs. Items tagged `near-miss` are in the set precisely so the
  number reflects this, and it is the known design hole (EXPERIMENTS E11).
- Conflict detection compares numbers in answer position, not *typed*
  quantities, so two sections of one subject discussing different quantities can
  look contradictory. Currently suppressed by a tuned coverage band rather than
  solved (EXPERIMENTS E11).
- Document titles are deliberately not indexed. Indexing them raises fact
  accuracy by 2.7pp and hallucination by 13.1pp, because every chunk inherits
  the document's name and the evidence gate stops working (EXPERIMENTS E12).
- No real-model numbers exist yet. Every figure above is from the no-model
  provider. The ablation's *shape* should survive attaching a model; the
  absolute numbers will not.
- The verifier's LLM backend is one small-model call per sentence. That is the
  dominant latency cost and the obvious thing to batch.
- No fine-tuning yet, by design. See `docs/DECISIONS.md` ADR-004.

## License

MIT. Built by Abdul Azeez.
