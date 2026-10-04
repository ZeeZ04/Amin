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
uv run amin ingest --reset --provider echo
uv run amin eval --provider echo

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

say "real index + eval"
uv run amin doctor
uv run amin ingest --reset
uv run amin eval

say "done"
echo "  amin ask \"How much notice must I give before the tenancy expires?\""
echo "  Record the eval numbers in docs/EXPERIMENTS.md as E4."
