.PHONY: install ingest eval ask test lint serve doctor clean sweep certs

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
