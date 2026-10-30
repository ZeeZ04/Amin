"""A disk cache for embeddings, keyed by embedding model and text.

Every index embeds its own documents (api.sync), so a knowledge pack that
five people turn on would be embedded five times, and a re-index after a
restart would embed everything again. The vector for a passage depends only
on the model and the text, so it is stored once here and reused by every
index. The cache holds vectors, never text: only a hash of each passage.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np

_lock = threading.Lock()


class VectorCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS vec (key TEXT PRIMARY KEY, v BLOB NOT NULL)")

    @staticmethod
    def key(model: str, text: str) -> str:
        return hashlib.sha256(f"{model}\0{text}".encode()).hexdigest()

    def embed(self, model: str, texts: list[str], compute: Callable[[list[str]], np.ndarray]) -> np.ndarray:
        """Vectors for `texts`, computing only the ones not seen before."""
        keys = [self.key(model, t) for t in texts]
        with _lock:
            found = {}
            for i in range(0, len(keys), 500):
                part = keys[i:i + 500]
                q = f"SELECT key, v FROM vec WHERE key IN ({','.join('?' * len(part))})"
                found.update((k, np.frombuffer(v, dtype=np.float32)) for k, v in self.db.execute(q, part))
        missing = [i for i, k in enumerate(keys) if k not in found]
        if missing:
            new = compute([texts[i] for i in missing])
            with _lock:
                self.db.executemany("INSERT OR REPLACE INTO vec VALUES (?, ?)",
                                    [(keys[i], new[j].astype(np.float32).tobytes()) for j, i in enumerate(missing)])
                self.db.commit()
            for j, i in enumerate(missing):
                found[keys[i]] = new[j].astype(np.float32)
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        return np.vstack([found[k] for k in keys])
