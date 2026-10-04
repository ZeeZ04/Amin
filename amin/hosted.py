"""Hosted-API providers, for the day a frontier row joins the benchmark.

Not required for anything in the repo to run: the local path (Ollama/MLX) and
the offline path (echo) are complete without these. They exist so that adding a
frontier comparison is a flag and an API key, not a refactor.

Token and cost accounting is built in, because "quality per dollar" is the axis
on which a 27B model running on hardware you already own competes honestly with
an API, and it is the only axis where the comparison favours the local system by
construction. Reporting it without reporting the quality gap would be
dishonest; reporting the quality gap without it would be incomplete.

    AMIN_PROVIDER=openai  AMIN_ANSWER_MODEL=gpt-4o-mini  OPENAI_API_KEY=...
    AMIN_PROVIDER=anthropic  AMIN_ANSWER_MODEL=claude-sonnet-4-5  ANTHROPIC_API_KEY=...

`openai` also covers any OpenAI-shaped endpoint - Groq, Together, OpenRouter,
DeepSeek, a vLLM server - via AMIN_OPENAI_BASE_URL.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx
import numpy as np

from .config import settings
from .providers import HashEmbedder


@dataclass
class Usage:
    """Running token and cost total for one provider instance."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    # USD per million tokens, (input, output). Prices move; these are set from
    # config so a stale constant can never silently misreport a cost.
    rates: tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    @property
    def cost_usd(self) -> float:
        rin, rout = self.rates
        return (self.input_tokens * rin + self.output_tokens * rout) / 1_000_000

    def summary(self) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }


class MissingKey(RuntimeError):
    pass


def _key(*names: str) -> str:
    for name in names:
        if value := os.environ.get(name):
            return value
    raise MissingKey(
        f"set one of {', '.join(names)} in your environment or .env to use this provider"
    )


# ---------------------------------------------------------------------------


class OpenAICompatProvider:
    """Any OpenAI-shaped chat-completions endpoint."""

    name = "openai"

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("AMIN_OPENAI_BASE_URL")
                         or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or _key("OPENAI_API_KEY", "AMIN_API_KEY")
        self.usage = Usage(rates=(settings.price_in_per_mtok, settings.price_out_per_mtok))
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=120.0,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        self._fallback_embed = HashEmbedder()

    def _messages(self, prompt: str, system: str) -> list[dict]:
        msgs = [{"role": "system", "content": system}] if system else []
        return msgs + [{"role": "user", "content": prompt}]

    def complete(self, prompt: str, *, model: str | None = None, system: str = "") -> str:
        r = self._client.post(
            "/chat/completions",
            json={
                "model": model or settings.answer_model,
                "messages": self._messages(prompt, system),
                "temperature": settings.temperature,
            },
        )
        r.raise_for_status()
        body = r.json()
        if usage := body.get("usage"):
            self.usage.add(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        return body["choices"][0]["message"]["content"].strip()

    def stream(self, prompt: str, *, model: str | None = None, system: str = "") -> Iterator[str]:
        with self._client.stream(
            "POST",
            "/chat/completions",
            json={
                "model": model or settings.answer_model,
                "messages": self._messages(prompt, system),
                "temperature": settings.temperature,
                "stream": True,
            },
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    return
                try:
                    delta = json.loads(payload)["choices"][0]["delta"].get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embeddings stay local on purpose.

        Sending the whole corpus to an API to compare answer quality would
        change two variables at once and cost real money on every re-index. The
        benchmark swaps the generator, not the retriever.
        """
        return self._fallback_embed(texts)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or _key("ANTHROPIC_API_KEY", "AMIN_API_KEY")
        self.usage = Usage(rates=(settings.price_in_per_mtok, settings.price_out_per_mtok))
        self._client = httpx.Client(
            base_url="https://api.anthropic.com/v1",
            timeout=120.0,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        self._fallback_embed = HashEmbedder()

    def _body(self, prompt: str, model: str | None, system: str, stream: bool) -> dict:
        body = {
            "model": model or settings.answer_model,
            "max_tokens": 1024,
            "temperature": settings.temperature,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }
        if system:
            body["system"] = system
        return body

    def complete(self, prompt: str, *, model: str | None = None, system: str = "") -> str:
        r = self._client.post("/messages", json=self._body(prompt, model, system, False))
        r.raise_for_status()
        body = r.json()
        if usage := body.get("usage"):
            self.usage.add(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        return "".join(
            block.get("text", "") for block in body.get("content", []) if block.get("type") == "text"
        ).strip()

    def stream(self, prompt: str, *, model: str | None = None, system: str = "") -> Iterator[str]:
        with self._client.stream(
            "POST", "/messages", json=self._body(prompt, model, system, True)
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "content_block_delta":
                    if text := event.get("delta", {}).get("text"):
                        yield text
                elif event.get("type") == "message_stop":
                    return

    def embed(self, texts: list[str]) -> np.ndarray:
        return self._fallback_embed(texts)


HOSTED = {"openai": OpenAICompatProvider, "anthropic": AnthropicProvider}
