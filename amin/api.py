"""HTTP API and the household web app.

Each signed-in person talks to their own engine, built on their own index
(see users.py). The page at / is the app; everything else is JSON.

Run on the home network:
    uv run uvicorn amin.api:api --host 0.0.0.0 --port 8000
then open http://<this-mac's-name>.local:8000 on any phone in the house.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import __version__, users
from .answer import Amin
from .config import settings
from .ingest import SUPPORTED, chunk_document, make_document
from .store import Store

api = FastAPI(title="Amin", version=__version__)
COOKIE = "amin_session"
MAX_UPLOAD = 25 * 1024 * 1024
WEB = Path(__file__).parent / "web" / "index.html"

_engines: dict[str, Amin] = {}
_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)  # one SQLite user at a time


def engine(name: str) -> Amin:
    if name not in _engines:
        _engines[name] = Amin(store=Store(users.index_path(name)))
    return _engines[name]


def current_user(request: Request) -> str:
    name = users.read_token(request.cookies.get(COOKIE))
    if not name:
        raise HTTPException(401, "sign in first")
    return name


class Credentials(BaseModel):
    name: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=200)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def _sign_in(response: Response, name: str) -> dict:
    response.set_cookie(
        COOKIE, users.make_token(name), httponly=True, samesite="strict", max_age=60 * 60 * 24 * 90
    )
    return {"name": name}


@api.get("/", response_class=HTMLResponse)
def app_page() -> str:
    return WEB.read_text(encoding="utf-8")


@api.post("/signup")
def signup(creds: Credentials, response: Response) -> dict:
    try:
        users.create(creds.name, creds.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _sign_in(response, creds.name.strip().lower())


@api.post("/login")
def login(creds: Credentials, response: Response) -> dict:
    if not users.verify(creds.name, creds.password):
        raise HTTPException(401, "wrong name or password")
    return _sign_in(response, creds.name.strip().lower())


@api.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE)
    return {"ok": True}


@api.get("/me")
def me(name: str = Depends(current_user)) -> dict:
    return {"name": name, "documents": sorted(p.name for p in users.docs_dir(name).iterdir())}


@api.post("/upload")
async def upload(filename: str, request: Request, name: str = Depends(current_user)) -> dict:
    """Raw-body upload (`?filename=lease.pdf`), so no multipart dependency."""
    safe = Path(filename).name  # trust boundary: strip any directory part
    if Path(safe).suffix.lower() not in SUPPORTED:
        raise HTTPException(400, f"supported: {', '.join(sorted(SUPPORTED))}")
    body = await request.body()
    if not body or len(body) > MAX_UPLOAD:
        raise HTTPException(400, "file is empty or larger than 25 MB")

    with _locks[name]:
        return _index_upload(name, safe, body)


def _index_upload(name: str, safe: str, body: bytes) -> dict:
    folder = users.docs_dir(name)
    path = folder / safe
    path.write_bytes(body)
    eng = engine(name)
    try:
        doc, text = make_document(path, folder)
        chunks = chunk_document(doc, text)
    except Exception as exc:  # unreadable PDF, wrong encoding: keep nothing half-indexed
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"could not read {safe}: {exc}") from exc
    if not chunks:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"no text found in {safe} (scanned image? OCR is not supported yet)")
    eng.store.upsert([doc], chunks, eng.provider.embed([c.text for c in chunks]))
    return {"document": safe, "chunks": len(chunks)}


@api.post("/ask")
def ask(req: AskRequest, name: str = Depends(current_user)) -> dict:
    with _locks[name]:
        answer = engine(name).ask(req.question)
    return {
        "question": answer.question,
        "outcome": answer.outcome.value,
        "routed_to": answer.routed_to,
        "refusal_reason": answer.refusal_reason,
        "claims": [
            {"text": c.text, "citations": c.cited_chunk_ids, "verdict": c.verdict.value}
            for c in answer.claims
        ],
        "sources": answer.sources(),
        "latency_ms": answer.latency_ms,
    }


@api.get("/chunks/{chunk_id}")
def chunk(chunk_id: str, name: str = Depends(current_user)) -> dict:
    with _locks[name]:
        found = engine(name).store.get_chunk(chunk_id)
    if found is None:
        raise HTTPException(404, "no such chunk")
    return {"doc_id": found.doc_id, "heading": found.heading, "text": found.text}


@api.get("/health")
def health() -> dict:
    return {
        "version": __version__,
        "provider": settings.provider,
        "answer_model": settings.answer_model,
    }


@api.get("/metrics")
def metrics() -> dict:
    """The most recent eval report. Amin publishes its own error rate."""
    reports = sorted(Path("reports").glob("eval-*.json"))
    if not reports:
        raise HTTPException(404, "no eval report yet - run `amin eval`")
    data = json.loads(reports[-1].read_text(encoding="utf-8"))
    return {"timestamp": data["timestamp"], "config": data["config"], "metrics": data["metrics"]}
