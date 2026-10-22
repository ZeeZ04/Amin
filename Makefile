NO_THINK = --chat-template-args '{"enable_thinking": false}'

.PHONY: install ingest eval ask test lint serve doctor clean sweep certs train-setup train-corpus distill train-sft serve-student preferences train-dpo bench-student

install:
	uv venv && uv pip install -e ".[dev]"

ingest:
	uv run amin ingest --reset

eval:
	uv run amin ingest --reset --provider echo
	uv run amin eval --provider echo

eval-real:
	uv run amin ingest --reset
	uv run amin eval

ask:
	uv run amin ask "$(Q)"

test:
	uv run pytest -q

lint:
	uv run ruff check amin tests

serve:
	# Reachable from phones on the home Wi-Fi. HTTPS once `make certs` has run.
	# Starts Amin's own model too (E31); without it, auto mode uses Ollama.
	@if [ -d data/models/amin-3 ] && ! curl -s localhost:8080/v1/models >/dev/null; then \
	  echo "starting amin-3 on :8080 (log: data/mlx-server.log)"; \
	  nohup uv run mlx_lm.server --model data/models/amin-3 --port 8080 $(NO_THINK) > data/mlx-server.log 2>&1 & \
	fi
	@if [ -f data/certs/amin.pem ]; then \
	  uv run uvicorn amin.api:api --host 0.0.0.0 --port 8443 \
	    --ssl-certfile data/certs/amin.pem --ssl-keyfile data/certs/amin-key.pem; \
	else \
	  echo "no certificate yet - serving plain HTTP. Run 'make certs' for HTTPS."; \
	  uv run uvicorn amin.api:api --host 0.0.0.0 --port 8000; \
	fi

certs:
	./scripts/make_cert.sh

doctor:
	uv run amin doctor

eval-bench:
	uv run amin ingest --reset --provider echo
	uv run amin bench --provider echo --verifier lexical

build-eval:
	uv run python scripts/build_eval_set.py

sweep:
	# The default provider is echo; sweeping the stub re-tunes the floor to the
	# stub, which is the bug E16 exposed. Real model unless overridden.
	uv run python scripts/sweep_floor.py --provider $${PROVIDER:-ollama}

clean:
	rm -rf data/index .pytest_cache **/__pycache__

# ---------------------------------------------------------------------------
# Amin's own model (ADR-012). Each step is resumable; see docs/TRAINING.md.
# ---------------------------------------------------------------------------
# LoRA on the bf16 base, then quantize the finished model once. 8-bit is
# near-lossless; Q_BITS=4 trades a little quality for speed if the latency
# gate needs it. (Low on disk? STUDENT=mlx-community/Qwen3-8B-4bit is QLoRA.)
STUDENT ?= mlx-community/Qwen3-8B-bf16
BASE = data/models/$(notdir $(STUDENT))
Q_BITS ?= 8

train-setup:
	uv sync --extra dev --extra train
	uv run python -c "from huggingface_hub import snapshot_download as d; d('$(STUDENT)', local_dir='$(BASE)')"

train-corpus:
	uv run python scripts/build_train_corpus.py
	uv run python -m amin.train.distill index

distill:
	# Hours, not minutes: keep the Mac awake. Safe to stop and re-run.
	caffeinate -i uv run python -m amin.train.distill run
	uv run python -m amin.train.distill export

train-sft:
	uv run mlx_lm.lora -c amin/train/sft.yaml --model $(BASE)
	uv run mlx_lm.fuse --model $(BASE) --adapter-path data/adapters/amin-1-sft \
	  --save-path data/models/amin-1-sft
	uv run mlx_lm.convert --hf-path data/models/amin-1-sft --mlx-path data/models/amin-1-sft-q$(Q_BITS) \
	  -q --q-bits $(Q_BITS)

serve-student:
	uv run mlx_lm.server --model $${MODEL:-data/models/amin-3} --port 8080 $(NO_THINK)

preferences:
	# Needs `make serve-student` running in another terminal.
	caffeinate -i uv run python -m amin.train.preferences run
	uv run python -m amin.train.preferences export

train-dpo:
	uv run mlx_lm_lora.train -c amin/train/dpo.yaml
	uv run mlx_lm.fuse --model data/models/amin-1-sft --adapter-path data/adapters/amin-1-dpo \
	  --save-path data/models/amin-1-bf16
	uv run mlx_lm.convert --hf-path data/models/amin-1-bf16 --mlx-path data/models/amin-1 -q --q-bits $(Q_BITS)

bench-student:
	# The ship gate: same 237 items, same retriever, student vs teacher.
	uv run amin ingest --reset
	AMIN_PROVIDER=mlx uv run amin bench --systems amin
