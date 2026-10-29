# R2: on-device live voice assistant (Apple first, Android later)

Evidence level is marked. VERIFIED = read on the source page this session; KNOWN = Apple docs or WWDC knowledge not re-fetched; CHECK = verify on a device before committing.

## Recommendation
Build a native pipeline behind one `Voice` protocol: **VAD + custom wake word -> WhisperKit (or SpeechTranscriber for English) -> existing edge-2 -> Kokoro/AVSpeech (English, Arabic) and Indic Parler-TTS (Malayalam)**, all in one `AVAudioEngine` with voice processing on. Do not use Picovoice or openWakeWord's stock models.

## 1. Wake word
| Option | Verdict | Source |
|---|---|---|
| openWakeWord | Code Apache-2.0, but all pretrained models are CC BY-NC-SA 4.0, so unusable. You can train your own "Hey Amin" head on the Apache feature extractor, but check the synthetic training data's licence. | [HF model card](https://huggingface.co/davidscripka/openwakeword) VERIFIED |
| Picovoice Porcupine | Proprietary, needs an AccessKey. Free tier reported ending 30 Jun 2026 and paid plans are about $6k/yr (third-party figure). Violates "no runtime cloud or licensing calls". Rejected. | [HA forum](https://community.home-assistant.io/t/fyi-picovoice-confirmed-free-tier-accesskeys-will-stop-working-after-june-30-2026/1012744), [Picovoice](https://picovoice.ai/pricing) CHECK |
| Own tiny Core ML keyword spotter | A small CNN/GRU over log-mel, trained on our own TTS-generated and recorded "Hey Amin/Ameen" plus Arabic and Malayalam variants. About 100-500 KB, under 1% CPU. Best long-term. | design |
| Whisper-base burst check (E37, today) | Works as a stopgap. It needs a VAD gate and costs about 0.4 s per burst, which is too heavy for always-on battery use. | EXPERIMENTS E37 |
| SFSpeechRecognizer / SpeechAnalyzer as wake word | Possible in the foreground only. Not a battery-friendly always-on listener. | KNOWN |

Stage it: energy VAD (Silero VAD, MIT, or the Core ML port) -> Core ML KWS -> optional Whisper-base confirmation of the phrase to cut false wakes (E37 had 1/5 false wakes unconfirmed).

**Background reality.** KNOWN, and a design constraint:
- **iOS:** third-party apps cannot listen for a wake phrase in the background. Only Apple's "Hey Siri" can. A backgrounded app is suspended unless it holds an active audio session (the `audio` background mode); a mic session may be kept alive but shows the orange dot and is likely to fail App Review without a clear, user-started reason. Use **foreground "Hey Amin"** (screen on, app open, or an explicit "Listening" mode) plus the existing Siri "Ask Amin" App Intent and Action Button / Lock Screen control for out-of-app launch.
- **macOS:** a menu-bar or login-item app can listen continuously with the mic permission. No suspension. This is the best Apple target for true always-on.
- **watchOS:** no background mic. Raise the wrist or tap, then relay to the phone (existing Watch relay).
- **Android:** a foreground service with a mic-type notification is allowed (Android 14 needs `FOREGROUND_SERVICE_MICROPHONE`). Background start from the idle state is restricted, so the user must start the service. Use the same Core ML-equivalent KWS via TFLite/ONNX.
- **Home hub** (always-on, mains power, Mac mini or Raspberry Pi-class): the right place for ambient "Hey Amin". Run KWS plus VAD there with no OS limits.

## 2. Speech to text
| Option | English | Arabic | Malayalam | Notes |
|---|---|---|---|---|
| SpeechAnalyzer / SpeechTranscriber (iOS 26, macOS 26) | yes | forum report that Arabic is listed but asset download fails (iOS 26.x) CHECK | not found in any source, assume no | Fastest and free for English, with no model to bundle. Query `SpeechTranscriber.supportedLocales` on a device. Launch set was about 10 languages, now reportedly about 40. [WWDC25](https://nonstrict.eu/wwdcindex/wwdc2025/277/), [forum](https://developer.apple.com/forums/thread/797835) |
| SFSpeechRecognizer (on-device) | yes | partial | no | Legacy, short sessions. DictationTranscriber falls back to the same model set. |
| WhisperKit (argmax OSS) | yes | yes (Whisper large-v3 Arabic is mediocre; test it) | weak in stock Whisper | MIT. iOS 17/macOS 14+, Core ML, streaming. Android only in the Pro SDK (paid), so on Android use whisper.cpp (MIT) or sherpa-onnx (Apache-2.0). [GitHub](https://github.com/argmaxinc/WhisperKit) VERIFIED |
| vrclc Whisper-medium-Malayalam | | | yes | Our server already uses it (E37, Apache-2.0). The card's WER is 14.7 on OpenSLR (read speech, optimistic) but about 64 on Common Voice 16, so expect rough results on natural speech. The medium size is about 1.5 GB in fp16, too big for the phone and tight on 6 GB devices, so convert to Core ML, quantise to 4-bit palettised, or use vrclc Whisper-small (about 480 MB). [vrclc medium](https://huggingface.co/vrclc/Whisper-medium-Malayalam), [small](https://huggingface.co/vrclc/Whisper-small-Malayalam) VERIFIED, licence per E37 |

Plan: language-ID on the first 2 s with Whisper-base, then route to SpeechTranscriber (en) or WhisperKit large-v3-turbo (ar), or the Malayalam fine-tune (ml). Latency target: under 300 ms after end of speech for English and under 800 ms for Whisper paths. Offer streaming partials. Whisper is not natively streaming, so use rolling 2-3 s windows with local agreement (what WhisperKit `--stream` does).

## 3. Text to speech
- **AVSpeechSynthesizer:** English and Arabic voices (Siri-grade "Premium/Enhanced" downloadable). Malayalam: Apple has had no Malayalam system voice (E37 confirmed none on macOS) CHECK iOS 26 voice list. Free, zero size, instant start. Keep it as the fallback for en and ar. Personal Voice and Siri voices are not available to third parties.
- **Kokoro-82M:** Apache-2.0, 82M params, 8 languages and 54 voices (English very natural; no Malayalam; Arabic not covered). Runs at several times real time on a Mac and on a recent iPhone through Core ML / MLX Swift ports (CHECK port licences and actual speed). Best natural English. [HF](https://huggingface.co/hexgrad/Kokoro-82M) VERIFIED
- **Piper:** MIT (original; the project moved repositories, check the new licence), ONNX, about 20-60 MB per voice, fast on a phone, quality below Kokoro. Voice licences vary per voice dataset, so check each one. Piper has Arabic voices; there is no good Malayalam one. KNOWN, CHECK
- **Indic Parler-TTS (AI4Bharat):** Apache-2.0, 0.9B params, Malayalam officially supported (voices Anjali, Harish, Anju; 25 h Malayalam training data; native-speaker score 86.5). Gated on Hugging Face (accept a form, then it can be redistributed under Apache-2.0). Runs on a Mac through PyTorch/MPS or MLX; about 3.6 GB in fp32, which is too heavy for an iPhone unless quantised, and generation is not real time on a phone. Use on the Mac first, and on hub or iPad-Pro-class devices later. [HF](https://huggingface.co/ai4bharat/indic-parler-tts) VERIFIED
- **IndicF5:** MIT per its card, 0.4B params, 11 languages including Malayalam, F5-style voice cloning from a reference clip (policy forbids cloning without the owner's permission). Smaller than Parler, so a better candidate for iPhone after Core ML conversion or quantisation (unproven). Card points to a newer Indic-Speak model; check its licence before choosing. [HF](https://huggingface.co/ai4bharat/IndicF5) VERIFIED
- **Rejected:** Meta MMS-TTS (non-commercial, E37). TTSKit (Argmax) has no Malayalam or Arabic.

Stream TTS sentence by sentence as the LLM generates, so the first audio starts after the first sentence (target under 400 ms from the first sentence boundary).

## 4. Conversation loop
States: `Idle (KWS) -> Listening -> Thinking -> Speaking -> Listening`, with a 2-turn idle timeout back to `Idle` (as E37).
- **Audio:** one `AVAudioEngine`; set `inputNode.setVoiceProcessingEnabled(true)` (AEC, noise suppression, AGC) so the mic hears the user and not the speaker. Use `.playAndRecord`, mode `.voiceChat`, and route output through the same engine (play TTS through an `AVAudioPlayerNode` in the same engine; AEC needs the playback to go through the same I/O unit). Gotcha: voice processing lowers output volume and ducks other audio. On macOS the same call exists. Android: `VOICE_COMMUNICATION` source plus `AcousticEchoCanceler`. KNOWN, CHECK on device.
- **VAD / endpointing:** Silero VAD (MIT) at 32 ms frames. End of turn after 500-700 ms of silence, adaptive: shorten after a complete sentence, lengthen after a trailing "and/um". The web mode uses a fixed 1.3 s, which feels slow. Optionally add a small semantic end-of-turn check on the partial transcript.
- **Barge-in:** while Speaking, keep VAD running on the AEC-cleaned mic. When speech lasts over 200-300 ms and overlaps no echo, duck TTS volume at once, stop it after 300 ms confirmation, cancel LLM generation, and feed the new utterance. Also accept a tap on the orb. Never stop on a lone "Amin", which would be our own TTS echo, and do not let the TTS say its own wake word.
- **Latency budget (target 1.0-1.5 s speech end -> first audio):** endpointing 0.5 s + STT finalisation 0.2 s + edge-2 first sentence 0.5-0.9 s (p50 0.9 s total on M3 Max; the iPhone will be slower) + TTS first chunk 0.15-0.3 s. Cut by streaming the STT partials into a speculative prefill of the LLM prompt.
- **Orb HUD:** drive the orb from the input RMS level (listening) and TTS player level (speaking).

## Open questions for the lead
1. Is foreground-only "Hey Amin" on iPhone acceptable, with always-on only on Mac and a hub?
2. Malayalam TTS on iPhone is unsolved (Parler 0.9B is too big); until then use the Mac or hub for Malayalam speech or text-only replies.
3. Confirm the vrclc licence on the model card (E37 says Apache-2.0; the cards I fetched list none).
