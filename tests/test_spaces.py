"""Projects, permissions and the general-knowledge fallback (ADR-013).

Every permission here is a privacy boundary, so each test checks both
directions: off means the documents are not reachable, on means they are, and
switching it back off removes them again.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from amin.answer import Amin
from amin.schema import Outcome
from amin.store import Store
from tests.test_app import client, invite_from, signup

LEASE = b"# Tenancy\nThe annual rent is AED 85,000, payable in four cheques.\n"
DIARY = b"# Diary\nMy locker combination is 4417.\n"
RENT = "What is the annual rent?"
LOCKER = "What is my locker combination?"


def ask(c: TestClient, q: str, project: str | None = None) -> dict:
    r = c.post("/ask", json={"question": q, "project": project})
    assert r.status_code == 200, r.text
    return r.json()


def from_docs(c, q, project=None) -> bool:
    r = ask(c, q, project)
    return bool(r["claims"]) and r["basis"] == "documents"


def upload(c, name, body, **params):
    r = c.post("/upload", params={"filename": name, **params}, content=body)
    assert r.status_code == 200, r.text


def new_project(c, name="Flat") -> str:
    r = c.post("/projects", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def patch(c, pid, **body):
    return c.patch(f"/projects/{pid}", json=body)


def test_project_documents_stay_in_the_project_until_general_chat_is_allowed(users_dir):
    abdul = signup(client(), "abdul")
    pid = new_project(abdul)
    upload(abdul, "lease.md", LEASE, library="project", project=pid)

    assert from_docs(abdul, RENT, pid)
    assert not from_docs(abdul, RENT), "general chat must not see a project by default"

    assert patch(abdul, pid, general_chat=True).status_code == 200
    assert from_docs(abdul, RENT)

    assert patch(abdul, pid, general_chat=False).status_code == 200
    assert not from_docs(abdul, RENT), "revoking must remove the documents again"


def test_project_reads_the_private_library_only_when_granted(users_dir):
    abdul = signup(client(), "abdul")
    upload(abdul, "diary.md", DIARY)  # private library
    pid = new_project(abdul)

    assert from_docs(abdul, LOCKER), "own chat sees own library by default"
    assert not from_docs(abdul, LOCKER, pid), "a project is sealed by default"

    patch(abdul, pid, grant_private=True)
    assert from_docs(abdul, LOCKER, pid)
    patch(abdul, pid, grant_private=False)
    assert not from_docs(abdul, LOCKER, pid)


def test_sharing_a_project_with_family(users_dir):
    abdul = signup(client(), "abdul")
    sara = signup(client(), "sara", invite_from(abdul))
    pid = new_project(abdul)
    upload(abdul, "lease.md", LEASE, library="project", project=pid)

    assert sara.post("/ask", json={"question": RENT, "project": pid}).status_code == 404
    assert pid not in [p["id"] for p in sara.get("/me").json()["projects"]]

    assert patch(abdul, pid, members=["sara"]).status_code == 200
    assert from_docs(sara, RENT, pid)
    assert not from_docs(sara, RENT), "sharing a project does not share it into her chat"

    # members may ask and upload, not change permissions or delete documents
    assert patch(sara, pid, general_chat=True).status_code == 403
    assert sara.delete("/documents", params={"filename": "lease.md", "library": "project", "project": pid}).status_code == 403

    patch(abdul, pid, general_chat=True)
    assert from_docs(sara, RENT), "general_chat applies to everyone who can open it"

    patch(abdul, pid, members=[])
    assert sara.post("/ask", json={"question": RENT, "project": pid}).status_code == 404
    assert not from_docs(sara, RENT), "unsharing removes it from her chat too"


def test_a_granted_private_library_is_visible_to_project_members(users_dir):
    """Granting is the owner's explicit choice; the app warns before it."""
    abdul = signup(client(), "abdul")
    sara = signup(client(), "sara", invite_from(abdul))
    upload(abdul, "diary.md", DIARY)
    pid = new_project(abdul)
    patch(abdul, pid, members=["sara"])
    assert not from_docs(sara, LOCKER, pid)
    patch(abdul, pid, grant_private=True)
    assert from_docs(sara, LOCKER, pid)
    patch(abdul, pid, grant_private=False)
    assert not from_docs(sara, LOCKER, pid)


