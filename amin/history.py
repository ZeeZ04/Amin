"""Conversation history: one SQLite file per person, beside their documents.

    data/users/<name>/history.db

Nobody else's account can reach it: every query is scoped by the file it
opens, not by a WHERE clause a bug could drop. Deleting a conversation
deletes its rows; deleting a document does not rewrite old answers, so the
person can delete the conversation too.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from contextlib import closing

from . import users

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id      TEXT PRIMARY KEY,
    title   TEXT NOT NULL,
    project TEXT,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer   TEXT NOT NULL,   -- the /ask response, as JSON
    created  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conv_id);
"""


def _db(name: str) -> sqlite3.Connection:
    db = sqlite3.connect(users.user_dir(name) / "history.db")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)
    return db


def _title(question: str) -> str:
    q = " ".join(question.split())
    return q if len(q) <= 60 else q[:59].rstrip() + "…"


def record(name: str, conv_id: str | None, project: str | None, question: str, answer: dict) -> str:
    """Append one exchange; start a conversation when `conv_id` is None or not this person's."""
    now = time.time()
    with closing(_db(name)) as db, db:
        if not conv_id or not db.execute("SELECT 1 FROM conversations WHERE id=?", (conv_id,)).fetchone():
            conv_id = secrets.token_hex(6)
            db.execute(
                "INSERT INTO conversations(id,title,project,created,updated) VALUES (?,?,?,?,?)",
                (conv_id, _title(question), project, now, now),
            )
        else:
            db.execute("UPDATE conversations SET updated=? WHERE id=?", (now, conv_id))
        db.execute(
            "INSERT INTO messages(conv_id,question,answer,created) VALUES (?,?,?,?)",
            (conv_id, question, json.dumps(answer, ensure_ascii=False), now),
        )
    return conv_id


def conversations(name: str, limit: int = 200) -> list[dict]:
    with closing(_db(name)) as db:
        rows = db.execute(
            "SELECT id,title,project,updated FROM conversations ORDER BY updated DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in rows]


def messages(name: str, conv_id: str) -> dict | None:
    with closing(_db(name)) as db:
        conv = db.execute("SELECT id,title,project,updated FROM conversations WHERE id=?", (conv_id,)).fetchone()
        if conv is None:
            return None
        rows = db.execute("SELECT question,answer FROM messages WHERE conv_id=? ORDER BY id", (conv_id,))
        return {**dict(conv), "messages": [{"question": r["question"], "answer": json.loads(r["answer"])} for r in rows]}


def delete(name: str, conv_id: str) -> bool:
    with closing(_db(name)) as db, db:
        return db.execute("DELETE FROM conversations WHERE id=?", (conv_id,)).rowcount > 0


def forget_project(name: str, project: str) -> None:
    """A project this person can no longer open takes its conversations with it."""
    with closing(_db(name)) as db, db:
        db.execute("DELETE FROM conversations WHERE project=?", (project,))
