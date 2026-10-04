"""Hybrid retrieval over SQLite.

Two reasons this is SQLite and not a vector database:

1. The whole point of Amin is that it runs on one laptop with no services to
   babysit. SQLite with FTS5 ships inside Python.
2. At household corpus scale (10^3-10^5 chunks) a brute-force numpy dot
   product is faster than an ANN index and has no recall loss. Swap in FAISS
   or sqlite-vec when the corpus outgrows memory, not before.

Fusion is Reciprocal Rank Fusion: it needs no score normalisation between the
dense and lexical arms, which is where naive weighted-sum hybrids usually go
wrong.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import numpy as np

from .config import settings
from .providers import content_tokens
from .schema import Chunk, Document, Retrieved, Tier

# Bump when the table definitions below change. `CREATE TABLE IF NOT EXISTS`
# cannot add a column to an existing database, so without a version check an
# upgraded Amin meets an old index and fails with "table has no column named
# ...", which looks like a bug in the query rather than a stale file. The index
# is a derived artefact - it can always be rebuilt from the corpus - so the
# correct response to a version mismatch is to drop it and say so.
SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    title  TEXT NOT NULL,
    path   TEXT NOT NULL,
    tier   INTEGER NOT NULL,
    lang   TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    superseded INTEGER NOT NULL DEFAULT 0,
    meta   TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id   TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    ordinal  INTEGER NOT NULL,
    heading  TEXT NOT NULL DEFAULT '',
    text     TEXT NOT NULL,
    tier     INTEGER NOT NULL,
    subject  TEXT NOT NULL DEFAULT '',
    superseded INTEGER NOT NULL DEFAULT 0,
    vector   BLOB
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, heading, chunk_id UNINDEXED, tokenize='unicode61 remove_diacritics 2'
);
"""

_ARABIC = r"؀-ۿ"
_WORD_RE = re.compile(rf"[A-Za-z0-9{_ARABIC}]+")


