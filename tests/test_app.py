"""The household app: accounts, invites, private vs household libraries, delete, sessions."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from amin import api as api_mod

LEASE = b"# Tenancy\nThe annual rent is AED 85,000, payable in four cheques.\n"
DIARY = b"# Diary\nMy locker combination is 4417.\n"
RENT_Q = {"question": "What is the annual rent?"}
LOCKER_Q = {"question": "What is my locker combination?"}


def client() -> TestClient:
    return TestClient(api_mod.api)


def signup(c, name, invite=None):
    r = c.post("/signup", json={"name": name, "password": "secret123", "invite": invite})
    assert r.status_code == 200, r.text
    return c


def invite_from(admin) -> str:
    return admin.post("/invites").json()["code"]


def answered(c, q) -> bool:
    """Answered *from documents*. A general-knowledge fallback is not access."""
    r = c.post("/ask", json=q).json()
    return bool(r["claims"]) and r["basis"] == "documents"


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
    import subprocess

    if not shutil.which("convert"):
        pytest.skip("ImageMagick's convert renders the test image: brew install imagemagick")

    from amin.ocr import ocr_image
    img = tmp_path / "bill.png"
    subprocess.run(["convert", "-size", "900x120", "xc:white", "-pointsize", "48",
                    "-annotate", "+20+80", "Amount due AED 412", str(img)], check=True)
    assert "412" in ocr_image(img)


def test_history_is_per_person_and_follows_project_access(users_dir):
    abdul = signup(client(), "abdul")
    sara = signup(client(), "sara", invite_from(abdul))
    first = abdul.post("/ask", json=RENT_Q).json()
    cid = first["conversation_id"]
    again = abdul.post("/ask", json={**LOCKER_Q, "conversation_id": cid}).json()
    assert again["conversation_id"] == cid
    conv = abdul.get(f"/conversations/{cid}").json()
    assert [m["question"] for m in conv["messages"]] == [RENT_Q["question"], LOCKER_Q["question"]]
    assert [c["id"] for c in abdul.get("/conversations").json()] == [cid]

    # another person can neither read nor continue it
    assert sara.get(f"/conversations/{cid}").status_code == 404
    assert sara.post("/ask", json={**RENT_Q, "conversation_id": cid}).json()["conversation_id"] != cid
    assert len(abdul.get(f"/conversations/{cid}").json()["messages"]) == 2

    # losing a project takes its conversations with it
    pid = abdul.post("/projects", json={"name": "Flat"}).json()["id"]
    abdul.patch(f"/projects/{pid}", json={"members": ["sara"]})
    sara.post("/ask", json={**RENT_Q, "project": pid})
    assert len(sara.get("/conversations").json()) == 2
    abdul.patch(f"/projects/{pid}", json={"members": []})
    assert len(sara.get("/conversations").json()) == 1

    assert abdul.delete(f"/conversations/{cid}").status_code == 200
    assert abdul.get(f"/conversations/{cid}").status_code == 404


def test_teach_amin_remembers_cites_and_forgets(users_dir):
    from amin import memory

    abdul = signup(client(), "abdul")
    sara = signup(client(), "sara", invite_from(abdul))
    r = abdul.post("/ask", json={"question": "Remember that my car's plate number is Dubai A 12345"}).json()
    assert r["outcome"] == "remembered" and "Dubai A 12345" in r["refusal_reason"]
    assert [f["text"] for f in abdul.get("/memory").json()] == ["my car's plate number is Dubai A 12345"]
    assert "memory.md" not in abdul.get("/me").json()["private"], "managed under Memory, not Documents"

    q = {"question": "What is my car's plate number?"}
    a = abdul.post("/ask", json=q).json()
    assert a["basis"] == "documents" and "12345" in " ".join(c["text"] for c in a["claims"])
    assert not answered(sara, q), "a taught fact is private to the person who taught it"

    fid = abdul.get("/memory").json()[0]["id"]
    assert abdul.delete(f"/memory/{fid}").status_code == 200
    assert not answered(abdul, q), "a deleted fact stops answering at once"
    assert memory.taught("تذكر أن موعد طبيب الأسنان يوم الخميس") == "موعد طبيب الأسنان يوم الخميس"
    assert memory.taught("ഓർക്കുക: എന്റെ രക്തഗ്രൂപ്പ് ഒ പോസിറ്റീവ് ആണ്") == "എന്റെ രക്തഗ്രൂപ്പ് ഒ പോസിറ്റീവ് ആണ്"
    assert memory.taught("Do you remember the Berlin Wall?") is None


def test_memory_edits_reach_the_index_not_just_the_file(users_dir):
    abdul = signup(client(), "abdul")
    abdul.post("/memory", json={"text": "The locker code at the gym is 4417."})
    abdul.post("/memory", json={"text": "The Wi-Fi password at home is falcon-river-22."})
    gym, wifi = {"question": "What is the locker code at the gym?"}, {"question": "What is the Wi-Fi password at home?"}
    assert answered(abdul, gym) and answered(abdul, wifi), "a second fact must be indexed too"
    first = abdul.get("/memory").json()[0]["id"]
    abdul.delete(f"/memory/{first}")
    assert not answered(abdul, gym), "a forgotten fact must stop answering while others remain"
    assert answered(abdul, wifi)


def test_re_uploading_a_document_replaces_the_old_version(users_dir):
    abdul = signup(client(), "abdul")
    abdul.post("/upload?filename=lease.md&library=private", content=LEASE)
    abdul.post("/upload?filename=lease.md&library=private",
               content=b"# Tenancy\nThe annual rent is AED 92,000, payable in two cheques.\n")
    r = abdul.post("/ask", json=RENT_Q).json()
    text = " ".join(c["text"] for c in r["claims"])
    assert "92,000" in text and "85,000" not in text


def test_model_files_are_served_only_to_members_and_only_listed_models(users_dir, tmp_path, monkeypatch):
    from amin.config import settings

    models = tmp_path / "models"
    (models / "edge-2-m46").mkdir(parents=True)
    (models / "edge-2-m46" / "config.json").write_text("{}")
    (models / "edge-2-m46" / "model.safetensors").write_bytes(b"\0" * 64)
    (models / "secret").mkdir()
    (models / "secret" / "config.json").write_text("{}")
    monkeypatch.setattr(settings, "models_path", models)

    assert client().get("/models").status_code == 401, "members only"
    c = signup(client(), "abdul")
    listed = c.get("/models").json()
    assert [m["name"] for m in listed] == ["edge-2-m46"] and listed[0]["bytes"] == 66
    assert c.get("/models/edge-2-m46/model.safetensors").content == b"\0" * 64
    assert c.get("/models/secret/config.json").status_code == 404, "only models Amin lists"
    assert c.get("/models/edge-2-m46/..%2Fsecret%2Fconfig.json").status_code == 404


def test_knowledge_packs_are_opt_in_cited_and_removable(users_dir, tmp_path, monkeypatch):
    import json as _json

    from amin.config import settings

    root = tmp_path / "packs"
    (root / "physics" / "docs").mkdir(parents=True)
    (root / "physics" / "pack.json").write_text(_json.dumps(
        {"title": "OpenStax Physics", "licence": "CC BY 4.0", "attribution": "OpenStax, Rice University"}))
    (root / "physics" / "docs" / "ch5.md").write_text(
        "# Newton's laws\n\n## Second law\nThe net force on a body equals its mass times its acceleration, F = ma.\n")
    monkeypatch.setattr(settings, "packs_path", root)

    abdul = signup(client(), "abdul")
    q = {"question": "What does Newton's second law say about the net force on a body?"}
    assert [p["enabled"] for p in abdul.get("/packs").json()] == [False], "off by default"
    assert not answered(abdul, q)
    assert abdul.patch("/me/prefs", json={"packs": ["physics"]}).status_code == 200
    r = abdul.post("/ask", json=q).json()
    assert r["basis"] == "documents" and any(c.startswith("k.physics.") for c in r["sources"])
    assert abdul.patch("/me/prefs", json={"packs": ["nonsense"]}).status_code == 400
    abdul.patch("/me/prefs", json={"packs": []})
    assert not answered(abdul, q), "switching a pack off removes it from the index"


def test_pack_front_matter_survives_attributions_with_colons(tmp_path):
    import json

    from amin.ingest import split_front_matter

    note = "Biology by OpenStax, CC BY 4.0. Source: https://openstax.org."
    raw = f"---\ntitle: {json.dumps('Biology · Cells')}\ntier: reference\nabout: openstax-biology\nnote: {json.dumps(note)}\n---\n\n# Cells\nText."
    parsed = split_front_matter(raw)
    assert parsed.meta["about"] == "openstax-biology" and parsed.meta["note"] == note


def test_reset_password_replaces_it_and_signs_out_everywhere(users_dir):
    from amin import users

    c = signup(client(), "owner")
    assert c.get("/me").status_code == 200
    before = users._load("users.json")["owner"]["session"]
    users.set_password("owner", "second-pass")
    assert not users.verify("owner", "secret123") and users.verify("owner", "second-pass")
    assert c.get("/me").status_code == 401  # the old sign-in no longer works
    assert users._load("users.json")["owner"]["session"] == before + 1
    with pytest.raises(ValueError):
        users.set_password("nobody", "whatever1")
