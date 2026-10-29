# Team brief (read this first; it replaces re-reading the repo)

**Amin** is a private, local AI assistant ("أمين", trustworthy). It answers general
questions and answers from the owner's own documents with a citation for every
claim. Nothing leaves the owner's device. Languages: English, Arabic (RTL), Malayalam.

## State of the repo (2026-10-29)
- Python core `amin/`: retrieval + citation pipeline, a single-pass router
  (`classify.py`), voice and wake word (`voice.py`, local Whisper), per-person
  memory (`memory.py`) and history.
- Model: **edge-2** = Gemma 4 E4B, SFT + DPO. 8-bit 7.4 GB, 6-bit 5.7 GB. It
  matches the 27B teacher on the release gate. p50 0.9 s on an M3 Max.
- Web app `amin/web/`: chat, voice mode with "Hey Amin", documents, projects, memory.
- Native SwiftUI apps `apple/`: iPhone/iPad/Mac/Vision Pro/Apple TV, plus a
  Watch relay and a Siri "Ask Amin" intent. Today they talk to an Amin server on
  the Mac through `Engine` (`apple/Sources/Kit/AminClient.swift`); an
  on-device engine must plug in behind that protocol.
- Decisions: `docs/DECISIONS.md` (ADR-012 ship gate, ADR-014 on-device, ADR-015
  memory not weights). Experiments: `docs/EXPERIMENTS.md` (E1–E38).
- Code map: run `graphify query "<question>"` in the repo root. Prefer it over
  reading files. Read only the lines you need.

## The owner's three tasks
1. **App:** a fully functioning, professionally designed app where **the model
   runs on the device** (iPhone, iPad, Mac first; Android later).
2. **Live talking assistant:** say "Hey Amin" / "Hey Ameen", then hold a natural
   back-and-forth voice conversation. The look is a JARVIS-like HUD: a glowing
   orb on a big screen.
3. **PC (Mac) model with more knowledge:** coding, AI/ML models, and UK
   education (all GCSE and A level, Edexcel and AQA boards).

## Rules every teammate follows
- **Privacy is the product.** No cloud APIs or telemetry at runtime. Every
  model, voice and dataset must run locally and be **licensed for commercial
  use**. Flag any licence you are unsure of.
- Facts go into the **index** (retrievable, citable, deletable), never into
  personal fine-tunes (ADR-015). Training teaches behaviour.
- Be concrete: name packages, versions, file paths, numbers and licences, with sources.
- **Tokens are tight.** Write your full output to your assigned file under
  `docs/team/`, at most about 600 words unless told otherwise. Reply to the lead
  in **at most 120 words**: the key decisions and the file path. Do not paste the file.
