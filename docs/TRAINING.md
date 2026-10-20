# Training Amin's own model

Amin's own model is Qwen3-8B (LoRA on bf16, shipped at 8-bit), post-trained on this Mac to do one job well:
read the passages it is given, cite them, and say so when they don't hold the
answer. The why is in ADR-012; this page is the runbook.

Facts never go into the weights. The model learns behaviour from synthetic
documents; your real documents stay in the index, where they can be cited,
added and deleted.

## Steps

| step | command | what it does | time on an M3 Max, 64 GB |
|---|---|---|---|
| 1 | `make train-setup` | installs MLX, downloads Qwen3-8B bf16 (~16 GB) to `data/models/`; needs ~60 GB free in all | 10–30 min |
| 2 | `make train-corpus` | writes 401 synthetic documents + 3,955 graded questions, indexes them separately from the eval index | ~5 min |
| 3 | `make distill` | the 27B answers every question through the real pipeline; only grader-passed answers are kept | 6–10 h, resumable |
| 4 | `make train-sft` | LoRA distillation into the 8B, fused, then an 8-bit copy for serving | 2–4 h |
| 5 | `make serve-student` + `make bench-student` | serves the student and runs the 237-item bench | ~30 min |
| 6 | `make preferences` (student still serving) | samples the student, pairs its failures with the teacher's answers | 4–8 h, resumable |
| 7 | `make train-dpo` | preference tuning, fused, quantized to `data/models/amin-1` (8-bit; `Q_BITS=4` for speed) | 1–3 h |
| 8 | `make serve-student MODEL=data/models/amin-1` + `make bench-student` | the ship gate | ~30 min |

Times are estimates; record real ones in `docs/EXPERIMENTS.md` (E23, E24).
Steps 3 and 6 append to `data/train/*.jsonl` and skip finished items, so
stopping and re-running loses nothing. Keep the Mac on power;
`caffeinate` is already in the targets.

Before the long runs, smoke-test the whole chain in minutes:

```bash
uv run python -m amin.train.distill run --limit 30
```

```bash
uv run python -m amin.train.distill export
```

```bash
uv run mlx_lm.lora -c amin/train/sft.yaml --iters 20
```

## The ship gate

amin-1 replaces `qwen3.6:27b` only if, on the 237-item bench:

- hallucination ≤ 7.1%,
- fact accuracy is not significantly below the teacher's (paired McNemar),
- p50 latency ≤ 2.5 s.

If it misses any one of the three, it doesn't ship. Log the run anyway; a
failed adapter tells you what to fix in the data.

## Using it

```bash
make serve-student MODEL=data/models/amin-1
```

Then, in `.env`:

```
AMIN_PROVIDER=mlx
AMIN_MLX_MODEL=amin-1
```

`amin doctor` checks both servers. Ollama is still needed, because retrieval
embeddings come from `nomic-embed-text`. `/health` reports the model name.

## Next rounds

Once Phase 0 of the app plan has logged real questions, the ones Amin got
wrong become new preference pairs (step 6 onward) for amin-2. Never add an eval
item to the training data. If a failure is worth testing, write a new eval item
for it *and* a different training item.

## Round 2 (amin-2): fix accuracy without losing the trap gains

What round 1 taught (EXPERIMENTS E23–E26):

- **SFT alone (run 2)** matches the 27B on accuracy but falls for 35% of
  adjacent-fact traps.
- **SFT + DPO (amin-1)** fixes the traps but refuses 17% of what it should
  answer.
- **Choosing the checkpoint by DPO pair accuracy** was the mistake: that
  metric hit 100% at step 200 and said nothing after.

The plan:

1. **A selection slice, k.** About 160 items written in their own session,
   never trained on and never used for anything but choosing checkpoints:

   | items | kind |
   |---|---|
   | 40 | adjacent-fact traps |
   | 40 | trap siblings |
   | 40 | fresh answerables |
   | 20 | general-knowledge |
   | 20 | personal-detail "decline" |

   Slice j stays the final, one-time test.
2. **SFT keeps general answering.** Add teacher answers under
   `GENERAL_SYSTEM` (general questions, plus personal questions it must
   decline) to the grounded set, so the LoRA does not erode what the base
   already knows. Run 2's recipe is otherwise unchanged.
3. **DPO leans towards answering.** Answer-side balance pairs (sibling
   answer chosen, refusal rejected) at 3× the refusal pairs, not 1×. In the
   app a wrong refusal now costs a citation, because the question falls
   through to a general answer. That is less than before, but it still costs.
4. **Select on slice k, in hybrid mode.** Benchmark every 25-step checkpoint
   and keep the best trust score whose answerable accuracy is not
   significantly below the teacher's. Only that one checkpoint then runs on
   slice j.

Afterwards, to make it stronger:

- **A bigger base.** Qwen3-14B fits LoRA training in bf16 on 64 GB. DPO with
  a bf16 reference will not, so use ORPO (no reference model) or an 8-bit
  reference.
- **Arabic.** More Arabic training documents and a larger Arabic slice. It is
  the thinnest slice today.
