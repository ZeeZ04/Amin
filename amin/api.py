"""HTTP API and the household web app.

Questions are asked in a *space*: a person's general chat, or a project. Each
space has its own index, holding exactly the documents its permissions allow
(see spaces.py, ADR-013). Where its documents answer, Amin cites them; where
they don't, it answers from general knowledge, labelled as such.
The page at / is the app; everything else is JSON.

Run on the home network (HTTPS once certs exist, see scripts/make_cert.sh):
    make serve
"""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
from collections import defaultdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, history, memory, spaces, users
from .answer import Amin
from .config import settings
from .ingest import SUPPORTED, chunk_document, make_document
from .store import Store

api = FastAPI(title="Amin", version=__version__)
COOKIE = "amin_session"
MAX_UPLOAD = 25 * 1024 * 1024
WEB = Path(__file__).parent / "web" / "index.html"
api.mount("/static", StaticFiles(directory=WEB.parent), name="static")  # logo, icons, manifest

_engines: dict[str, Amin] = {}
_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)  # one SQLite user at a time
_create_lock = threading.Lock()


# -- engines and indexing ----------------------------------------------------


def _parse(path: Path, doc_id: str):
    doc, text = make_document(path, path.parent)
    doc = doc.model_copy(update={"doc_id": doc_id, "title": path.name})
    return doc, chunk_document(doc, text)


def engine(index: str) -> Amin:
    """The engine for one space, built on first use and synced to its permissions."""
    with _create_lock:
        if index not in _engines:
            _engines[index] = Amin(store=Store(spaces.index_path(index)), fallback=True)
            fresh = True
        else:
            fresh = False
    if fresh:
        sync(index)
    return _engines[index]


def sync(index: str, cache: dict | None = None) -> None:
    """Make an index hold exactly what its permissions allow, no more.

    Called after every upload, delete and permission change. Documents no
    longer allowed are deleted from the index; newly allowed ones are parsed
    and embedded (once per sync batch, via `cache`).
    """
    eng = engine(index) if index in _engines else None
    if eng is None:
        return  # built lazily; engine() syncs it on first use
    cache = {} if cache is None else cache
    want = spaces.desired_docs(index)
    with _locks[index]:
        have = eng.store.doc_ids()
        for doc_id in have - set(want):
            eng.store.delete_doc(doc_id)
        for doc_id, (_, path) in want.items():
            if doc_id in have:
                continue
            key = (doc_id, path.stat().st_mtime_ns)
            if key not in cache:
                try:
                    doc, chunks = _parse(path, doc_id)
                except Exception:
                    cache[key] = None  # unreadable file: skip it rather than lock the space out
                else:
                    vectors = eng.provider.embed([c.text for c in chunks]) if chunks else None
                    cache[key] = (doc, chunks, vectors)
            if cache[key] and cache[key][1]:
                doc, chunks, vectors = cache[key]
                eng.store.upsert([doc], chunks, vectors)


def resync(indexes: list[str]) -> None:
    cache: dict = {}
    for index in dict.fromkeys(indexes):
        sync(index, cache)


def _space(name: str, project: str | None) -> str:
    """The index this person may ask in, or 403/404."""
    if not project:
        return spaces.chat_index(name)
    p = spaces.get_project(project)
    if p is None or not p.can_open(name):
        raise HTTPException(404, "no such project")
    return spaces.project_index(p.id)


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
    project: str | None = None  # None: general chat
    conversation_id: str | None = None  # None: start a new conversation


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    grant_private: bool | None = None
    grant_household: bool | None = None
    general_chat: bool | None = None
    members: list[str] | None = None


