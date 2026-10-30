"""Memory spaces: where documents live and who may search them (ADR-013).

A *source* is a folder of documents:

    private:<user>     the user's own library
    household          the shared household library
    project:<id>       one project's documents

An *index* is what a question is asked against, and each index subscribes to
sources by permission:

    chat:<user>        the user's general chat. Their private library and the
                       household library (each switchable in their settings),
                       plus every project they can open whose owner allowed
                       "general chat may use this project".
    project:<id>       the project's documents, plus the owner's private
                       library and/or the household library if the owner
                       granted them.

Every permission is off by default except the user's own libraries in their
own chat. Documents are copied into each subscribing index (the household
library always worked this way), so a revoked permission is a deletion, not a
filter that a bug could skip. `sync()` makes one index match its permissions.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import users

PROJECTS = "_projects"
DEFAULT_PREFS = {"chat_private": True, "chat_household": True}


# ---------------------------------------------------------------------------
# projects
# ---------------------------------------------------------------------------


@dataclass
class Project:
    id: str
    name: str
    owner: str
    created: float
    members: list[str] = field(default_factory=list)  # besides the owner
    # Sources the owner lets this project search, beyond its own documents.
    grant_private: bool = False
    grant_household: bool = False
    # May the general chat of everyone with access search this project?
    general_chat: bool = False

    def can_open(self, name: str) -> bool:
        return name == self.owner or name in self.members

    def to_json(self) -> dict:
        return dict(self.__dict__)


def projects_root() -> Path:
    path = users.root() / PROJECTS
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_dir(pid: str) -> Path:
    if not pid.isalnum():  # trust boundary: becomes a path
        raise ValueError("bad project id")
    return projects_root() / pid


def _meta(pid: str) -> Path:
    return project_dir(pid) / "project.json"


def get_project(pid: str) -> Project | None:
    try:
        f = _meta(pid)
    except ValueError:
        return None
    return Project(**json.loads(f.read_text())) if f.exists() else None


def save_project(p: Project) -> None:
    f = _meta(p.id)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(p.to_json(), indent=2))
    tmp.chmod(0o600)
    tmp.replace(f)


def create_project(name: str, owner: str) -> Project:
    name = " ".join(name.split())[:60]
    if not name:
        raise ValueError("a project needs a name")
    p = Project(id=secrets.token_hex(5), name=name, owner=owner, created=time.time())
    save_project(p)
    project_docs(p.id)
    return p


def all_projects() -> list[Project]:
    out = []
    for d in sorted(projects_root().iterdir()):
        if d.is_dir() and (p := get_project(d.name)):
            out.append(p)
    return out


def projects_for(name: str) -> list[Project]:
    return [p for p in all_projects() if p.can_open(name)]


def project_docs(pid: str) -> Path:
    path = project_dir(pid) / "docs"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# preferences
# ---------------------------------------------------------------------------


def prefs(name: str) -> dict:
    return {**DEFAULT_PREFS, **users.get_prefs(name)}


# ---------------------------------------------------------------------------
# sources and indexes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Source:
    kind: str  # private | household | project | pack
    key: str  # user name, "", project id, or pack name

    @property
    def folder(self) -> Path:
        if self.kind == "private":
            return users.docs_dir(self.key)
        if self.kind == "household":
            return users.docs_dir(users.HOUSEHOLD)
        if self.kind == "pack":
            from . import packs

            return packs.folder(self.key)
        return project_docs(self.key)

    @property
    def prefix(self) -> str:
        # "p." and "h." are the prefixes indexes already hold; keep them.
        if self.kind == "pack":
            return f"k.{self.key}."
        return {"private": "p.", "household": "h."}.get(self.kind, f"j.{self.key}.")

    def doc_id(self, filename: str) -> str:
        return self.prefix + filename


def private(name: str) -> Source:
    return Source("private", name)


HOUSEHOLD = Source("household", "")


def project_source(pid: str) -> Source:
    return Source("project", pid)


def chat_index(name: str) -> str:
    return f"chat:{name}"


def project_index(pid: str) -> str:
    return f"project:{pid}"


def index_path(index: str) -> Path:
    kind, key = index.split(":", 1)
    if kind == "chat":
        return users.index_path(key)  # the index every user already has
    return project_dir(key) / "amin.db"


def sources_of(index: str) -> list[Source]:
    """What this index may search, by the permissions as they stand now."""
    kind, key = index.split(":", 1)
    if kind == "chat":
        pref = prefs(key)
        out = []
        if pref["chat_private"]:
            out.append(private(key))
        if pref["chat_household"]:
            out.append(HOUSEHOLD)
        out += [project_source(p.id) for p in projects_for(key) if p.general_chat]
        from . import packs

        out += [Source("pack", n) for n in pref.get("packs", []) if packs.info(n)]
        return out
    p = get_project(key)
    if p is None:
        return []
    out = [project_source(p.id)]
    if p.grant_private:
        out.append(private(p.owner))
    if p.grant_household:
        out.append(HOUSEHOLD)
    return out


def indexes_reading(source: Source) -> list[str]:
    """Every index that currently subscribes to this source."""
    candidates = [chat_index(n) for n in users.names()] + [project_index(p.id) for p in all_projects()]
    return [i for i in candidates if source in sources_of(i)]


def desired_docs(index: str) -> dict[str, tuple[Source, Path]]:
    out = {}
    for src in sources_of(index):
        folder = src.folder
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            if path.is_file() and not path.name.startswith("."):
                out[src.doc_id(path.name)] = (src, path)
    return out
