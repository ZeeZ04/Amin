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

Amin publishes its own error rate, because a tool named "trustworthy" should be
the one tool that does.

| metric | no-model baseline | direction |
|---|---|---|
| grounded accuracy | 0.235 | higher better |
| correct refusal | 0.875 | higher better |
| **hallucination rate** | **0.125** | **lower better** |
| citation precision | 1.000 | higher better |
| routing accuracy | 1.000 | higher better |

> **Read that table carefully.** These are the numbers for the `echo` provider —
> a deterministic lexical extractor with **no language model at all**, which
> exists so the whole pipeline is testable in CI offline. They measure the
> *plumbing*, not the system's quality, and grounded accuracy of 0.235 is
> genuinely bad. They are published anyway, because a baseline you are
> embarrassed by is the only kind that proves the harness works.
>
> Attaching a real model (`--provider ollama`) is the next experiment, and
> `docs/EXPERIMENTS.md` is where its numbers go. Nothing in this README will
> claim an improvement that the harness has not measured.

Reproduce: `make eval` (no model needed) or `amin eval --provider ollama`.

---

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
| `amin eval [--failures]` | run the eval set, print the metrics table |
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
data/corpus/     six synthetic source documents, exact ground truth
data/eval/       30-item eval set: 17 answerable, 8 unanswerable, 5 out-of-scope
docs/            ARCHITECTURE · EVAL · EXPERIMENTS · DECISIONS
private/         gitignored. Real documents go here and never into a commit.
```

## The data wall

`private/` and `data/index/` are gitignored. The committed corpus is six
**synthetic** documents — a tenancy contract, an appliance manual, two versions
of a module handbook, an insurance schedule and an Arabic summary — written for
this repository. That gives two things a scraped corpus cannot: ground truth
that is exact by construction, and a repo anyone can clone and run without
inheriting someone's private paperwork.

The two handbook versions disagree with each other on coursework weighting, on
purpose. That is what the conflict-detection path is tested against.

## Limits, stated plainly

- A 27B model is far from frontier on hard multi-step reasoning. It is close
  enough on retrieval-grounded question answering, which is the only thing Amin
  does. Pushing it outside that lane is how you make it look broken.
- Coverage gating is lexical. It cannot tell that "FR-550" is a different
  appliance from "FR-440" — eval item `u01` is the known failure, and it is in
  the set precisely so the number reflects it.
- The verifier's LLM backend is one small-model call per sentence. That is the
  dominant latency cost and the obvious thing to batch.
- No fine-tuning yet, by design. See `docs/DECISIONS.md` ADR-004.

## License

MIT. Built by Abdul Azeez.