class Prefs(BaseModel):
    chat_private: bool | None = None
    chat_household: bool | None = None


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
    # Version the stylesheet and script by content, so an update reaches every
    # browser at once instead of after its cache expires.
    html = WEB.read_text(encoding="utf-8")
    for asset in ("app.css", "app.js"):
        stamp = hashlib.sha256((WEB.parent / asset).read_bytes()).hexdigest()[:10]
        html = html.replace(f"/static/{asset}", f"/static/{asset}?v={stamp}")
    return html


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
        "people": users.names(),
        "prefs": spaces.prefs(name),
        # memory.md is managed through /memory, not as a document
        "private": sorted(p.name for p in users.docs_dir(name).iterdir() if p.name != memory.FILE),
        "household": sorted(p.name for p in users.docs_dir(users.HOUSEHOLD).iterdir()),
        "projects": [_project_view(p, name) for p in spaces.projects_for(name)],
    }


@api.patch("/me/prefs")
def set_prefs(body: Prefs, name: str = Depends(current_user)) -> dict:
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    users.set_prefs(name, **values)
    resync([spaces.chat_index(name)])
    return spaces.prefs(name)


# -- projects ----------------------------------------------------------------


def _project_view(p: spaces.Project, name: str) -> dict:
    return {
        **p.to_json(),
        "role": "owner" if p.owner == name else "member",
        "documents": sorted(f.name for f in spaces.project_docs(p.id).iterdir()),
    }


def _owned(pid: str, name: str) -> spaces.Project:
    p = spaces.get_project(pid)
    if p is None or not p.can_open(name):
        raise HTTPException(404, "no such project")
    if p.owner != name:
        raise HTTPException(403, "only the project's owner can change that")
    return p


@api.post("/projects")
def create_project(body: ProjectCreate, name: str = Depends(current_user)) -> dict:
    try:
        p = spaces.create_project(body.name, name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _project_view(p, name)


@api.patch("/projects/{pid}")
def update_project(pid: str, body: ProjectUpdate, name: str = Depends(current_user)) -> dict:
    p = _owned(pid, name)
    before = set(p.members) | {p.owner}
    if body.name is not None:
        p.name = " ".join(body.name.split())[:60]
    for flag in ("grant_private", "grant_household", "general_chat"):
        if (v := getattr(body, flag)) is not None:
            setattr(p, flag, v)
    if body.members is not None:
        known = set(users.names())
        if bad := [m for m in body.members if m not in known or m == p.owner]:
            raise HTTPException(400, f"not household members: {', '.join(bad)}")
        p.members = sorted(set(body.members))
    spaces.save_project(p)
    for gone in before - set(p.members) - {p.owner}:
        history.forget_project(gone, p.id)
    # Everyone who could open it before or can now: their chat may gain or lose it.
    people = before | set(p.members) | {p.owner}
    resync([spaces.project_index(p.id)] + [spaces.chat_index(n) for n in people])
    return _project_view(p, name)


@api.delete("/projects/{pid}")
def delete_project(pid: str, name: str = Depends(current_user)) -> dict:
    p = _owned(pid, name)
    people = set(p.members) | {p.owner}
    index = spaces.project_index(p.id)
    with _locks[index]:
        _engines.pop(index, None)
        shutil.rmtree(spaces.project_dir(p.id))
    for person in people:
        history.forget_project(person, p.id)
    resync([spaces.chat_index(n) for n in people])
    return {"deleted": p.id}


# -- documents ---------------------------------------------------------------


def _source(library: str, name: str, project: str | None, writing: str) -> spaces.Source:
    if library == "private":
        return spaces.private(name)
    if library == "household":
        if writing == "delete" and not users.is_admin(name):
            raise HTTPException(403, "only the admin can delete shared documents")
        return spaces.HOUSEHOLD
    if library == "project":
        p = spaces.get_project(project or "")
        if p is None or not p.can_open(name):
            raise HTTPException(404, "no such project")
        if writing == "delete" and p.owner != name:
            raise HTTPException(403, "only the project's owner can delete its documents")
        return spaces.project_source(p.id)
    raise HTTPException(400, "library must be 'private', 'household' or 'project'")


@api.post("/upload")
async def upload(
    filename: str,
    request: Request,
    library: str = "private",
    project: str | None = None,
    name: str = Depends(current_user),
) -> dict:
    """Raw-body upload (`?filename=lease.pdf&library=project&project=<id>`)."""
    src = _source(library, name, project, "upload")
    safe = Path(filename).name  # trust boundary: strip any directory part
    if not safe or safe.startswith(".") or Path(safe).suffix.lower() not in SUPPORTED:
        raise HTTPException(400, f"supported: {', '.join(sorted(SUPPORTED))}")
    body = await request.body()
    if not body or len(body) > MAX_UPLOAD:
        raise HTTPException(400, "file is empty or larger than 25 MB")

    path = src.folder / safe
    path.write_bytes(body)
    try:
        _, chunks = _parse(path, src.doc_id(safe))
    except Exception as exc:  # unreadable file, OCR missing: keep nothing half-indexed
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"could not read {safe}: {exc}") from exc
    if not chunks:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"no readable text in {safe}")

    readers = spaces.indexes_reading(src)
    for index in readers:
        eng = engine(index)  # make sure each reader exists, then bring them all up to date
        with _locks[index]:
            eng.store.delete_doc(src.doc_id(safe))  # a re-upload replaces the old version
    resync(readers)
    return {"document": safe, "library": library, "project": project, "chunks": len(chunks)}


