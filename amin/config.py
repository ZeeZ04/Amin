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
    # Qwen3 "thinks" before answering unless told not to. At ~9 tok/s on the
    # 27B that reasoning alone can exceed the request timeout, and the eval
    # measures grounding, not long reasoning. Off by default; AMIN_THINK=1 to
    # measure what it buys. (E16: the amin row died on a 180s ReadTimeout.)
    think: bool = False
    request_timeout: float = 600.0
    # mlx_lm.server, which serves Amin's own post-trained model (ADR-012).
    mlx_host: str = "http://127.0.0.1:8080"
    # Label only: shown in answers and /health. The server decides what it loads.
    mlx_model: str = "amin-1"

    # -- post-training (amin/train, ADR-012) ---------------------------------
    # The teacher is whatever answer_model is; the student is what gets tuned.
    student_model: str = "mlx-community/Qwen3-8B-bf16"
    train_path: Path = REPO_ROOT / "data" / "train"

    # -- storage -------------------------------------------------------------
    index_path: Path = REPO_ROOT / "data" / "index" / "amin.db"
    corpus_path: Path = REPO_ROOT / "data" / "corpus"
    private_path: Path = REPO_ROOT / "private"
    # One folder per household account: documents + index. Never committed.
    users_path: Path = REPO_ROOT / "data" / "users"
    eval_set: Path = REPO_ROOT / "data" / "eval" / "eval_set.jsonl"
    policy_path: Path = Path(__file__).parent / "policy.yaml"

    # -- chunking ------------------------------------------------------------
    chunk_chars: int = 900
    chunk_overlap: int = 150

    # -- retrieval -----------------------------------------------------------
    top_k_dense: int = 12
    top_k_lexical: int = 12
    top_k_final: int = 6
    # Conflict detection looks deeper than generation does: a contradicting
    # passage sitting at rank 7 is exactly the one that must not be missed,
    # and checking it costs no model call.
    top_k_conflict: int = 14
    # A chunk joins the conflict comparison if its coverage is at least this
    # fraction of the best coverage seen. Tuned in docs/EXPERIMENTS.md E14
    # against the whole eval set, counting false conflicts on answerable items -
    # not against the conflict items alone, which would reward over-firing.
    conflict_relative_floor: float = 0.7
    conflict_min_coverage: float = 0.25
    rrf_k: int = 60
    # Minimum IDF-weighted share of the question's distinctive terms that some
    # retrieved chunk must contain before Amin will answer at all. This single
    # number is the main dial between "refuses too often" and "answers from
    # nothing", and it is tuned by the eval harness, not by vibes.
    # See docs/EXPERIMENTS.md for the sweep that chose this value.
    # 0.45 was tuned on the echo stub. Re-swept on qwen3.6:27b in E16: 0.15.
    evidence_floor: float = 0.15
    # Refuse when the question names an identifier (FR-550, PHY-205) that no
    # retrieved chunk contains. E16: catches 13/99 unanswerables, 0/110
    # answerables blocked, model-free. See covenant.missing_identifiers.
    identifier_gate: bool = True
    # Multiplier applied to a chunk from a document marked `status: superseded`.
    # Strong enough to lose a tie, too weak to hide a clearly better match.
    superseded_penalty: float = 0.7

    # -- hosted-API pricing, for the cost column in the benchmark ------------
    # USD per million tokens. Left at zero so a local run never reports a
    # fabricated cost; set them when adding a hosted row, from that provider's
    # current price page rather than from a constant in this repo.
    price_in_per_mtok: float = 0.0
    price_out_per_mtok: float = 0.0

    # -- verification --------------------------------------------------------
    # Off by default since E19: on qwen3.6:27b it rejected 5 correct answers
    # (3 refusals, 2 answers stripped to a fragment) to stop 1 hallucination.
    # Citations stay 100% precise without it. Re-test on a smaller model.
    verifier: str = "off"  # llm | lexical | off
    lexical_overlap_floor: float = 0.28
    # Refuse rather than return an answer whose claims mostly failed the check.
    min_citation_precision: float = 0.5

    @property
    def model_label(self) -> str:
        """The model actually answering: the MLX server's, not the Ollama tag."""
        return self.mlx_model if self.provider == "mlx" else self.answer_model


settings = Settings()
