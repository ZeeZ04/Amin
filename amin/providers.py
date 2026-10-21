"""Model providers behind one small interface.

The model is a replaceable part. A better open model lands roughly every
quarter, so nothing above this module is allowed to know which one is running.

`EchoProvider` exists so the whole pipeline, including the eval harness, runs
deterministically in CI with no model and no network.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from typing import Protocol, runtime_checkable

import httpx
import numpy as np

from .config import settings


@runtime_checkable
class Provider(Protocol):
    name: str

    def complete(self, prompt: str, *, model: str | None = None, system: str = "") -> str: ...

    def stream(self, prompt: str, *, model: str | None = None, system: str = "") -> Iterator[str]: ...

    def embed(self, texts: list[str]) -> np.ndarray: ...


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


class OllamaProvider:
    name = "ollama"

    def __init__(self, host: str | None = None, timeout: float | None = None):
        self.host = (host or settings.ollama_host).rstrip("/")
        self._client = httpx.Client(base_url=self.host, timeout=timeout or settings.request_timeout)

    def _payload(self, prompt: str, model: str | None, system: str, stream: bool) -> dict:
        return {
            "model": model or settings.answer_model,
            "prompt": prompt,
            "system": system,
            "stream": stream,
            "think": settings.think,
            "options": {"temperature": settings.temperature, "num_ctx": settings.num_ctx},
        }

    def complete(self, prompt: str, *, model: str | None = None, system: str = "") -> str:
        r = self._client.post("/api/generate", json=self._payload(prompt, model, system, False))
        r.raise_for_status()
        return r.json().get("response", "").strip()

    def stream(self, prompt: str, *, model: str | None = None, system: str = "") -> Iterator[str]:
        with self._client.stream(
            "POST", "/api/generate", json=self._payload(prompt, model, system, True)
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk := obj.get("response"):
                    yield chunk
                if obj.get("done"):
                    return

    def embed(self, texts: list[str]) -> np.ndarray:
        out = []
        for t in texts:
            r = self._client.post(
                "/api/embeddings", json={"model": settings.embed_model, "prompt": t}
            )
            r.raise_for_status()
            out.append(r.json()["embedding"])
        return _l2(np.asarray(out, dtype=np.float32))

    def available(self) -> bool:
        try:
            return self._client.get("/api/tags", timeout=3.0).status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# MLX — Apple-native path, serves Amin's own post-trained model (ADR-012)
# ---------------------------------------------------------------------------

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.S)


class MLXProvider:
    """Thin wrapper over an `mlx_lm.server` running locally.

    mlx_lm exposes an OpenAI-compatible endpoint, so this is deliberately
    boring. Start it with (`make serve-student`):
        mlx_lm.server --model data/models/amin-1 --port 8080 \
          --chat-template-args '{"enable_thinking": false}'
    """

    name = "mlx"
    # One server serves one model, whatever `model=` a caller asks for: the
    # student replaces both answer_model and utility_model. Requests name the
    # server's default so it never tries to load an Ollama tag as a path.
    model_label = settings.mlx_model

    def __init__(
        self, host: str | None = None, timeout: float | None = None, temperature: float | None = None
    ):
        self.host = (host or settings.mlx_host).rstrip("/")
        self._client = httpx.Client(base_url=self.host, timeout=timeout or settings.request_timeout)
        self.temperature = settings.temperature if temperature is None else temperature
        self._embedder: Provider | None = None

    def _messages(self, prompt: str, system: str) -> list[dict]:
        msgs = [{"role": "system", "content": system}] if system else []
        return msgs + [{"role": "user", "content": prompt}]

    def complete(self, prompt: str, *, model: str | None = None, system: str = "") -> str:
        r = self._client.post(
            "/v1/chat/completions",
            json={
                "model": "default_model",
                "messages": self._messages(prompt, system),
                "temperature": self.temperature,
                "max_tokens": 1024,
                "stream": False,
            },
        )
        r.raise_for_status()
        # Thinking is off in the server's template and in training, but a
        # stray empty block must never reach the citation parser.
        return _THINK_RE.sub("", r.json()["choices"][0]["message"]["content"]).strip()

    def stream(self, prompt: str, *, model: str | None = None, system: str = "") -> Iterator[str]:
        with self._client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "default_model",
                "messages": self._messages(prompt, system),
                "temperature": self.temperature,
                "max_tokens": 1024,
                "stream": True,
            },
        ) as r:
            r.raise_for_status()
            pending = ""  # held back while it could still be an opening <think>
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                body = line[6:]
                if body.strip() == "[DONE]":
                    return
                try:
                    delta = json.loads(body)["choices"][0]["delta"].get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if not delta:
                    continue
                if pending is not None:
                    pending += delta
                    if "<think>".startswith(pending.lstrip()) and pending.strip():
                        continue
                    if pending.lstrip().startswith("<think>"):
                        if "</think>" not in pending:
                            continue
                        pending = pending.split("</think>", 1)[1].lstrip()
                    delta, pending = pending, None
                    if not delta:
                        continue
                yield delta

    def embed(self, texts: list[str]) -> np.ndarray:
        # mlx_lm.server does not serve embeddings. Retrieval stays on Ollama's
        # embed model so an index built for the teacher serves the student
        # unchanged - a bench against a hashed index would compare retrievers,
        # not models.
        if self._embedder is None:
            self._embedder = OllamaProvider()
        return self._embedder.embed(texts)

    def available(self) -> bool:
        try:
            return self._client.get("/v1/models", timeout=3.0).status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Echo — deterministic, offline, for tests and CI
# ---------------------------------------------------------------------------


class EchoProvider:
    """Answers only from the passages in the prompt, by extraction.

    This is not a language model and does not pretend to be one. Its job is to
    let every component above it be tested for *behaviour* (does it cite? does
    it refuse?) without a 18 GB download in CI.
    """

    name = "echo"

    def __init__(self):
        self._embed = HashEmbedder()

    def complete(self, prompt: str, *, model: str | None = None, system: str = "") -> str:
        # Verification sub-prompts: answer by lexical overlap.
        if "VERIFY" in prompt:
            claim = _between(prompt, "<claim>", "</claim>")
            passage = _between(prompt, "<passage>", "</passage>")
            return "YES" if _overlap(claim, passage) >= settings.lexical_overlap_floor else "NO"

        passages = re.findall(
            r"\[(S\d+)\][^\n]*\n(.*?)(?=\n\[S\d+\]|\Z)", prompt.split("<question>")[0], re.S
        )
        if not passages:
            return "NO_EVIDENCE"
        question = _between(prompt, "<question>", "</question>") or prompt[-300:]
        best, best_score = None, 0.0
        for tag, body in passages:
            s = _overlap(question, body)
            if s > best_score:
                best, best_score = (tag, body), s
        if best is None or best_score < 0.05:
            return "NO_EVIDENCE"
        tag, body = best
        sentence = next(
            (s for s in _sentences(body) if _overlap(question, s) > 0.08), _sentences(body)[0]
        )
        return f"{sentence.rstrip('.')} [{tag}]."

    def stream(self, prompt: str, *, model: str | None = None, system: str = "") -> Iterator[str]:
        yield self.complete(prompt, model=model, system=system)

    def embed(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts)


class HashEmbedder:
    """Deterministic bag-of-words hashing embedder. No model, no network.

    Good enough to make dense retrieval *work* in tests; genuinely worse than a
    real embedding model, which is why it is never the default outside CI.
    """

    def __init__(self, dim: int = 512):
        self.dim = dim

    def __call__(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in _tokens(t):
                h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=4).digest(), "big")
                out[i, h % self.dim] += 1.0
        return _l2(out)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_ARABIC = r"؀-ۿ"
_TOKEN_RE = re.compile(rf"[A-Za-z0-9{_ARABIC}]+")
_DIACRITICS = re.compile(r"[ً-ْٰـ]")

# Function words carry no evidence. Shared by the retriever's coverage gate and
# the verifier, so "does this passage support this claim" and "does the corpus
# cover this question" are judged on the same vocabulary.
STOPWORDS = frozenset(
    """a an the of to in is are was were be been being and or for on at by with from that this
    these those it its as if then than you your we our they their he she his her not no but so do
    does did can could will would shall should may might must have has had there here what which
    who whom whose when where why how any all each more most other some such only own same also
    per about into over under between after before during while because very much many how long
    i me my mine us them one two""".split()
)


def _tokens(text: str) -> list[str]:
    text = _DIACRITICS.sub("", text.lower())
    # Normalise alef/ya/ta-marbuta variants so Arabic retrieval does not miss
    # on orthographic noise. Cheap, and it measurably helps.
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"}))
    return _TOKEN_RE.findall(text)


def _l2(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.maximum(n, 1e-9)


def _overlap(a: str, b: str) -> float:
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)


_SENT_RE = re.compile(r"(?<=[.!?؟۔])\s+|\n+")


def _sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENT_RE.split(text.strip()) if s.strip()]
    return parts or [text.strip()]


def _between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    j = text.find(end, i + len(start)) if i >= 0 else -1
    return text[i + len(start) : j].strip() if i >= 0 and j > i else ""


def content_tokens(text: str) -> set[str]:
    """Tokens that can carry evidence: no function words, no single characters."""
    return {t for t in _tokens(text) if t not in STOPWORDS and len(t) > 1}


class AutoProvider:
    """Amin's own model when its server is up, the Ollama model when not.

    Decided per call, not at startup: if mlx_lm.server stops or starts while
    the app runs, answers follow without a restart. Embeddings always come
    from Ollama, as for the MLX provider, so the index never changes.
    """

    RECHECK_S = 30.0

    def __init__(self):
        self.mlx = MLXProvider()
        self.ollama = OllamaProvider()
        self._up: bool | None = None
        self._checked = 0.0
        self._last = self.mlx

    def _mlx_up(self) -> bool:
        import time

        now = time.monotonic()
        if self._up is None or now - self._checked > self.RECHECK_S:
            self._up, self._checked = self.mlx.available(), now
        return bool(self._up)

    def _pick(self) -> Provider:
        self._last = self.mlx if self._mlx_up() else self.ollama
        return self._last

    @property
    def name(self) -> str:
        return self._last.name

    @property
    def model_label(self) -> str:
        return settings.mlx_model if self._last is self.mlx else settings.answer_model

    def complete(self, prompt: str, *, model: str | None = None, system: str = "") -> str:
        prov = self._pick()
        try:
            return prov.complete(prompt, model=model, system=system)
        except httpx.TransportError:
            if prov is self.ollama:
                raise
            self._up, self._last = False, self.ollama  # it went away mid-run
            return self.ollama.complete(prompt, model=model, system=system)

    def stream(self, prompt: str, *, model: str | None = None, system: str = "") -> Iterator[str]:
        yield from self._pick().stream(prompt, model=model, system=system)

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.ollama.embed(texts)


def get_provider(kind: str | None = None) -> Provider:
    kind = (kind or settings.provider).lower()
    if kind == "echo":
        return EchoProvider()
    if kind == "auto":
        return AutoProvider()
    if kind == "mlx":
        return MLXProvider()
    if kind == "ollama":
        return OllamaProvider()
    if kind in ("openai", "anthropic"):
        from .hosted import HOSTED

        return HOSTED[kind]()
    raise ValueError(
        f"unknown provider {kind!r} (expected auto | ollama | mlx | echo | openai | anthropic)"
    )