@api.delete("/documents")
def delete_document(
    filename: str, library: str = "private", project: str | None = None, name: str = Depends(current_user)
) -> dict:
    src = _source(library, name, project, "delete")
    if library == "private" and Path(filename).name == memory.FILE:
        raise HTTPException(400, "manage what you told Amin under Memory")
    path = src.folder / Path(filename).name
    if not path.exists():
        raise HTTPException(404, "no such document")
    readers = spaces.indexes_reading(src)
    path.unlink()
    resync(readers)
    return {"deleted": path.name, "library": library, "project": project}


# -- asking ------------------------------------------------------------------


def _reindex_private(name: str) -> None:
    """After a memory edit: re-index memory.md everywhere it is read.

    sync() only adds documents an index lacks, and memory.md keeps its name as
    it changes, so the old copy is dropped first. Otherwise a newly taught fact
    would be missing and a forgotten one would still answer."""
    src = spaces.private(name)
    readers = spaces.indexes_reading(src)
    stale = src.doc_id(memory.FILE)
    for index in readers:
        eng = engine(index)
        with _locks[index]:
            eng.store.delete_doc(stale)
    resync(readers)


@api.post("/ask")
def ask(req: AskRequest, name: str = Depends(current_user)) -> dict:
    index = _space(name, req.project)
    if (fact := memory.taught(req.question)) is not None:
        return _remember(name, req, fact)
    eng = engine(index)
    context = history.recent(name, req.conversation_id)
    with _locks[index]:
        answer = eng.ask(req.question, context)
        cited = {cid for c in answer.claims for cid in c.cited_chunk_ids}
        found = {cid: eng.store.get_chunk(cid) for cid in cited}
    result = {
        "question": answer.question,
        "asked_as": answer.asked_as,
        "outcome": answer.outcome.value,
        "basis": "general" if answer.outcome.value == "general" else "documents",
        "routed_to": answer.routed_to,
        "refusal_reason": answer.refusal_reason,
        "claims": [
            {"text": c.text, "citations": c.cited_chunk_ids, "verdict": c.verdict.value}
            for c in answer.claims
        ],
        # What each citation chip shows without another round trip.
        "sources": {cid: {"doc_id": ch.doc_id, "heading": ch.heading} for cid, ch in found.items() if ch},
        "latency_ms": answer.latency_ms,
    }
    result["conversation_id"] = history.record(name, req.conversation_id, req.project, req.question, result)
    return result


# -- voice -------------------------------------------------------------------

MAX_AUDIO = 15 * 1024 * 1024


@api.post("/transcribe")
async def transcribe(request: Request, lang: str | None = None, name: str = Depends(current_user)) -> dict:
    """Raw-body audio from the voice mode; transcribed on this machine."""
    from .voice import VoiceUnavailable
    from .voice import transcribe as stt

    body = await request.body()
    if not body or len(body) > MAX_AUDIO:
        raise HTTPException(400, "no audio, or more than 15 MB")
    hint = lang if lang in ("en", "ar", "ml") else None
    try:
        return await run_in_threadpool(stt, body, request.headers.get("content-type", "audio/webm"), hint)
    except VoiceUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # undecodable audio
        raise HTTPException(400, f"could not read that recording: {exc}") from exc


