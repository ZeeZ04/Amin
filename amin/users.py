"""Household accounts.

Each person has a private folder (documents + index) under data/users/<name>/.
Shared household documents live once in data/users/_household/docs and are
indexed into every member's index, so one search covers both libraries while
nobody's index ever contains another person's private files. "_household"
cannot collide with a user name: names may not start with an underscore.

Signup is invite-only: the first account becomes the admin; everyone after
needs a one-time invite code from the admin.

Passwords: PBKDF2 (stdlib). Sessions: HMAC-signed cookie carrying a per-user
session version; "sign out everywhere" bumps the version, which invalidates
every cookie issued before it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from pathlib import Path

from .config import settings

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
HOUSEHOLD = "_household"
INVITE_TTL = 7 * 24 * 3600


def root() -> Path:
    path = settings.users_path
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_dir(name: str) -> Path:
    if name != HOUSEHOLD and not NAME_RE.match(name):  # trust boundary: becomes a path
        raise ValueError("names: 2-32 characters, lowercase letters, digits, - or _")
    return root() / name


def docs_dir(name: str) -> Path:
    path = user_dir(name) / "docs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path(name: str) -> Path:
    return user_dir(name) / "amin.db"


def _load(file: str) -> dict:
    f = root() / file
    return json.loads(f.read_text()) if f.exists() else {}


def _save(file: str, data: dict) -> None:
    f = root() / file
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.chmod(0o600)
    tmp.replace(f)  # atomic: a crash mid-write cannot corrupt the account list


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def names() -> list[str]:
    return sorted(_load("users.json"))


def is_admin(name: str) -> bool:
    return bool(_load("users.json").get(name, {}).get("admin"))


def create(name: str, password: str, invite: str | None = None) -> None:
    name = name.strip().lower()
    if not NAME_RE.match(name):  # user_dir() allows HOUSEHOLD; an account must not
        raise ValueError("names: 2-32 characters, lowercase letters, digits, - or _")
    if len(password) < 6:
        raise ValueError("password must be at least 6 characters")
    reg = _load("users.json")
    if name in reg:
        raise ValueError("that name is taken")
    first = not reg
    if not first:
        _use_invite(invite)
    salt = secrets.token_hex(16)
    reg[name] = {"salt": salt, "hash": _hash(password, salt), "admin": first, "session": 0}
    _save("users.json", reg)
    docs_dir(name)


def set_password(name: str, password: str) -> None:
    """Replace a password and sign the account out everywhere. Only reachable
    from this computer's command line (`amin reset-password`), which is the
    recovery path: whoever holds the computer already holds the data."""
    name = name.strip().lower()
    if len(password) < 6:
        raise ValueError("password must be at least 6 characters")
    reg = _load("users.json")
    if name not in reg:
        raise ValueError(f"no account called {name!r}; accounts: {', '.join(sorted(reg)) or 'none'}")
    salt = secrets.token_hex(16)
    reg[name].update(salt=salt, hash=_hash(password, salt), session=reg[name].get("session", 0) + 1)
    _save("users.json", reg)


def verify(name: str, password: str) -> bool:
    entry = _load("users.json").get(name.strip().lower())
    if not entry:
        _hash(password, "00" * 16)  # same cost either way: timing does not reveal names
        return False
    return hmac.compare_digest(entry["hash"], _hash(password, entry["salt"]))


# -- invites -----------------------------------------------------------------


def new_invite() -> str:
    code = secrets.token_urlsafe(6)
    inv = _load("invites.json")
    now = time.time()
    inv = {c: t for c, t in inv.items() if t > now}  # drop expired
    inv[code] = now + INVITE_TTL
    _save("invites.json", inv)
    return code


def _use_invite(code: str | None) -> None:
    inv = _load("invites.json")
    if not code or inv.get(code.strip(), 0) < time.time():
        raise ValueError("a valid invite code is required — ask the admin for one")
    del inv[code.strip()]
    _save("invites.json", inv)


# -- sessions ----------------------------------------------------------------


def _secret() -> bytes:
    f = root() / ".secret"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
        f.chmod(0o600)
    return f.read_text().encode()


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(name: str) -> str:
    payload = f"{name}.{_load('users.json')[name]['session']}"
    return f"{payload}.{_sign(payload)}"


def read_token(token: str | None) -> str | None:
    if not token or token.count(".") != 2:
        return None
    name, version, sig = token.split(".")
    if not hmac.compare_digest(sig, _sign(f"{name}.{version}")):
        return None
    entry = _load("users.json").get(name)
    if not entry or str(entry["session"]) != version:
        return None
    return name


def sign_out_everywhere(name: str) -> None:
    reg = _load("users.json")
    reg[name]["session"] += 1
    _save("users.json", reg)


# -- preferences ---------------------------------------------------------------


def get_prefs(name: str) -> dict:
    return dict(_load("users.json").get(name, {}).get("prefs", {}))


def set_prefs(name: str, **values) -> dict:
    reg = _load("users.json")
    reg[name].setdefault("prefs", {}).update(values)
    _save("users.json", reg)
    return dict(reg[name]["prefs"])
