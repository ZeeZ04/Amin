# Roadmap

Where Amin is going and what is left, as of 2026-10-22. The direction is
ADR-014: a public release that runs fully on each person's own devices, in
English, Arabic and Malayalam.

## Done

- Grounded pipeline with citation verification, conflict detection and
  refusal gates (E1–E22).
- Amin's own model: amin-3 (Qwen3-8B, SFT) matches qwen3.6:27b on held-out
  slices at about 4× the speed (E31).
- Household accounts, projects and permissions (ADR-013).
- App redesign: sidebar on tablet and desktop, tabs on phone, a source
  inspector, in-app dialogs, light and dark themes, bundled Malayalam font.
- Conversation history, one database per person (`amin/history.py`).
- Malayalam in the tokenizer, verifier, conflict detector and OCR, plus a
  Malayalam eval with a baseline (E32).
- Multilingual safety router: crisis caught 14/14 against 0/14 before (E34).
- On-device base chosen: Gemma 4 E4B (E33); edge student training (E35).
- Follow-up questions (E36), and voice mode with "Hey Amin" in the web app (E37).

## Next: design

1. **Interface language.** Arabic and Malayalam interface text, with the
   full right-to-left layout for Arabic. Answers already follow the
   question's language; the interface does not yet.
2. **Document viewer.** Open the whole document with the cited passage
   highlighted in place, not only the passage.
3. **Answer progress.** Show the stages while an answer is built: searching,
   reading, checking sources. Long Malayalam answers make waiting visible.
4. **History tools.** Rename, search, and pin conversations.
5. **First run.** A guided start: create the admin, add a first document,
   ask a first question.
6. **Status page.** Which model is answering, how fast, and storage used.
7. **Quality passes.** Accessibility (VoiceOver, keyboard, contrast), a
   worst-case data stress test (`break-ui`), and a maskable app icon.
8. **Voice, next steps.** Malayalam speech output (AI4Bharat Indic voices).
   Real-speaker tests of the wake word and of Malayalam recognition. Siri
   Shortcuts ("Hey Siri, ask Amin") in the native app.

## Next: model

1. Finish E32 on the teacher, Gemma 4 E4B and Qwen3.5-9B, then choose the
   base (ADR-014).
2. Build grounded Malayalam training data: translate the synthetic training
   corpus with IndicTrans2 (MIT), keeping the exact answer keys.
3. SFT on the chosen base: the amin-3 mix (to keep English and Arabic) plus
   Aya human Malayalam, translated Dolly and grounded Malayalam. Then DPO
   aimed at Malayalam declining, which is 59.6% today.
4. Fluent review: a family member reads the Aya held-out answers and
   corrects them; the corrections become the Malayalam gate.
5. Multilingual embeddings. `bge-m3` is pulled; swapping it in changes
   retrieval for every language, so it gets its own bench run first.
6. A local single-pass classifier for routing (medical, legal, financial,
   crisis), language and question kind. This is Jev's idea, run on Amin's own
   model.

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
