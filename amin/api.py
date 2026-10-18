"""HTTP API and the household web app.

Each signed-in person talks to their own engine, built on their own index:
their private documents plus the shared household library (see users.py).
The page at / is the app; everything else is JSON.

Run on the home network (HTTPS once certs exist, see scripts/make_cert.sh):
    make serve
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
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
api.mount("/static", StaticFiles(directory=WEB.parent), name="static")  # logo, icons, manifest
PREFIX = {"private": "p.", "household": "h."}

_engines: dict[str, Amin] = {}
_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)  # one SQLite user at a time
_create_lock = threading.Lock()


# -- engines and indexing ----------------------------------------------------


def _parse(path: Path, folder: Path, doc_id: str):
    doc, text = make_document(path, folder)
    doc = doc.model_copy(update={"doc_id": doc_id, "title": path.name})
    return doc, chunk_document(doc, text)


def engine(name: str) -> Amin:
    with _create_lock:
        if name not in _engines:
            eng = Amin(store=Store(users.index_path(name)))
            _engines[name] = eng
            _sync_household(name, eng)
    return _engines[name]


def _sync_household(name: str, eng: Amin) -> None:
    """A new member (or an index rebuilt from scratch) gets every shared document."""
    folder = users.docs_dir(users.HOUSEHOLD)
    have = eng.store.doc_ids()
    for path in sorted(folder.iterdir()):
        doc_id = PREFIX["household"] + path.name
        if doc_id in have:
            continue
        try:
            doc, chunks = _parse(path, folder, doc_id)
        except Exception:
            continue  # unreadable shared file: skip it rather than lock this member out
        if chunks:
            eng.store.upsert([doc], chunks, eng.provider.embed([c.text for c in chunks]))


def current_user(request: Request) -> str:
    name = users.read_token(request.cookies.get(COOKIE))
    if not name:
        raise HTTPException(401, "sign in first")
    return name


def admin_user(name: str = Depends(current_user)) -> str:
    if not users.is_admin(name):
        raise HTTPException(403, "only the admin can do that")
    return name


# -- accounts ----------------------------------------------------------------


class Credentials(BaseModel):
    name: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=200)
    invite: str | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def _sign_in(request: Request, response: Response, name: str) -> dict:
    response.set_cookie(
        COOKIE,
        users.make_token(name),
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=60 * 60 * 24 * 90,
    )
    return {"name": name}


@api.get("/", response_class=HTMLResponse)
def app_page() -> str:
    return WEB.read_text(encoding="utf-8")


@api.get("/setup")
def setup_state() -> dict:
    """Lets the sign-in page know whether the next account is the admin."""
    return {"first_account": not users.names()}


@api.post("/signup")
def signup(creds: Credentials, request: Request, response: Response) -> dict:
    try:
        users.create(creds.name, creds.password, creds.invite)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _sign_in(request, response, creds.name.strip().lower())


@api.post("/login")
def login(creds: Credentials, request: Request, response: Response) -> dict:
    if not users.verify(creds.name, creds.password):
        raise HTTPException(401, "wrong name or password")
    return _sign_in(request, response, creds.name.strip().lower())


@api.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE)
    return {"ok": True}


@api.post("/logout-all")
def logout_all(response: Response, name: str = Depends(current_user)) -> dict:
    users.sign_out_everywhere(name)
    response.delete_cookie(COOKIE)
    return {"ok": True}


@api.post("/invites")
def invite(_: str = Depends(admin_user)) -> dict:
    return {"code": users.new_invite(), "valid_days": users.INVITE_TTL // 86400}


@api.get("/me")
def me(name: str = Depends(current_user)) -> dict:
    return {
        "name": name,
        "admin": users.is_admin(name),
        "private": sorted(p.name for p in users.docs_dir(name).iterdir()),
        "household": sorted(p.name for p in users.docs_dir(users.HOUSEHOLD).iterdir()),
    }


# -- documents ---------------------------------------------------------------


def _owner(library: str, name: str) -> str:
    if library not in PREFIX:
        raise HTTPException(400, "library must be 'private' or 'household'")
    return name if library == "private" else users.HOUSEHOLD


def _members(library: str, name: str) -> list[str]:
    """Whose index a document in this library lives in."""
    return [name] if library == "private" else users.names()


@api.post("/upload")
async def upload(
    filename: str, request: Request, library: str = "private", name: str = Depends(current_user)
) -> dict:
    """Raw-body upload (`?filename=lease.pdf&library=household`): no multipart dependency."""
    owner = _owner(library, name)
    safe = Path(filename).name  # trust boundary: strip any directory part
    if not safe or Path(safe).suffix.lower() not in SUPPORTED:
        raise HTTPException(400, f"supported: {', '.join(sorted(SUPPORTED))}")
    body = await request.body()
    if not body or len(body) > MAX_UPLOAD:
        raise HTTPException(400, "file is empty or larger than 25 MB")

    folder = users.docs_dir(owner)
    path = folder / safe
    path.write_bytes(body)
    try:
        doc, chunks = _parse(path, folder, PREFIX[library] + safe)
    except Exception as exc:  # unreadable file, OCR missing: keep nothing half-indexed
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"could not read {safe}: {exc}") from exc
    if not chunks:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"no readable text in {safe}")

    vectors = engine(name).provider.embed([c.text for c in chunks])  # embed once, index everywhere
    for member in _members(library, name):
        with _locks[member]:
            engine(member).store.upsert([doc], chunks, vectors)
    return {"document": safe, "library": library, "chunks": len(chunks)}


@api.delete("/documents")
def delete_document(filename: str, library: str = "private", name: str = Depends(current_user)) -> dict:
    owner = _owner(library, name)
    if library == "household" and not users.is_admin(name):
        raise HTTPException(403, "only the admin can delete shared documents")
    path = users.docs_dir(owner) / Path(filename).name
    if not path.exists():
        raise HTTPException(404, "no such document")
    for member in _members(library, name):
        with _locks[member]:
            engine(member).store.delete_doc(PREFIX[library] + path.name)
    path.unlink()
    return {"deleted": path.name, "library": library}


# -- asking ------------------------------------------------------------------


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
    model = settings.mlx_model if settings.provider == "mlx" else settings.answer_model
    return {"version": __version__, "provider": settings.provider, "answer_model": model}


@api.get("/metrics")
def metrics() -> dict:
    """The most recent eval report. Amin publishes its own error rate."""
    reports = sorted(Path("reports").glob("eval-*.json"))
    if not reports:
        raise HTTPException(404, "no eval report yet - run `amin eval`")
    data = json.loads(reports[-1].read_text(encoding="utf-8"))
    return {"timestamp": data["timestamp"], "config": data["config"], "metrics": data["metrics"]}
