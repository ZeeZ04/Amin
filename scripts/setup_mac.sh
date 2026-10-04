#!/usr/bin/env bash
# One-time setup on an Apple Silicon Mac. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."

say() { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }

command -v uv >/dev/null || { say "installing uv"; curl -LsSf https://astral.sh/uv/install.sh | sh; }

say "python env"
uv venv
uv pip install -e ".[dev]"

say "offline check (no model needed)"
uv run pytest -q
uv run python scripts/build_eval_set.py
uv run amin ingest --reset --provider echo
uv run amin bench --provider echo --verifier lexical

if ! command -v ollama >/dev/null; then
  say "ollama is not installed"
  echo "  brew install ollama   # then: ollama serve"
  echo "Skipping model pulls. Amin works now with --provider echo."
  exit 0
fi

say "pulling models (~23 GB total, one time)"
ollama pull nomic-embed-text   # ~275 MB  embeddings
ollama pull qwen3:8b           # ~5 GB    verifier + query rewriting
ollama pull qwen3.6:27b        # ~18 GB   answer model

say "real index + ablation benchmark"
uv run amin doctor
uv run amin ingest --reset
# Smoke-test on a stratified sample first: the full 173-item, 3-system run is
# ~500 model calls plus one verifier call per sentence, which is a long wait to
# discover a misconfigured model name.
uv run amin bench --sample 24
say "full run (this takes a while - 3 systems x 173 items)"
uv run amin bench

say "done"
echo "  amin ask \"How much notice must I give before the tenancy expires?\""
echo
echo "NEXT, in this order:"
echo "  1. Record these numbers in docs/EXPERIMENTS.md as E7."
echo "  2. Re-sweep the evidence floor: make sweep"
echo "     0.45 is tuned for the no-model extractor; a real model abstains on"
echo "     its own, so the floor should come down. Do not keep the old default."
echo "  3. If naive RAG's hallucination rate also collapses with a real model,"
echo "     the verifier is not earning its latency. Cut it and say so."
