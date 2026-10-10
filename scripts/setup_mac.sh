#!/usr/bin/env bash
# One-time setup on an Apple Silicon Mac. Safe to re-run: every step is skipped
# if it is already done, so a failed model pull can be resumed by running this
# again rather than starting over.
set -euo pipefail
cd "$(dirname "$0")/.."

say()  { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
warn() { printf "\033[1;33m    %s\033[0m\n" "$1"; }
fail() { printf "\n\033[1;31m==> %s\033[0m\n" "$1"; exit 1; }

OLLAMA_HOST_URL="${AMIN_OLLAMA_HOST:-http://127.0.0.1:11434}"

server_up() { curl -fsS --max-time 3 "$OLLAMA_HOST_URL/api/tags" >/dev/null 2>&1; }

command -v uv >/dev/null || { say "installing uv"; curl -LsSf https://astral.sh/uv/install.sh | sh; }

say "python env"
uv venv --allow-existing
uv sync --extra dev   # install from uv.lock, not a fresh resolve

say "offline checks (no model needed)"
uv run pytest -q
uv run python scripts/build_eval_set.py
uv run amin ingest --reset --provider echo
uv run amin bench --provider echo --verifier lexical

# ---------------------------------------------------------------------------
# From here on a model is required.
# ---------------------------------------------------------------------------

if ! command -v ollama >/dev/null; then
  say "ollama is not installed — stopping here"
  echo "    brew install ollama"
  echo "    brew services start ollama   # or: ollama serve  (blocks the terminal)"
  echo "    then re-run this script."
  echo
  echo "Everything above works without it. Amin runs now with --provider echo."
  exit 0
fi

# The previous version of this script went straight to `ollama pull` and died
# with "could not connect to ollama server" halfway through setup. The server
# being installed and the server running are different things, so check.
if ! server_up; then
  say "ollama is installed but not serving at $OLLAMA_HOST_URL"
  if command -v brew >/dev/null && brew services list 2>/dev/null | grep -q '^ollama'; then
    warn "starting it as a background service..."
    brew services start ollama >/dev/null 2>&1 || true
    for _ in $(seq 1 20); do server_up && break; sleep 1; done
  fi
fi

if ! server_up; then
  say "still cannot reach the ollama server — stopping here"
  echo "    Start it in another terminal, then re-run this script:"
  echo
  echo "      brew services start ollama   # background, survives reboot"
  echo "      ollama serve                 # foreground, blocks that terminal"
  echo
  echo "Nothing above this point is lost; the script resumes from here."
  exit 1
fi

say "pulling models (~23 GB total, one time, resumable)"
# Pull smallest first: if the big one fails or is interrupted, the usable parts
# of the system are already in place.
for model in nomic-embed-text qwen3:8b qwen3.6:27b; do
  if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$model"; then
    echo "    $model already present, skipping"
  else
    echo "    pulling $model"
    ollama pull "$model" || fail "pull failed for $model — re-run this script to resume"
  fi
done

say "doctor"
uv run amin doctor

say "real index"
uv run amin ingest --reset

say "smoke test (stratified sample — fast)"
# The full run is 3 systems x 237 items plus one verifier call per sentence.
# That is a long wait to discover a misconfigured model name.
uv run amin bench --sample 30

say "full benchmark (this takes a while)"
uv run amin bench

say "done"
echo "    amin ask \"How much notice must I give before the tenancy expires?\""
echo
echo "NEXT, in this order:"
echo "  1. Record these numbers in docs/EXPERIMENTS.md as E16."
echo "  2. Re-sweep the evidence floor:  make sweep"
echo "     0.45 is tuned for the no-model extractor. A real model abstains on"
echo "     its own, so the floor should come down. Do not keep the old default"
echo "     without re-measuring."
echo "  3. If naive RAG's hallucination rate also collapses with a real model,"
echo "     the verifier is not earning its latency. Cut it and write that down."