@api.post("/wake")
async def wake(request: Request, name: str = Depends(current_user)) -> dict:
    """A short burst of speech: does it start with "Hey Amin"? (amin/voice.py)"""
    from .voice import VoiceUnavailable
    from .voice import wake as hears_wake

    body = await request.body()
    if not body or len(body) > 2 * 1024 * 1024:
        raise HTTPException(400, "no audio, or more than 2 MB")
    try:
        return await run_in_threadpool(hears_wake, body, request.headers.get("content-type", "audio/webm"))
    except VoiceUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception:
        return {"wake": False, "rest": "", "text": ""}  # an undecodable burst is not a wake


# -- memory (Teach Amin, ADR-015) -------------------------------------------


class Fact(BaseModel):
    text: str = Field(min_length=1, max_length=memory.MAX_FACT)


def _remember(name: str, req: AskRequest, fact: str) -> dict:
    """ "Remember that …" saves the fact rather than answering it, and says so."""
    try:
        item = memory.add(name, fact)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _reindex_private(name)
    result = {
        "question": req.question, "asked_as": "", "outcome": "remembered", "basis": "memory",
        "routed_to": "", "refusal_reason": f"Saved to your memory: “{item['text']}”",
        "claims": [], "sources": {}, "latency_ms": 0, "fact_id": item["id"],
    }
    result["conversation_id"] = history.record(name, req.conversation_id, req.project, req.question, result)
    return result


@api.get("/memory")
def list_memory(name: str = Depends(current_user)) -> list[dict]:
    return memory.facts(name)


@api.post("/memory")
def add_memory(fact: Fact, name: str = Depends(current_user)) -> dict:
    try:
        item = memory.add(name, fact.text)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    _reindex_private(name)
    return item


@api.delete("/memory/{fact_id}")
def delete_memory(fact_id: str, name: str = Depends(current_user)) -> dict:
    if not memory.remove(name, fact_id):
        raise HTTPException(404, "no such fact")
    _reindex_private(name)
    return {"deleted": fact_id}


# -- history -----------------------------------------------------------------


@api.get("/conversations")
def list_conversations(name: str = Depends(current_user)) -> list[dict]:
    return history.conversations(name)


@api.get("/conversations/{cid}")
def get_conversation(cid: str, name: str = Depends(current_user)) -> dict:
    conv = history.messages(name, cid)
    if conv is None:
        raise HTTPException(404, "no such conversation")
    return conv


@api.delete("/conversations/{cid}")
def delete_conversation(cid: str, name: str = Depends(current_user)) -> dict:
    if not history.delete(name, cid):
        raise HTTPException(404, "no such conversation")
    return {"deleted": cid}


@api.get("/chunks/{chunk_id}")
def chunk(chunk_id: str, project: str | None = None, name: str = Depends(current_user)) -> dict:
    index = _space(name, project)
    eng = engine(index)
    with _locks[index]:
        found = eng.store.get_chunk(chunk_id)
    if found is None:
        raise HTTPException(404, "no such chunk")
    return {"doc_id": found.doc_id, "heading": found.heading, "text": found.text}


@api.get("/health")
def health() -> dict:
    return {"version": __version__, "provider": settings.provider, "answer_model": settings.model_label}


@api.get("/metrics")
def metrics() -> dict:
    """The most recent eval report. Amin publishes its own error rate."""
    reports = sorted(Path("reports").glob("eval-*.json"))
    if not reports:
        raise HTTPException(404, "no eval report yet - run `amin eval`")
    data = json.loads(reports[-1].read_text(encoding="utf-8"))
    return {"timestamp": data["timestamp"], "config": data["config"], "metrics": data["metrics"]}