def test_deleting_a_project_removes_it_everywhere(users_dir):
    abdul = signup(client(), "abdul")
    pid = new_project(abdul)
    upload(abdul, "lease.md", LEASE, library="project", project=pid)
    patch(abdul, pid, general_chat=True)
    assert from_docs(abdul, RENT)
    assert abdul.delete(f"/projects/{pid}").status_code == 200
    assert not from_docs(abdul, RENT)
    assert abdul.post("/ask", json={"question": RENT, "project": pid}).status_code == 404


def test_chat_preferences_switch_the_libraries_off(users_dir):
    abdul = signup(client(), "abdul")
    upload(abdul, "diary.md", DIARY)
    assert from_docs(abdul, LOCKER)
    assert abdul.patch("/me/prefs", json={"chat_private": False}).json()["chat_private"] is False
    assert not from_docs(abdul, LOCKER)


def test_bad_project_ids_are_not_paths(users_dir):
    abdul = signup(client(), "abdul")
    assert abdul.post("/ask", json={"question": RENT, "project": "../abdul"}).status_code == 404
    assert abdul.patch("/projects/..%2Fx", json={"general_chat": True}).status_code == 404


# -- the fallback itself -------------------------------------------------------


class _Stub:
    name = "stub"

    def __init__(self, reply: str):
        self.reply = reply
        self.systems: list[str] = []

    def complete(self, prompt, *, model=None, system=""):
        self.systems.append(system)
        return self.reply

    def stream(self, prompt, *, model=None, system=""):
        yield self.complete(prompt, model=model, system=system)

    def embed(self, texts):
        import numpy as np

        return np.zeros((len(texts), 8), dtype=np.float32)


def test_empty_space_answers_generally_labelled_and_uncited(tmp_path):
    stub = _Stub("Ottawa is the capital of Canada [S1].")
    ans = Amin(store=Store(tmp_path / "x.db"), provider=stub, fallback=True).ask("What is the capital of Canada?")
    assert ans.outcome is Outcome.GENERAL
    assert ans.text == "Ottawa is the capital of Canada."  # a tag here would fake a citation
    assert not ans.sources() and not ans.refused


def test_strict_mode_still_refuses(tmp_path):
    stub = _Stub("Ottawa.")
    ans = Amin(store=Store(tmp_path / "x.db"), provider=stub, fallback=False).ask("What is the capital of Canada?")
    assert ans.refused and not stub.systems, "strict mode must not call the model with no evidence"


def test_general_no_evidence_reply_is_an_abstention(tmp_path):
    ans = Amin(store=Store(tmp_path / "x.db"), provider=_Stub("NO_EVIDENCE"), fallback=True).ask("Who is my landlord?")
    assert ans.refused


# -- grading the fallback --------------------------------------------------------


def _general(text: str):
    from amin.schema import Answer, Claim, Verdict

    return Answer(question="q", outcome=Outcome.GENERAL,
                  claims=[Claim(text=text, verdict=Verdict.UNCITED, verifier_note="general knowledge")])


def test_general_answer_to_a_general_fact_passes_only_if_right():
    from amin.evaluate import Item, grade

    item = Item(id="u", question="Capital of Burkina Faso?", kind="unanswerable", expect_general=["Ouagadougou"])
    assert grade(item, _general("It is Ouagadougou.")).passed
    assert not grade(item, _general("It is Bamako.")).passed


def test_general_answer_to_a_personal_question_must_decline():
    from amin.evaluate import Item, grade

    item = Item(id="u", question="What is my landlord's name?", kind="unanswerable")
    assert grade(item, _general("I don't have access to your documents, so I don't know.")).passed
    assert not grade(item, _general("Your landlord is Ahmed Saeed.")).passed
