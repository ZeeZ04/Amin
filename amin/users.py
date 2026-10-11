"""Household accounts: each person gets their own documents and their own index.

Isolation is by directory, not by row filter: a user's documents and index live
under data/users/<name>/, and the engine for one user is built on that user's
index alone. A query cannot reach another person's files because no code path
opens them.

Passwords are PBKDF2-hashed (stdlib). Sessions are HMAC-signed cookies with a
per-install secret. shortcut: plain HTTP on the home network, so a password
crosses the Wi-Fi in clear text; put it behind HTTPS before it leaves the house.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path

from .config import settings

NAME_RE = re.compile(r"^[a-z0-9_-]{2,32}$")


def root() -> Path:
    path = settings.users_path
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_dir(name: str) -> Path:
    if not NAME_RE.match(name):  # trust boundary: the name becomes a path
        raise ValueError("invalid user name")
    return root() / name


def docs_dir(name: str) -> Path:
    path = user_dir(name) / "docs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path(name: str) -> Path:
    return user_dir(name) / "amin.db"


def _registry() -> dict:
    f = root() / "users.json"
    return json.loads(f.read_text()) if f.exists() else {}


def _save(reg: dict) -> None:
    f = root() / "users.json"
    f.write_text(json.dumps(reg, indent=2))
    f.chmod(0o600)


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def create(name: str, password: str) -> None:
    name = name.strip().lower()
    user_dir(name)  # validates
    if len(password) < 6:
        raise ValueError("password must be at least 6 characters")
    reg = _registry()
    if name in reg:
        raise ValueError("that name is taken")
    salt = secrets.token_hex(16)
    reg[name] = {"salt": salt, "hash": _hash(password, salt)}
    _save(reg)
    docs_dir(name)


def verify(name: str, password: str) -> bool:
    entry = _registry().get(name.strip().lower())
    if not entry:
        _hash(password, "00" * 16)  # same cost either way, so timing does not reveal names
        return False
    return hmac.compare_digest(entry["hash"], _hash(password, entry["salt"]))


def _secret() -> bytes:
    f = root() / ".secret"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
        f.chmod(0o600)
    return f.read_text().encode()


def make_token(name: str) -> str:
    sig = hmac.new(_secret(), name.encode(), hashlib.sha256).hexdigest()
    return f"{name}.{sig}"


def read_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    name, sig = token.rsplit(".", 1)
    good = hmac.new(_secret(), name.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, good) and name in _registry():
        return name
    return None
