# R4: Stronger PC ("Jarvis") model (2026-10-29)

Caveat: most numbers below come from the vendors' model cards as relayed by third-party sites. The search tool could not open the HF cards directly. **Verify each licence file and score on the HF card before committing.**

## 1. Base candidates (64 GB, commercial)
| Model | Size / memory (4-bit) | Coding | Licence |
|---|---|---|---|
| Qwen3.6-27B (dense) | ~16 GB | SWE-bench Verified 77.2, LiveCodeBench ~83.9 (BenchLM), Terminal-Bench 2.0 59.3 | Apache 2.0 per two secondary sources; one disputes it. Check the card |
| Qwen3.6-35B-A3B (MoE) | ~20 GB, ~100+ tok/s on M3 Ultra-class | SWE-bench V 73.4, LCB v6 80.4 | same |
| Gemma 4 31B / 26B-A4B | ~18 / ~15 GB | LCB v6 80.0 / 77.1 | Apache 2.0 (moved from Gemma Terms) per several blogs |
| Devstral Small 2 (24B) | ~14 GB | SWE-bench V 68.0 (one table 65.8) | Apache 2.0. Devstral 2 123B is modified MIT with a revenue cap: avoid |
| GLM-4.7-Flash (30B-A3B) | ~18 GB | scores unverified | MIT per secondary sources |

Sources: [Qwen3.6-27B card](https://huggingface.co/Qwen/Qwen3.6-27B), [BenchLM compare](https://benchlm.ai/md/compare/qwen3-6-27b-vs-qwen3-6-35b-a3b.md), [Devstral Small 2](https://www.llmreference.com/model/devstral-small-2), [Gemma 4 guide](https://codersera.com/blog/gemma-4-complete-guide-2026/), [GLM-4.7-Flash](https://www.verdent.ai/guides/model/glm-4-7-flash). HumanEval+ is saturated and was not found for these. Skip it.

**Tokenizers (E32):** Qwen3 gave 0.79 chars/token on Malayalam. Check Qwen3.6 with the same E32 script before trusting it; I did not find a figure. Gemma 4 gave 2.94, which is about 3.7x cheaper and faster for Malayalam and, I infer, better for Arabic. Gemma 4 31B is the only large candidate that is also on Amin's existing tokenizer and chat template, so edge-2's SFT/DPO data transfers unchanged. Qwen is stronger at code. The code benchmarks are roughly equal (LCB 80 vs 80-84); Qwen leads on agentic SWE-bench.

**Training fit:** MLX LoRA on a 27-31B dense model in 4-bit (QLoRA) should fit in 64 GB with short sequences and gradient checkpointing; this was not verified by a source. The MoE 35B-A3B reportedly trains about 3x faster per step than the dense 27B but needs max seq length 128 in one tool ([mlx-optiq](https://mlx-optiq.pages.dev/docs/qwen3.6)). That is community evidence only. Treat the MoE as an inference-only model unless a pilot works.

## 2. Data (commercial-safe vs flagged)
- **nvidia/OpenCodeInstruct**: CC BY 4.0, card says commercial OK; per-row `license` field and generator models (Qwen family) mean attribution and a row filter are needed ([card](https://huggingface.co/datasets/nvidia/OpenCodeInstruct/blob/main/README.md)). Use, with a NOTICE file.
- **Magicoder OSS-Instruct 75K**: generated with gpt-3.5-turbo, so OpenAI terms apply; sources conflict on the dataset licence. **Flag: legal check before use. Default is to skip.**
- Prefer permissive generation: have the local Qwen3.6-27B or Devstral (Apache) write the SFT data. This is the same recipe as the 27B-teacher distillation.
- **Docs retrieval pack:** Python docs are PSF licence (permissive, keep notices). PyTorch docs are BSD-3 (I believe, not verified). MLX / mlx-lm are MIT. Confirm each repo's LICENSE file. These go in the **index** (citable), not in weights (ADR-015).
- Non-commercial or ToS-risky: anything distilled from GPT/Claude/Gemini APIs, and CC-BY-NC sets. Exclude.

## 3. Recipe recommendation
1. **Route, don't replace.** Keep edge-2 (E4B) as the fast default. Add a "pc-code" route in `amin/classify.py`, where the single-pass router already outputs the intent. Code/ML intent goes to the big model; everything else stays on edge-2. Cost: about 16-20 GB resident when active, loaded on demand.
2. **Base: start with Gemma 4 31B** (same tokenizer and template, Malayalam/Arabic safe, LCB 80). Run a Qwen3.6-27B bake-off on a coding-only route, since it has the best SWE-bench.
3. **RAG over Python/PyTorch/MLX docs** first. It is cheap, citable and deletable, and fits Amin's citation-per-claim rule.
4. **LoRA only for behaviour:** Amin's grounded SFT plus a small (about 5-10k) coding mix with a replay of existing behaviour data, at low rank and low LR to avoid forgetting. Then DPO.
Do not fine-tune on facts (ADR-015).

## 4. Evaluation and gate protection
- Local runs: LiveCodeBench (a recent date window, to limit contamination), EvalPlus HumanEval+/MBPP+ as a sanity check, BigCodeBench-Instruct, and a small SWE-bench Verified Lite subset only if a harness is practical. Add 50 Amin-written ML-explanation prompts with citation checks against the doc pack.
- **ADR-012 gate:** run the full existing gate unchanged on the PC model for every non-code route, plus Malayalam/Arabic probes. A new model ships only if it matches edge-2 on the gate. Since the router keeps non-code traffic on edge-2, the gate only has to prove the router (misrouted-prompt rate, and a Malayalam code question) does not regress.

## Open items
Verify licences on the HF cards; measure Qwen3.6 Malayalam chars/token; pilot a QLoRA step on Gemma 4 31B and record peak memory.
