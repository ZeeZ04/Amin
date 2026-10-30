"""Knowledge packs (Task 3): read-only libraries of openly licensed knowledge.

    data/packs/<name>/pack.json   {"title", "description", "licence", "attribution", "source"}
    data/packs/<name>/docs/*.md   one file per chapter or page, headings as sections

A pack is retrieved from and cited exactly like a document ("OpenStax Biology
2e · 4.2 Cell structure"). It is not trained into the model (ADR-015). Each
person switches packs on for their own chat (prefs["packs"]); every pack is
off by default. Only material whose licence allows commercial use and
redistribution goes in a pack (docs/team/RESEARCH.md licence register): Python
docs (PSF-2.0) and OpenStax (CC BY 4.0) today. Exam boards' own specifications
and papers stay out unless the board grants a licence; owners can still add
copies they downloaded to their private library.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import settings

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def root() -> Path:
    return settings.packs_path


def folder(name: str) -> Path:
    if not _NAME.match(name):  # trust boundary: becomes a path
        raise ValueError("bad pack name")
    return root() / name / "docs"


def info(name: str) -> dict | None:
    f = root() / name / "pack.json"
    if not _NAME.match(name) or not f.exists():
        return None
    meta = json.loads(f.read_text(encoding="utf-8"))
    docs = folder(name)
    meta["name"] = name
    meta["documents"] = sum(1 for p in docs.iterdir() if p.suffix == ".md") if docs.exists() else 0
    return meta


def available() -> list[dict]:
    if not root().exists():
        return []
    return [m for d in sorted(root().iterdir()) if d.is_dir() and (m := info(d.name))]
