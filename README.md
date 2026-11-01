# Amin

A private assistant for your own Mac. Amin runs on your computer, answers
general questions, and answers from your own documents with the passage behind
each sentence. An answer with no document behind it is labelled general
knowledge. It works in English, Arabic and Malayalam, by text or voice. `أمين`
means trustworthy.

There is no subscription and no cloud service. Once the models are downloaded,
your questions and documents stay on your Mac. Amin asks for a name and password
the first time, but that account exists only on this Mac.

## Requirements

- A Mac with Apple silicon. Intel Macs can't run the on-device model.
- Enough memory for the model. This was measured on one Mac (M3 Max, 64 GB,
  macOS 26):

  | model | on disk | peak memory | status |
  |---|---|---|---|
  | edge-2-q8 (Amin's own) | 7.4 GB | **8.1 GB** | default, [not published yet](#limits) |
  | gemma-4-e4b-it-8bit (its public base) | 8.3 GB | not measured; expect about the same | what a fresh install uses |
  | qwen3.6:27b through Ollama (optional) | ~18 GB | **26 GB** | larger fallback |

  16 GB should be enough for the Gemma model, but no Mac smaller than 64 GB has
  been tested. Voice loads Whisper as well, and its memory hasn't been measured.
- About 12 GB of free disk for the Gemma model, embeddings and voice.
- [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com) (`brew install uv ollama`).
  Ollama provides the embeddings for document search.

## Install

```bash
git clone https://github.com/ZeeZ04/Amin.git && cd Amin
uv sync --python 3.12 --extra dev --extra train --extra voice
```

Check that it works, with no model and no network:

```bash
uv run pytest -q
uv run amin ingest --reset --provider echo
uv run amin bench --provider echo --verifier lexical --no-save
```

Download a model, the embeddings and the voice models:

```bash
uv run hf download mlx-community/gemma-4-e4b-it-8bit --local-dir data/models/gemma-4-e4b-it-8bit
brew services start ollama
ollama pull nomic-embed-text
make voice-models
```

Gemma has its own licence terms, which you accept by downloading it. Then start
Amin:

```bash
uv run amin jarvis --model gemma-4-e4b-it-8bit
```

The first load takes about a minute. A window opens on `127.0.0.1`. It first
asks you to sign in: follow the link and create your local account, and the first
account becomes the admin. Then say "Hey Amin". Ctrl-C in the terminal stops
everything.

To add your own documents, open the address the terminal prints without
`/jarvis`, and upload them under Documents. They are stored in `data/users/`, which git
ignores.

## How it answers

```
question
  ├─ 1. scope check ───── medical, legal and financial questions are handled by policy.yaml
  ├─ 2. retrieve ──────── embeddings + keywords over your documents
  ├─ 3. evidence check ── do the documents really cover this?
  ├─ 4. generate ──────── from the passages, or labelled as general knowledge
  ├─ 5. verify ───────── check each sentence against the passage it cites
  └─ 6. assemble ─────── delete unsupported citations, label uncited reasoning
```

Facts you teach it ("Remember that…") go into your private library, not into the
model, so they are cited and can be deleted. `docs/ARCHITECTURE.md` has the
detail.

## What has been measured

edge-2-q8 against the 27B model on the repository's synthetic documents, in the
app's mode (E38 in [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md); ADR-012 is the
gate a new model must pass):

| | edge-2 | qwen3.6:27b |
|---|---|---|
| answered correctly from documents | 108/110 | 108/110 |
| correctly declined | 85/99 | 85/99 |
| Malayalam reading comprehension | 93/108 | 86/108 |
| median time per answer | 0.9 s | about 7 s |

These numbers don't apply to the public Gemma base, which hasn't had Amin's
training. They also don't show how Amin does on your own documents. To reproduce
the pipeline test without a model, run `make eval-bench`. Those figures measure
plumbing only, because the test provider has no language model.

## Limits

- **The trained model isn't published.** A fresh install runs the untrained
  Gemma base, which is less tuned for citing and declining. Building edge-2
  yourself is in [`docs/TRAINING.md`](docs/TRAINING.md) and takes many hours.
- **It's a small model.** It is far from a frontier model on hard reasoning, and
  it will sometimes be wrong. Check the cited passage when the answer matters.
- **Coding and image reading are unmeasured.** Don't assume it does either well.
- **Malayalam is the weakest language.** About 86% of answerable questions were
  correct and 83% of declines were right on IndicQA, measured on the 4.1 GB
  phone build.
- **Voice is lightly tested.** Its checks show the method works, but they aren't
  accuracy figures for real speakers and accents.
- **Search has known holes.** The evidence check matches words, so it can confuse
  "FR-550" with "FR-440". See E11.
- **`make serve` is reachable by other devices on your network.** It binds to all
  addresses. `amin jarvis` binds to `127.0.0.1` only, so use that.
- **Sign-in is still there.** It's left over from when Amin served a household,
  and it's local only. Removing it is planned.
- **Some code still reaches beyond this Mac if you turn it on.** Installing downloads
  from Hugging Face, PyPI and Ollama. `amin/hosted.py` can use a hosted model if
  you configure one, for benchmarks. Neither happens while you use Amin normally.
- **The native app in [`apple/`](apple/README.md) isn't ready.** It builds from
  source with Xcode, and its Mac screens are still being reworked. It still has
  sign-in code from an earlier plan. Other Apple platforms aren't being worked on.
- **Nothing else is supported.** There's no App Store build, Android app or
  website. [`archive/`](archive/README.md) holds that unused work.

## Repository

```
amin/      the Python app: pipeline, CLI, API, web and voice windows, training
apple/     the SwiftUI app
data/      synthetic sample documents and evaluation sets
docs/      architecture, experiments, decisions, training
reports/   saved benchmark results
private/   for your own files; ignored by git
archive/   unused: old backend and website
```

## License

The code is MIT, built by Abdul Azeez. The bundled Malayalam font is under the
SIL Open Font License (`amin/web/fonts/OFL.txt`). Models you download keep their
own licences.
