# R1: running edge-2 (Gemma 4 E4B) on device

Status of evidence: web search only, 2026-10-29. Items marked VERIFY were not confirmed from primary sources.

## 1. Swift runtime
- Package: `https://github.com/ml-explore/mlx-swift-lm`, README snippet `.upToNextMinor(from: "3.32.3")` (main = 3.x). Products: `MLXLLM`, `MLXLMCommon`, `MLXEmbedders`. (Older `mlx-swift-examples` is superseded.) Source: https://github.com/ml-explore/mlx-swift-lm
- **Gemma 4 support: not confirmed.** README lists only Gemma 3. A developer reported on 2.31.x that `gemma4` is not registered; reusing Gemma 3 code fails at weight load (per-layer embeddings, KV sharing across back half of decoder, partial-rotation "proportional" RoPE). swift-jinja 1.x also silently corrupted the chat template (model loads, outputs gibberish); workaround was building the prompt string by hand. Community port: github.com/yejingyang8963-byte/Swift-gemma4-core (sidecar registration, E2B 4-bit only tested). Source: https://developer.apple.com/forums/thread/822084. An AI Engineer talk reports 40 tok/s on iPhone with `mlx-community/gemma-4-e2b-it-4bit` via mlx-swift-lm (version not stated). VERIFY: grep a 3.32.x checkout for `gemma4` in `Libraries/MLXLLM/Models/`; if absent, we write/port the model (~1 file) and register via `LLMTypeRegistry`.
- Our edge-2 is E4B, so the community E2B port is not drop-in (VERIFY E4B config: layer counts, shared-KV layers).
- Minimal load/stream (API from mlx-swift-lm 2.x/3.x docs; check exact signatures):
```swift
let container = try await loadModelContainer(directory: URL(filePath: modelDir)) // data/models/edge-2-q6 copied into app
let session = ChatSession(container, instructions: system)
for try await chunk in session.streamResponse(to: userText) { text += chunk }
```
Wrap this behind the existing `Engine` protocol (`apple/Sources/Kit/AminClient.swift`).

## 2. Memory
- Entitlement `com.apple.developer.kernel.increased-memory-limit` (Apple doc: https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.kernel.increased-memory-limit). Apple publishes no numbers.
- Community measurements: even with the entitlement, ceiling about 6144 MB on iPhone 16 Pro Max (8 GB) and iPhone 17 Pro Max (12 GB); 6656 MB with debugger. iPads expose more (M-series iPad Pro with 16 GB reported up to ~12 GB). Source: https://developer.apple.com/forums/thread/834805. One report says the entitlement worked in dev builds but not App Store builds: VERIFY on TestFlight.
- Verdict: **6-bit 5.7 GB will not run reliably on iPhone** (weights plus KV cache plus app exceed ~6 GB, jetsam kills). 8-bit 7.4 GB is out. Mac and M-series iPad (16 GB) can run 6-bit or 8-bit.
- iPhone: **4-bit E4B (~3.9 GB)** is the realistic fit on 8/12 GB phones with a short context (about 2-3 GB headroom); safer is an **E2B 4-bit student** (~1.5-2.5 GB; measured 340-390 MB resident reported by the port author with mmap, 12-14 tok/s on a 7.4 GB iPhone). Plan: Mac/iPad Pro = edge-2 q6; iPhone = E4B q4 (needs a gate re-run) or E2B student. Per-layer embeddings can be mmapped and stay off the working set: test.
- MLX does not run in the iOS Simulator (needs Metal GPU features absent there): test on device or Mac (Designed for iPad / native macOS).

## 3. Embeddings
- **intfloat/multilingual-e5-small** (118M, 384-d, covers en/ar/ml, **MIT**). Community MLX (https://huggingface.co/Roxas13/e5-small-mlx) and Core ML int8 conversions exist (https://huggingface.co/tuanda2912/hark-multilingual-e5-small-coreml). XLM-RoBERTa arch is in MLXEmbedders. Needs "query: " / "passage: " prefixes. Recommended; convert ourselves to avoid third-party trust.
- EmbeddingGemma-300M: Core ML int8 ~295 MB, Matryoshka dims; licence not confirmed (likely Gemma terms): VERIFY. bge-m3 (MIT, 568M) too big for phones; unverified in Swift.

## 4. Android
- Google's supported path: **LiteRT-LM** `.litertlm` files for Gemma 4 E2B (~2.6 GB) and E4B (~3.7 GB) at https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm. MediaPipe LLM Inference is maintenance-only. One user reported incoherent Russian from the E4B file: test Arabic and Malayalam ourselves.
- Our SFT+DPO weights: need conversion from HF safetensors (de-MLX first: we have MLX quant, so convert from the pre-quant bf16 checkpoint) via LiteRT-LM/ai-edge-torch export, then 4-bit. Not verified for fine-tuned Gemma 4: VERIFY.
- Fallback: llama.cpp GGUF (Q4_K_M, Unsloth repos) via JNI, MIT licence, slower than LiteRT GPU. MLC not researched. LiteRT-LM and llama.cpp: Apache 2.0 / MIT.

## 5. Licence
- Gemma 4 was released under **Apache 2.0**, replacing the Gemma Terms of Use used for Gemma 1-3. Commercial use and redistribution allowed with notice/attribution; no prohibited-use policy per secondary sources. Source: https://opensource.googleblog.com/2026/03/gemma-4-expanding-the-gemmaverse-with-apache-20.html. VERIFY against the LICENSE file in the HF model repo before shipping; keep a NOTICE entry. Shipping weights in the app is allowed. App Store size: weights >4 GB need On-Demand Resources or first-launch download (a download is allowed; no cloud inference).
