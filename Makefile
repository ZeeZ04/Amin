.PHONY: install ingest eval ask test lint serve doctor clean sweep

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
	uv run uvicorn amin.api:api --reload --port 8000

doctor:
	uv run amin doctor

sweep:
	uv run python scripts/sweep_floor.py

clean:
	rm -rf data/index .pytest_cache **/__pycache__
