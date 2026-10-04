"""Configuration. Everything overridable by env var or .env, nothing hardcoded in logic."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AMIN_", env_file=".env", extra="ignore")

    # -- provider ------------------------------------------------------------
    provider: str = "ollama"  # ollama | echo | mlx
    ollama_host: str = "http://127.0.0.1:11434"
    answer_model: str = "qwen3.6:27b"
    # A small fast model does the mechanical work: query rewriting and verification.
    utility_model: str = "qwen3:8b"
    embed_model: str = "nomic-embed-text"
    temperature: float = 0.1
    num_ctx: int = 8192

    # -- storage -------------------------------------------------------------
    index_path: Path = REPO_ROOT / "data" / "index" / "amin.db"
    corpus_path: Path = REPO_ROOT / "data" / "corpus"
    private_path: Path = REPO_ROOT / "private"
    eval_set: Path = REPO_ROOT / "data" / "eval" / "eval_set.jsonl"
    policy_path: Path = Path(__file__).parent / "policy.yaml"

    # -- chunking ------------------------------------------------------------
    chunk_chars: int = 900
    chunk_overlap: int = 150

    # -- retrieval -----------------------------------------------------------
    top_k_dense: int = 12
    top_k_lexical: int = 12
    top_k_final: int = 6
    rrf_k: int = 60
    # Minimum IDF-weighted share of the question's distinctive terms that some
    # retrieved chunk must contain before Amin will answer at all. This single
    # number is the main dial between "refuses too often" and "answers from
    # nothing", and it is tuned by the eval harness, not by vibes.
    # See docs/EXPERIMENTS.md for the sweep that chose this value.
    evidence_floor: float = 0.45

    # -- hosted-API pricing, for the cost column in the benchmark ------------
    # USD per million tokens. Left at zero so a local run never reports a
    # fabricated cost; set them when adding a hosted row, from that provider's
    # current price page rather than from a constant in this repo.
    price_in_per_mtok: float = 0.0
    price_out_per_mtok: float = 0.0

    # -- verification --------------------------------------------------------
    verifier: str = "llm"  # llm | lexical | off
    lexical_overlap_floor: float = 0.28
    # Refuse rather than return an answer whose claims mostly failed the check.
    min_citation_precision: float = 0.5


settings = Settings()
