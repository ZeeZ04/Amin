"""HTTP API.

Deliberately small: a chat endpoint that returns the structured answer (not a
text blob), a sources endpoint so the client can show the quoted passage behind
any citation, and a metrics endpoint that serves the last eval report — because
a system that claims to be trustworthy should publish its own error rate.

Run:  uvicorn amin.api:api --reload --port 8000
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import __version__
from .answer import Amin
from .config import settings
from .store import Store

api = FastAPI(title="Amin", version=__version__)
api.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_amin: Amin | None = None


def engine() -> Amin:
    global _amin
    if _amin is None:
        _amin = Amin()
    return _amin


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@api.get("/health")
def health() -> dict:
    try:
        stats = Store().stats()
    except Exception as exc:
        raise HTTPException(503, f"index unavailable: {exc}") from exc
    return {
        "version": __version__,
        "provider": settings.provider,
        "answer_model": settings.answer_model,
        "index": stats,
    }


@api.post("/ask")
def ask(req: AskRequest) -> dict:
    answer = engine().ask(req.question)
    return {
        "question": answer.question,
        "outcome": answer.outcome.value,
        "routed_to": answer.routed_to,
        "refusal_reason": answer.refusal_reason,
        "claims": [
            {
                "text": c.text,
                "citations": c.cited_chunk_ids,
                "verdict": c.verdict.value,
            }
            for c in answer.claims
        ],
        "sources": answer.sources(),
        "citation_precision": answer.citation_precision,
        "latency_ms": answer.latency_ms,
        "model": answer.model,
    }


@api.get("/chunks/{chunk_id}")
def chunk(chunk_id: str) -> dict:
    found = Store().get_chunk(chunk_id)
    if found is None:
        raise HTTPException(404, "no such chunk")
    return {
        "chunk_id": found.chunk_id,
        "doc_id": found.doc_id,
        "heading": found.heading,
        "tier": found.tier.label,
        "text": found.text,
    }


@api.get("/metrics")
def metrics() -> dict:
    """The most recent eval report. Amin publishes its own error rate."""
    reports = sorted(Path("reports").glob("eval-*.json"))
    if not reports:
        raise HTTPException(404, "no eval report yet - run `amin eval`")
    data = json.loads(reports[-1].read_text(encoding="utf-8"))
    return {"timestamp": data["timestamp"], "config": data["config"], "metrics": data["metrics"]}
