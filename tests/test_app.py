"""The household app: accounts, invites, private vs household libraries, delete, sessions."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from amin import api as api_mod
from amin.config import settings

LEASE = b"# Tenancy\nThe annual rent is AED 85,000, payable in four cheques.\n"
DIARY = b"# Diary\nMy locker combination is 4417.\n"
RENT_Q = {"question": "What is the annual rent?"}
LOCKER_Q = {"question": "What is my locker combination?"}


@pytest.fixture()
def users_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "users_path", tmp_path / "users")
    monkeypatch.setattr(settings, "provider", "echo")
    api_mod._engines.clear()
    return tmp_path / "users"


def client() -> TestClient:
    return TestClient(api_mod.api)


def signup(c, name, invite=None):
    r = c.post("/signup", json={"name": name, "password": "secret123", "invite": invite})
    assert r.status_code == 200, r.text
    return c


def invite_from(admin) -> str:
    return admin.post("/invites").json()["code"]


def answered(c, q) -> bool:
    return bool(c.post("/ask", json=q).json()["claims"])


def test_first_account_is_admin_and_others_need_an_invite(users_dir):
    admin = signup(client(), "abdul")
    assert admin.get("/me").json()["admin"] is True
    stranger = client()
    r = stranger.post("/signup", json={"name": "guest", "password": "secret123"})
    assert r.status_code == 400 and "invite" in r.json()["detail"]
    code = invite_from(admin)
    member = signup(client(), "sara", code)
    assert member.get("/me").json()["admin"] is False
    # one use only
    assert client().post("/signup", json={"name": "omar", "password": "secret123", "invite": code}).status_code == 400
    assert member.post("/invites").status_code == 403


def test_private_documents_stay_private_household_ones_are_shared(users_dir):
    abdul = signup(client(), "abdul")
    sara = signup(client(), "sara", invite_from(abdul))
    assert abdul.post("/upload?filename=diary.md&library=private", content=DIARY).status_code == 200
    assert abdul.post("/upload?filename=lease.md&library=household", content=LEASE).status_code == 200

    assert answered(abdul, LOCKER_Q) and answered(abdul, RENT_Q)
    assert answered(sara, RENT_Q), "household docs are for everyone"
    assert not answered(sara, LOCKER_Q), "sara must not see abdul's private diary"
    assert sara.get("/me").json()["private"] == []


def test_new_member_gets_existing_household_documents(users_dir):
    abdul = signup(client(), "abdul")
    abdul.post("/upload?filename=lease.md&library=household", content=LEASE)
    late = signup(client(), "late", invite_from(abdul))
    assert answered(late, RENT_Q)


def test_delete_removes_answers_everywhere(users_dir):
    abdul = signup(client(), "abdul")
    sara = signup(client(), "sara", invite_from(abdul))
    abdul.post("/upload?filename=lease.md&library=household", content=LEASE)
    assert sara.delete("/documents?filename=lease.md&library=household").status_code == 403
    assert abdul.delete("/documents?filename=lease.md&library=household").status_code == 200
    assert not answered(sara, RENT_Q) and not answered(abdul, RENT_Q)
    assert abdul.get("/me").json()["household"] == []


def test_sign_out_everywhere_kills_other_sessions(users_dir):
    phone = signup(client(), "abdul")
    laptop = client()
    assert laptop.post("/login", json={"name": "abdul", "password": "secret123"}).status_code == 200
    assert phone.post("/logout-all").status_code == 200
    assert laptop.get("/me").status_code == 401
    assert phone.get("/me").status_code == 401


@pytest.mark.parametrize("bad", ["../etc", "a", "Abdul Azeez!", "_household"])
def test_user_names_cannot_escape_their_folder(users_dir, bad):
    assert client().post("/signup", json={"name": bad, "password": "secret123"}).status_code in (400, 422)


def test_upload_strips_directories_and_rejects_unknown_types(users_dir):
    c = signup(client(), "abdul")
    assert c.post("/upload?filename=evil.exe", content=b"x").status_code == 400
    assert c.post("/upload?filename=x.md&library=everyone", content=LEASE).status_code == 400
    assert c.post("/upload?filename=../../escape.md", content=LEASE).json()["document"] == "escape.md"


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")
def test_photo_is_read_with_ocr(users_dir, tmp_path):
    from amin.ocr import ocr_image
    import subprocess
    img = tmp_path / "bill.png"
    subprocess.run(["convert", "-size", "900x120", "xc:white", "-pointsize", "48",
                    "-annotate", "+20+80", "Amount due AED 412", str(img)], check=True)
    assert "412" in ocr_image(img)
