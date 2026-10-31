# Handoff: where Amin stands (2026-10-31)

Start new work from this page. The detail lives in README, ROADMAP, EXPERIMENTS and docs/team.

## Decisions the owner has made

- **Public product.** Anyone can create an account, and it goes to the App Store and Google Play.
  - The cloud (Supabase) holds the **account and subscription only**. Questions, documents, memory and voice stay on the device.
  - Models download once from **Hugging Face**.
  - **Free + Pro** through RevenueCat.
- **One model in focus: edge-2-q8.** This is Gemma 4 E4B, SFT then DPO.
  - edge-2-m46 is the iPhone build (E39).
  - amin-3 is retired. An upgrade replaces the current model only if it wins the paired gate (ADR-012).
- **Design: Lantern Majlis** (docs/team/D5-in-app-refresh.md, option B).
- **PC first, as a program:** `amin jarvis` (double-click *Amin Jarvis.command*) runs everything locally and opens the voice window. The iPad and home-device apps come later.

## State

| Area | State |
|---|---|
| Model | edge-2-q8 on the Mac, running in Jarvis |
| PC "Jarvis" | `/jarvis` page with the orb, "Hey Amin" wake word, Whisper speech recognition (Malayalam-tuned), full answer pipeline with citations. Started with `amin jarvis` on 127.0.0.1:8770 |
| Native apps | iPhone, iPad, Mac, Vision Pro, TV and Watch. On-device model and on-device documents with citations; Lantern Majlis design on sign-in, chat and settings. Onboarding, sidebar, documents and memory screens are still in the old style |
| Public backend | Code only (backend/, site/, apple Account): Supabase schema and functions, RevenueCat, Hugging Face downloads, legal pages. **None of the accounts exist yet.** See backend/SETUP.md |
| Knowledge packs | Python docs and six OpenStax books, opt-in, cited. E40: 30/32 education answers cited |
| CI | Green. Wait for checks before merging |

## Open problems, in order

1. **Robotic voice.** Replies are spoken with the browser's system voice, and there is no Malayalam voice at all.
   - Wanted: a natural on-device voice in English, Arabic and Malayalam.
   - Candidates to evaluate (check licences): Kokoro-82M (Apache-2.0, English, very natural), Piper (MIT, many languages incl. Arabic), Indic Parler-TTS (Apache-2.0, Malayalam), IndicF5.
   - Quick interim win: macOS Premium/Enhanced voices.
   - Serve it from the Amin server (a `/speak` endpoint that streams audio) so the Jarvis page, the web app and the native apps all share it.
2. **Accounts are mixed up.**
   - The local server still uses the old household model: invite codes, first account is admin.
   - The public product uses Supabase accounts.
   - Decide how they meet. For example, Jarvis on the PC signs in with the Supabase account, or runs with no account at all because it is the owner's own machine. Then remove invite codes from the public path.
3. **Malayalam and Arabic on the native apps.** Speech recognition on the device (WhisperKit) and the voice from item 1.
4. **The rest of the Lantern Majlis screens.** Onboarding, sidebar, documents, memory, and the web app.
5. **Going live.** The owner creates the service accounts (backend/SETUP.md), then end-to-end tests against them.
6. **Multilingual retrieval on the device.** multilingual-e5-small, which needs the owner's OK to download.

## Working rules

- Keep the code graph current (`graphify update .`) and read only what a change needs.
- Branch, then PR, then **green CI**, then merge.
- Ask before downloads, outward actions and anything touching accounts or credentials.
- The owner types their own passwords.
