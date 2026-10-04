# Architecture

```
                     ┌──────────────────────────────────────┐
  question  ───────▶ │ 1  COVENANT: scope check             │──▶ refuse + refer
                     │    policy.yaml → medical/legal/money │    (before retrieval)
                     └──────────────────┬───────────────────┘
                                        ▼
                     ┌──────────────────────────────────────┐
                     │ 2  RETRIEVE                          │
                     │    dense (embeddings)  ┐              │
                     │    lexical (FTS5 BM25) ┘ RRF fusion   │
                     │    × IDF coverage × source tier       │
                     └──────────────────┬───────────────────┘
                                        ▼
                     ┌──────────────────────────────────────┐
                     │ 3  EVIDENCE GATE                     │──▶ refuse
                     │    max coverage ≥ evidence_floor     │    "no source for that"
                     └──────────────────┬───────────────────┘
                                        ▼
                     ┌──────────────────────────────────────┐
                     │ 4  GENERATE                          │──▶ model says NO_EVIDENCE
                     │    passages only, tag every sentence │    → refuse
                     └──────────────────┬───────────────────┘
                                        ▼
                     ┌──────────────────────────────────────┐
                     │ 5  VERIFY each sentence              │
                     │    vs the chunk it actually cited    │
                     │    strict on numbers; llm or lexical │
                     └──────────────────┬───────────────────┘
                                        ▼
                     ┌──────────────────────────────────────┐
                     │ 6  ASSEMBLE                          │──▶ refuse if citation
                     │    drop UNSUPPORTED, label UNCITED   │    precision < floor
                     └──────────────────┬───────────────────┘
                                        ▼
                              answer + quoted sources
```

## Why these pieces

**SQLite, not a vector database.** The corpus is 10^3–10^5 chunks. At that scale
a brute-force numpy dot product beats an ANN index and loses no recall, and
SQLite with FTS5 ships inside Python — no service to keep running on a laptop
that closes its lid. Swap in sqlite-vec or FAISS when the vectors stop fitting
in memory, not before.

**RRF, not weighted-sum hybrid.** Reciprocal Rank Fusion needs no score
normalisation between the dense and lexical arms, which is where naive hybrids
break: cosine similarities and BM25 scores are not on comparable scales and the
weights end up tuned to one corpus. The cost of RRF is that its output carries
no absolute relevance signal — see `docs/EXPERIMENTS.md` E2 for the bug that
caused and how coverage fixed it.

**Structure-aware chunking.** Chunks are split on headings and packed by
sentence, never mid-sentence, and a chunk carries exactly one heading. A chunk
that straddles two contract clauses produces a citation pointing at the wrong
clause, which is worse than no citation: it looks authoritative and is wrong.

**Claims, not text.** `Answer` is a list of `Claim`s, each with its citations and
a verifier verdict. The API returns that structure rather than a string, so a
client can render sourced and unsourced material differently without re-parsing
prose. This is the single design choice everything else depends on.

**The provider interface.** Three implementations — Ollama, MLX, and `echo`.
Nothing above `providers.py` knows which is running. `echo` is a deterministic
lexical extractor with no model, which is how 38 behaviour tests and the full
eval harness run offline in under a second.

## Degradation, deliberately

| failure | behaviour |
|---|---|
| embedding model missing | dense arm returns nothing, lexical retrieval still answers |
| verifier LLM unreachable | falls back to the lexical verifier, notes it in the claim |
| index built with a different embedding model | explicit error naming the fix, not a silent dimension crash |
| model returns unparseable verdict | falls back to lexical, records the raw reply |

Each of these is a real failure mode of a laptop deployment. None of them should
turn into a wrong answer, which is why every one degrades toward refusing rather
than toward guessing.

## Not built yet

Per-person memory and permissions (phase 3), the web and phone clients (phase 4),
LoRA fine-tuning (phase 5), voice and tools (phase 6). See the build plan in the
project notes. The order is deliberate: nothing above matters if the answers
cannot be trusted.
