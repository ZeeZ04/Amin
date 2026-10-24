"""Teach Amin: facts a person tells Amin, kept in their own private library.

    "Remember that my car's plate is Dubai A 12345"
        → data/users/<name>/memory.json      (the facts, source of truth)
        → data/users/<name>/docs/memory.md   (one section per fact, indexed)

Taught facts go into the index, never into model weights (ADR-012, ADR-015).
In the index each one is citable like a document, editable and deletable. A
deleted fact is gone from every answer at the next sync, which no amount of
fine-tuning can promise. Because memory.md lives in the private library, the
existing permissions decide where it is used: the person's own chat, and a
project only if they granted it their library (ADR-013).
"""

from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

from . import users

FILE = "memory.md"
MAX_FACT = 500

# An explicit request to remember, in each language Amin reads. Only an
# explicit request saves anything: Amin never decides on its own to keep what
# someone said.
TEACH = re.compile(
    r"^\s*(?:please\s+)?(?:remember|note|save|keep in mind)(?:\s+that)?[\s,:]+"
    r"|^\s*(?:تذكر|تذكّر|احفظ|سجل)(?:\s+أن)?[\s،:]+"
    r"|^\s*(?:ഓർക്കുക|ഓർത്തുവെക്കുക|ഓർത്തു\s*വയ്ക്കുക|ഓർമ്മിക്കുക)[\s,:]+",
    re.IGNORECASE,
)


def taught(message: str) -> str | None:
    """The fact in "remember that …", or None if the message isn't a request to remember."""
    m = TEACH.match(message)
    if not m:
        return None
    fact = message[m.end():].strip()
    return fact or None


def _json(name: str) -> Path:
    return users.user_dir(name) / "memory.json"


def facts(name: str) -> list[dict]:
    f = _json(name)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def _save(name: str, items: list[dict]) -> None:
    f = _json(name)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(f)
    _render(name, items)


def _render(name: str, items: list[dict]) -> None:
    """memory.md: one heading per fact, so each fact is its own chunk and its own citation."""
    doc = users.docs_dir(name) / FILE
    if not items:
        doc.unlink(missing_ok=True)
        return
    parts = ["# What you told Amin\n"]
    for it in items:
        day = time.strftime("%-d %B %Y", time.localtime(it["created"]))
        parts.append(f"## Told on {day}\n\n{it['text']}\n")
    doc.write_text("\n".join(parts), encoding="utf-8")


def add(name: str, text: str) -> dict:
    text = " ".join(text.split())
    if not text:
        raise ValueError("nothing to remember")
    if len(text) > MAX_FACT:
        raise ValueError(f"keep a fact under {MAX_FACT} characters; add a document for anything longer")
    items = facts(name)
    item = {"id": "m" + secrets.token_hex(3), "text": text, "created": time.time()}
    items.append(item)
    _save(name, items)
    return item


def remove(name: str, fact_id: str) -> bool:
    items = facts(name)
    kept = [it for it in items if it["id"] != fact_id]
    if len(kept) == len(items):
        return False
    _save(name, kept)
    return True
