"""The household app: accounts, isolation between people, upload, ask."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from amin import api as api_mod
from amin.config import settings

LEASE = b"# Tenancy\nThe annual rent is AED 85,000, payable in four cheques.\n"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "users_path", tmp_path / "users")
    monkeypatch.setattr(settings, "provider", "echo")
    api_mod._engines.clear()
    return TestClient(api_mod.api)


def _signup(c, name):
    r = c.post("/signup", json={"name": name, "password": "secret123"})
    assert r.status_code == 200, r.text


def test_new_user_starts_empty_and_must_sign_in(client):
    assert client.get("/me").status_code == 401
    _signup(client, "abdul")
    assert client.get("/me").json() == {"name": "abdul", "documents": []}


def test_documents_are_private_to_their_owner(client):
    _signup(client, "abdul")
    r = client.post("/upload?filename=lease.md", content=LEASE)
    assert r.status_code == 200 and r.json()["chunks"] >= 1
    assert client.post("/ask", json={"question": "What is the annual rent?"}).json()["claims"]

    client.post("/logout")
    _signup(client, "sara")
    assert client.get("/me").json()["documents"] == []
    answer = client.post("/ask", json={"question": "What is the annual rent?"}).json()
    assert not answer["claims"], "sara must not see abdul's lease"


def test_wrong_password_and_duplicate_name_are_rejected(client):
    _signup(client, "abdul")
    assert client.post("/login", json={"name": "abdul", "password": "wrong-one"}).status_code == 401
    assert client.post("/signup", json={"name": "abdul", "password": "secret123"}).status_code == 400


@pytest.mark.parametrize("bad", ["../etc", "a", "Abdul Azeez!"])
def test_user_names_cannot_escape_their_folder(client, bad):
    assert client.post("/signup", json={"name": bad, "password": "secret123"}).status_code in (400, 422)


def test_upload_strips_directories_and_rejects_unknown_types(client):
    _signup(client, "abdul")
    assert client.post("/upload?filename=evil.exe", content=b"x").status_code == 400
    r = client.post("/upload?filename=../../escape.md", content=LEASE)
    assert r.json()["document"] == "escape.md"
