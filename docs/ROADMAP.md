# Roadmap

Where Amin is going and what is left, as of 2026-10-30. The direction is
ADR-014: a public release that runs fully on each person's own devices, in
English, Arabic and Malayalam.

## Done

- Grounded pipeline with citation verification, conflict detection and
  refusal gates (E1–E22).
- Household accounts, projects and permissions (ADR-013); one history
  database per person; Teach Amin, personal memory that is cited and
  deletable (ADR-015).
- Malayalam in the tokenizer, verifier, conflict detector and OCR, with
  evals (E32); the multilingual safety router, crisis 14/14 (E34); the
  single-pass routing classifier (Jev's idea, run locally).
- **Amin's own model, edge-2** (Gemma 4 E4B, SFT then DPO): the default
  answer model on the Mac (E38). **edge-2-m46** (4.1 GB, mixed 4/6-bit) is
  the iPhone build; it matches q6 on every paired test (E39).
- **Native apps** for iPhone, iPad, Mac, Vision Pro, Apple TV and Watch:
  - the model runs on the device through MLX Swift, and downloads from the
    Amin computer over the home network, never the internet;
  - documents on the device, answered from with citations (`LocalLibrary`);
  - first-run onboarding; the Majlis Orb voice HUD; "Hey Amin" ambient mode
    with on-device speech; Mac quick ask (⌥Space) and menu-bar door.
- **Knowledge packs** (Task 3): Python docs and six OpenStax textbooks,
  opt-in per person, cited like documents, with a shared embedding cache.

## Next

1. **Multilingual retrieval.** On the device, add multilingual-e5-small (MIT,
   about 470 MB; needs the owner's OK to download) as a second ranking signal,
   so a Malayalam question finds an English document. On the server, bench
   `bge-m3` (already pulled) against nomic-embed-text.
2. **Education.** Run the held-out GCSE/A-level set (`data/eval/eval_edu.jsonl`)
   with and without packs (E40). Add the Oak National Academy pack (OGL v3,
   needs an API key from the owner). AQA and Pearson material stays out unless
   the boards grant a licence.
3. **Coding and AI route** for the Mac: a Gemma 4 31B vs Qwen3.6-27B bake-off
   on coding questions (disk permitting).
4. **Voice.** Malayalam speech recognition on the device (WhisperKit with a
   Malayalam fine-tune; licence to verify) and Malayalam speech output.
5. **Design.** Interface language (Arabic RTL, Malayalam), the whole-document
   viewer, answer progress stages, iPad and Mac layouts per DESIGN.md, and a
   hands-on check of quick ask.
6. **Fluent review.** A Malayalam speaker reads the held-out answers; the
   corrections become the Malayalam gate.

## Later: every device, fully private

| platform | plan |
|---|---|
| iPhone, iPad, Mac, Vision Pro, Apple TV | One SwiftUI app; the model on-device via MLX Swift; SQLite per person |
| Apple Watch | Companion app: ask by voice, answers from the iPhone |
| Apple home hub ("HomeView") | No SDK yet; the iPad build is the likely starting point |
| Android phone and tablet | Kotlin app; the model via llama.cpp or MediaPipe (Gemma) |

Also needed:
- Encrypted sync between one person's own devices, with no server reading it.
- Store accounts (Apple Developer, Google Play), held by the owner.
- A privacy policy and store review.
- Model sizing per device: E2B or E4B-class on phones, larger on Macs.
