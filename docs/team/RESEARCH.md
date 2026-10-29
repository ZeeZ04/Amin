# Amin research decisions (2026-10-29)
V = verified. TV = to verify before build or ship.

## 1. Task 1: on-device app
- **Runtime:** mlx-swift-lm (MLXLLM, MLXLMCommon, MLXEmbedders). Gemma4Text exists and "gemma4" is registered (V). R1's port plan is void. Pin the version; check the chat template renders (R1 saw swift-jinja corrupt it). TV. Plug in behind `Engine` (`apple/Sources/Kit/AminClient.swift`).
- **Model:** Mac and 16 GB iPad: edge-2 q6. iPhone: the memory ceiling is about 6 GB even with the entitlement (community figure, TV), so q6 and q8 are out. Ship E4B 4-bit (~3.9 GB) only if it passes the ADR-012 gate, else an E2B 4-bit student. Test on a real device and TestFlight (no MLX in the Simulator). Over 4 GB: first-launch download or On-Demand Resources. TV.
- **Embedder:** multilingual-e5-small (MIT, en/ar/ml), self-converted, with query/passage prefixes. Skip EmbeddingGemma (licence unclear) and bge-m3 (too big).
- **Android (later):** LiteRT-LM `.litertlm`, exported from our bf16 SFT+DPO weights (unproven for fine-tuned Gemma 4, TV; test Arabic and Malayalam). Fallback llama.cpp GGUF Q4_K_M.

## 2. Task 2: live voice
- **Wake word:** own Core ML keyword spotter on Silero VAD, trained on our own TTS and recordings of "Hey Amin/Ameen". v1 stopgap: VAD plus Whisper-base confirm (E37: 0.4 s). Rejected: openWakeWord models (CC BY-NC-SA, V) and Picovoice (proprietary AccessKey).
- **Platforms:** iOS cannot listen in the background (TV on device), so v1 is foreground only, plus the Siri intent and Action Button. macOS menu-bar app is the always-on target. Watch: tap, then relay.
- **STT:** English: SpeechTranscriber. Arabic: WhisperKit large-v3-turbo (Apple Arabic assets reportedly fail, TV). Malayalam: vrclc Whisper-small on phone, medium on Mac; expect weak natural-speech accuracy; licence conflict (E37 says Apache-2.0, cards list none), TV. Android: whisper.cpp.
- **TTS:** English: Kokoro-82M (check the port). Arabic: AVSpeech (Piper only with a clean voice licence, TV). Malayalam: Indic Parler-TTS on Mac and hub only; text-only replies on iPhone. Rejected: MMS-TTS.
- **Loop:** Idle, Listening, Thinking, Speaking, with a 2-turn idle timeout. One `AVAudioEngine` with voice processing. Silero endpointing at 500-700 ms, adaptive. Barge-in: duck at 200-300 ms of speech, stop at 300 ms, cancel generation. Stream TTS per sentence. Target 1.0-1.5 s on Mac (TV).
- **v1:** Mac and iPad foreground voice, English and Arabic, Whisper-confirm wake, AVSpeech fallback. **Later:** custom KWS, Malayalam on device, Android, hub.

## 3. Task 3: PC model
- **Routing:** add a "pc-code" intent in `amin/classify.py`. Code and ML go to the big model, loaded on demand (16-20 GB); all else stays on edge-2.
- **Bake-off:** Gemma 4 31B (same tokenizer and template, so edge-2 data transfers; Malayalam 2.94 chars/token) against Qwen3.6-27B (SWE-bench 77.2, Malayalam tokenizer unmeasured, run E32). Add Devstral Small 2 as a control. Scores are third-party (TV). Pilot QLoRA memory on 31B.
- **Coding data:** OpenCodeInstruct (CC BY 4.0, filter rows, NOTICE file) plus synthetic data from a local Apache-licensed teacher. Skip Magicoder and anything distilled from GPT, Claude or Gemini APIs. Docs go in the index, not weights: Python, PyTorch, MLX (confirm LICENSE files).
- **Education pack (retrieval only, ADR-015):**
  - Pack A (shippable): Oak National Academy text (OGL v3, drop third-party assets, KS1-4 only), OpenStax, Wikipedia (separate pack), and our own-words spec summaries.
  - Pack B: owner-imported board PDFs, indexed locally, never shipped.
  - Never train on AQA or Pearson text (AQA bans AI training).
  - Metadata: board, spec code (R3's codes are from memory, TV), subject, level, topic, licence.
- **Evaluation:** ADR-012 gate unchanged on non-code routes, with Arabic and Malayalam probes and a misroute rate. Code: LiveCodeBench, EvalPlus, plus 50 ML prompts with citation checks. Education: 30-50 teacher-written questions per board and subject, deduped against all training and retrieval text, frozen, with a no-retrieval baseline and abstention checks.

## 4. Licence register
| Item | Licence | Commercial |
|---|---|---|
| Gemma 4 (E4B, 31B) | Apache-2.0 (E4B V; 31B TV) | Yes |
| Qwen3.6 | Apache-2.0, disputed | TV |
| Devstral Small 2 | Apache-2.0 | Yes |
| mlx-swift-lm | MIT assumed | TV |
| multilingual-e5-small | MIT | Yes |
| WhisperKit, whisper.cpp, Silero | MIT | Yes |
| vrclc Whisper (ml) | Unclear | TV |
| Kokoro-82M | Apache-2.0 | Yes |
| Indic Parler-TTS | Apache-2.0, gated | Yes |
| Piper | MIT, voices vary | TV |
| LiteRT-LM, llama.cpp | Apache-2.0, MIT | Yes |
| openWakeWord models, MMS-TTS | Non-commercial | No |
| Picovoice | Proprietary | No |
| OpenCodeInstruct, OpenStax | CC BY 4.0 | Yes |
| Magicoder | Conflicting | No |
| Oak | OGL v3 | Yes, not third-party assets |
| Wikipedia | CC BY-SA | Yes, share-alike |
| AQA, Pearson | All rights reserved | No |

## 5. Risks and owner questions
**Risks:** 1. iPhone memory kills E4B or fails the gate. 2. AQA or Pearson text leaking into training or the shipped pack. 3. Malayalam voice quality and licence. 4. No iOS background wake word. 5. Second-hand licences and scores (Qwen3.6, ports, spec codes).

**Owner only:**
1. Write to copyright@aqa.org.uk and copyrightPQS@pearson.com for a commercial retrieval licence. Is Pack B acceptable meanwhile?
2. Accept foreground-only "Hey Amin" on iPhone?
3. Accept text-only Malayalam replies on iPhone for v1?
4. Accept a first-launch download of over 4 GB?
5. Fund Malayalam recordings and a teacher for the eval set?