def _fts_query(question: str) -> str:
    """Turn free text into a safe FTS5 OR-query. User text never reaches FTS raw."""
    terms = [t for t in _WORD_RE.findall(question) if len(t) > 1]
    return " OR ".join(f'"{t}"' for t in terms[:32])


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or settings.index_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self._idf_cache: dict[str, float] | None = None
        self._subject_cache: dict[str, str] | None = None
        self._doc_token_cache: dict[str, set[str]] | None = None
        self._n_chunks: int = 0
        # Set by _migrate when an older index was discarded, so the CLI can tell
        # the user to re-ingest instead of silently reporting an empty index.
        self.stale_rebuild: bool = False
        self._migrate()
        self.db.executescript(SCHEMA)

    def _migrate(self) -> None:
        """Drop a stale index rather than half-upgrading it."""
        current = self.db.execute("PRAGMA user_version").fetchone()[0]
        if current == SCHEMA_VERSION:
            return
        existing = {
            r[0]
            for r in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            )
        }
        if existing & {"documents", "chunks", "chunks_fts"}:
            self.stale_rebuild = True
            self.db.executescript(
                "DROP TABLE IF EXISTS chunks_fts;"
                "DROP TABLE IF EXISTS chunks;"
                "DROP TABLE IF EXISTS documents;"
            )
        self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.db.commit()

    def _invalidate(self) -> None:
        self._idf_cache = None
        self._subject_cache = None
        self._doc_token_cache = None

    # -- writing -------------------------------------------------------------

    def reset(self) -> None:
        self.db.executescript(
            "DELETE FROM chunks_fts; DELETE FROM chunks; DELETE FROM documents;"
        )
        self.db.commit()
        self._invalidate()

    def upsert(self, docs: list[Document], chunks: list[Chunk], vectors: np.ndarray) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        with self.db:
            self.db.executemany(
                "INSERT OR REPLACE INTO documents(doc_id,title,path,tier,lang,subject,superseded,meta)"
                " VALUES(?,?,?,?,?,?,?,?)",
                [
                    (
                        d.doc_id,
                        d.title,
                        d.path,
                        int(d.tier),
                        d.lang,
                        d.subject,
                        int(d.superseded),
                        json.dumps(d.meta),
                    )
                    for d in docs
                ],
            )
            doc_ids = [d.doc_id for d in docs]
            self.db.executemany("DELETE FROM chunks WHERE doc_id = ?", [(i,) for i in doc_ids])
            self.db.executemany(
                "DELETE FROM chunks_fts WHERE chunk_id LIKE ? || '#%'", [(i,) for i in doc_ids]
            )
            self.db.executemany(
                "INSERT INTO chunks(chunk_id,doc_id,ordinal,heading,text,tier,subject,superseded,vector)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                [
                    (
                        c.chunk_id,
                        c.doc_id,
                        c.ordinal,
                        c.heading,
                        c.text,
                        int(c.tier),
                        c.subject,
                        int(c.superseded),
                        np.asarray(v, dtype=np.float32).tobytes(),
                    )
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )
            self.db.executemany(
                "INSERT INTO chunks_fts(text,heading,chunk_id) VALUES(?,?,?)",
                [(c.text, c.heading, c.chunk_id) for c in chunks],
            )
        self._invalidate()

    # -- reading -------------------------------------------------------------

    def stats(self) -> dict:
        row = self.db.execute(
            "SELECT (SELECT COUNT(*) FROM documents) d, (SELECT COUNT(*) FROM chunks) c"
        ).fetchone()
        tiers = {
            Tier(r["tier"]).label: r["n"]
            for r in self.db.execute("SELECT tier, COUNT(*) n FROM chunks GROUP BY tier")
        }
        return {"documents": row["d"], "chunks": row["c"], "by_tier": tiers}

    def _row_to_chunk(self, row: sqlite3.Row) -> Chunk:
        return Chunk(
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            ordinal=row["ordinal"],
            heading=row["heading"],
            text=row["text"],
            tier=Tier(row["tier"]),
            subject=row["subject"],
            superseded=bool(row["superseded"]),
        )

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        row = self.db.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
        return self._row_to_chunk(row) if row else None

    def all_chunks(self) -> list[Chunk]:
        return [self._row_to_chunk(r) for r in self.db.execute("SELECT * FROM chunks")]

    def _matrix(self) -> tuple[list[str], np.ndarray]:
        ids, vecs = [], []
        for row in self.db.execute("SELECT chunk_id, vector FROM chunks WHERE vector IS NOT NULL"):
            ids.append(row["chunk_id"])
            vecs.append(np.frombuffer(row["vector"], dtype=np.float32))
        if not ids:
            return [], np.zeros((0, 1), dtype=np.float32)
        return ids, np.vstack(vecs)

    def dense(self, query_vec: np.ndarray, k: int) -> list[str]:
        ids, mat = self._matrix()
        if not ids:
            return []
        q = np.asarray(query_vec, dtype=np.float32).ravel()
        if q.shape[0] != mat.shape[1]:
            raise ValueError(
                f"query dim {q.shape[0]} != index dim {mat.shape[1]} "
                "- the index was built with a different embedding model; run `amin ingest --reset`"
            )
        scores = mat @ q
        order = np.argsort(-scores)[:k]
        return [ids[i] for i in order]

    def lexical(self, question: str, k: int) -> list[str]:
        query = _fts_query(question)
        if not query:
            return []
        try:
            rows = self.db.execute(
                "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ?"
                " ORDER BY bm25(chunks_fts, 1.0, 0.4) LIMIT ?",
                (query, k),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [r["chunk_id"] for r in rows]

    # -- evidence coverage ---------------------------------------------------
    #
    # RRF scores are rank-derived: the top hit scores ~1/(k+1) whether it is a
    # perfect match or pure noise. They are therefore useless as an absolute
    # "is there evidence here" signal, which is exactly what the refusal gate
    # needs. Coverage answers a different and answerable question: how much of
    # the question's distinctive vocabulary does this chunk actually contain,
    # weighted so that rare terms count and common ones barely do.

    def _idf(self) -> dict[str, float]:
        if self._idf_cache is None:
            df: dict[str, int] = {}
            n = 0
            for row in self.db.execute("SELECT text, heading FROM chunks"):
                n += 1
                for tok in content_tokens(f"{row['heading']} {row['text']}"):
                    df[tok] = df.get(tok, 0) + 1
            import math

            self._n_chunks = n
            self._idf_cache = {
                tok: math.log(1.0 + n / (1.0 + count)) for tok, count in df.items()
            }
        return self._idf_cache

    def _unseen_idf(self) -> float:
        """Weight for a query term that appears nowhere in the corpus.

        A term the corpus has never seen is maximally distinctive, so it must
        carry the largest weight - otherwise a question about something absent
        would score as well covered by the terms that happen to overlap.
        """
        import math

        self._idf()
        return math.log(1.0 + max(self._n_chunks, 1))

    def coverage(self, question: str, chunk: Chunk) -> float:
        idf = self._idf()
        terms = content_tokens(question)
        if not terms:
            return 1.0  # nothing distinctive to ask about; do not gate on it
        present = content_tokens(f"{chunk.heading} {chunk.text}")
        unseen = self._unseen_idf()
        total = sum(idf.get(t, unseen) for t in terms)
        hit = sum(idf.get(t, unseen) for t in terms if t in present)
        return hit / total if total else 0.0

    # -- fusion --------------------------------------------------------------

    def search(
        self, question: str, query_vec: np.ndarray | None = None, limit: int | None = None
    ) -> list[Retrieved]:
        dense_ids = self.dense(query_vec, settings.top_k_dense) if query_vec is not None else []
        lex_ids = self.lexical(question, settings.top_k_lexical)

        k = settings.rrf_k
        fused: dict[str, float] = {}
        d_rank: dict[str, int] = {}
        l_rank: dict[str, int] = {}
        for rank, cid in enumerate(dense_ids, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank)
            d_rank[cid] = rank
        for rank, cid in enumerate(lex_ids, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank)
            l_rank[cid] = rank

        results: list[Retrieved] = []
        for cid, score in fused.items():
            chunk = self.get_chunk(cid)
            if chunk is None:
                continue
            cov = self.coverage(question, chunk)
            # Coverage reorders within the fused candidate set, where RRF alone
            # is nearly flat. Tier is a small, deliberately weak nudge: a
            # primary source wins ties, never relevance outright.
            adjusted = score * (1.0 + 1.5 * cov) * (1.0 + (4 - int(chunk.tier)) * 0.04)
            # A superseded document stays searchable - "what did last year's
            # handbook say" is a real question - but must never outrank the
            # current version at comparable relevance. Without this, a question
            # explicitly about the 2026/27 handbook was answered from the 2025
            # one, which is a wrong answer with a correct-looking citation.
            if chunk.superseded:
                adjusted *= settings.superseded_penalty
            results.append(
                Retrieved(
                    chunk=chunk,
                    score=adjusted,
                    coverage=cov,
                    dense_rank=d_rank.get(cid),
                    lexical_rank=l_rank.get(cid),
                )
            )
        results.sort(key=lambda r: (-r.score, -r.coverage))
        return results[: limit or settings.top_k_final]

    # -- document relatedness ------------------------------------------------

    def are_related(self, doc_a: str, doc_b: str, overlap_floor: float = 0.15) -> bool:
        """Are two documents about the same thing?

        Only comparable documents can contradict each other. A tenancy contract
        and an electricity tariff both have a section headed "Security deposit"
        with different figures, and that is not a disagreement - they are about
        different deposits.

        Declared `about:` subjects are authoritative. The vocabulary-overlap
        fallback is a heuristic with a known failure mode: it was measured at
        0.19 and 0.24 for the two genuinely related pairs in this corpus and at
        most 0.12 for every unrelated pair, so 0.15 separates them here. That
        margin is a property of this corpus, not a law. Declare `about:` on
        documents that matter rather than relying on it.
        """
        if doc_a == doc_b:
            return True
        subjects = self._subjects()
        sa, sb = subjects.get(doc_a, ""), subjects.get(doc_b, "")
        if sa and sb:
            return sa == sb
        return self._doc_overlap(doc_a, doc_b) >= overlap_floor

    def _subjects(self) -> dict[str, str]:
        if self._subject_cache is None:
            self._subject_cache = {
                r["doc_id"]: r["subject"]
                for r in self.db.execute("SELECT doc_id, subject FROM documents")
            }
        return self._subject_cache

    def _doc_tokens(self) -> dict[str, set[str]]:
        if self._doc_token_cache is None:
            acc: dict[str, set[str]] = {}
            for row in self.db.execute("SELECT doc_id, text FROM chunks"):
                acc.setdefault(row["doc_id"], set()).update(content_tokens(row["text"]))
            self._doc_token_cache = acc
        return self._doc_token_cache

    def _doc_overlap(self, doc_a: str, doc_b: str) -> float:
        tokens = self._doc_tokens()
        ta, tb = tokens.get(doc_a, set()), tokens.get(doc_b, set())
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    def close(self) -> None:
        self.db.close()
