"""Behaviour tests. No model, no network: the echo provider plus the hash embedder.

These pin the properties the project claims, so a change that breaks a trust
property fails CI rather than quietly degrading answers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amin.answer import Amin
from amin.config import settings
from amin.covenant import Covenant
from amin.ingest import chunk_document, ingest, make_document, split_front_matter
from amin.providers import EchoProvider, HashEmbedder
from amin.schema import Outcome, Tier, Verdict
from amin.store import Store
from amin.verifier import Verifier, lexical_support

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "data" / "corpus"


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> Store:
    path = tmp_path_factory.mktemp("index") / "test.db"
    s = Store(path)
    docs, chunks = ingest(CORPUS)
    s.upsert(docs, chunks, HashEmbedder()([c.text for c in chunks]))
    return s


@pytest.fixture(scope="module")
def amin(store) -> Amin:
    provider = EchoProvider()
    return Amin(store=store, provider=provider, verifier=Verifier(provider, mode="lexical"))


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------


def test_front_matter_is_parsed_and_tiers_are_honoured():
    doc, body = make_document(CORPUS / "fridge-manual.md", CORPUS)
    assert doc.doc_id == "fridge-manual"
    assert doc.tier is Tier.PRIMARY
    assert "---" not in body.split("\n")[0]


def test_front_matter_absent_is_not_an_error():
    parsed = split_front_matter("# Heading\n\nbody text")
    assert parsed.meta == {}
    assert parsed.body.startswith("# Heading")


def test_chunks_never_straddle_headings():
    doc, body = make_document(CORPUS / "tenancy-agreement.md", CORPUS)
    chunks = chunk_document(doc, body)
    assert len(chunks) >= 4
    headings = {c.heading for c in chunks}
    assert "Notice and renewal" in headings
    # A chunk carries exactly one heading, so a citation points at one clause.
    notice = [c for c in chunks if c.heading == "Notice and renewal"]
    assert any("90 days" in c.text for c in notice)
    assert all("Security deposit" not in c.text for c in notice)


def test_chunk_ids_are_stable_across_runs():
    doc, body = make_document(CORPUS / "insurance-policy.md", CORPUS)
    first = [c.chunk_id for c in chunk_document(doc, body)]
    second = [c.chunk_id for c in chunk_document(doc, body)]
    assert first == second


# ---------------------------------------------------------------------------
# retrieval
# ---------------------------------------------------------------------------


def test_index_contains_every_corpus_document(store):
    stats = store.stats()
    assert stats["documents"] == len(list(CORPUS.glob("*.md")))
    assert stats["chunks"] > 20


def test_hybrid_retrieval_finds_the_right_clause(store):
    hits = store.search("how much notice before the tenancy expires", HashEmbedder()(["how much notice before the tenancy expires"])[0])
    assert hits
    assert any("90 days" in h.chunk.text for h in hits[:3])


def test_lexical_arm_works_without_a_query_vector(store):
    hits = store.search("ALF-9 water filter cartridge", None)
    assert any("ALF-9" in h.chunk.text for h in hits)


def test_arabic_query_retrieves_the_arabic_document(store):
    q = "كم مدة الإشعار قبل انتهاء العقد"
    hits = store.search(q, HashEmbedder()([q])[0])
    assert any(h.chunk.doc_id == "ar-tenancy-summary" for h in hits)


def test_dimension_mismatch_is_a_clear_error(store):
    import numpy as np

    with pytest.raises(ValueError, match="different embedding model"):
        store.dense(np.zeros(7, dtype="float32"), 3)


# ---------------------------------------------------------------------------
# verifier
# ---------------------------------------------------------------------------


def test_invented_figure_is_rejected_even_with_high_word_overlap():
    passage = "The annual rent is AED 78,000, payable in four equal cheques of AED 19,500."
    ok, note = lexical_support("The annual rent is AED 92,000 payable in four cheques.", passage)
    assert not ok
    assert "figure" in note


def test_true_claim_with_matching_figures_is_supported():
    passage = "The annual rent is AED 78,000, payable in four equal cheques of AED 19,500."
    ok, _ = lexical_support("The annual rent is AED 78,000.", passage)
    assert ok


def test_topically_related_but_unstated_claim_is_rejected():
    passage = "Error code E1 indicates a fresh food compartment thermistor fault."
    ok, _ = lexical_support("The compressor must be replaced by an engineer.", passage)
    assert not ok


def test_unsupported_claims_are_removed_from_the_answer():
    provider = EchoProvider()
    verifier = Verifier(provider, mode="lexical")
    claims = verifier.verify_draft(
        "The deposit is AED 3,900. [S1] The deposit is AED 9,000. [S1]",
        {"S1": "c1"},
        {"c1": "Clause 11.1 - The security deposit is AED 3,900, equal to 5 percent."},
    )
    verdicts = {c.text: c.verdict for c in claims}
    assert any(v is Verdict.SUPPORTED for v in verdicts.values())
    assert any(v is Verdict.UNSUPPORTED for v in verdicts.values())
    assert Amin._apply_verification(claims) == [c for c in claims if c.verdict is Verdict.SUPPORTED]


# ---------------------------------------------------------------------------
# covenant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question,route",
    [
        ("Should I take ibuprofen for this headache?", "medical"),
        ("What dosage of paracetamol is right for a nine year old?", "medical"),
        ("Am I liable if the leak floods the flat below mine?", "legal"),
        ("Can I sue the landlord for not repairing the AC?", "legal"),
        ("Is bitcoin a good investment right now?", "financial"),
    ],
)
def test_out_of_scope_questions_are_routed(question, route):
    decision = Covenant().check(question)
    assert not decision.allowed
    assert decision.route is not None
    assert decision.route.name == route
    assert decision.route.refer_to


def test_in_scope_questions_are_allowed():
    assert Covenant().check("How much is the security deposit?").allowed


def test_routing_happens_even_when_the_corpus_has_the_document(amin):
    """The tenancy contract is indexed, but legal advice is still refused."""
    answer = amin.ask("Can I sue the landlord for not repairing the central air conditioning?")
    assert answer.outcome is Outcome.REFUSED_OUT_OF_SCOPE
    assert answer.routed_to == "legal"
    assert not answer.claims


# ---------------------------------------------------------------------------
# end to end
# ---------------------------------------------------------------------------


def test_grounded_question_is_answered_with_a_real_citation(amin):
    answer = amin.ask("What is the part number for the fridge water filter cartridge?")
    assert answer.outcome is Outcome.ANSWERED
    assert "ALF-9" in answer.text
    assert any(s["doc_id"] == "fridge-manual" for s in answer.sources())
    assert answer.citation_precision > 0


def test_question_with_no_source_is_refused_not_answered(amin):
    answer = amin.ask("What is the capital of Burkina Faso?")
    assert answer.refused, f"expected refusal, got: {answer.text!r}"
    assert not answer.asserted


def test_every_shown_claim_either_verified_or_is_labelled(amin):
    answer = amin.ask("How much notice must I give before the tenancy expires?")
    for claim in answer.claims:
        assert claim.verdict is not Verdict.UNSUPPORTED
        if claim.verdict is Verdict.UNCITED:
            assert not claim.cited_chunk_ids


def test_sources_are_resolvable_back_to_indexed_chunks(amin, store):
    answer = amin.ask("What is the standard excess on a contents insurance claim?")
    for source in answer.sources():
        assert store.get_chunk(source["chunk_id"]) is not None


def test_settings_evidence_floor_is_the_single_refusal_dial(amin, monkeypatch):
    """Raising the floor must turn an answered question into a refusal."""
    q = "What is the recommended freezer temperature?"
    assert amin.ask(q).outcome is Outcome.ANSWERED
    monkeypatch.setattr(settings, "evidence_floor", 10.0)
    assert amin.ask(q).refused


# -- identifier gate (E16 / E18 near-miss hole) -------------------------------


@pytest.mark.parametrize(
    "question, expected",
    [
        ("How long is the warranty on the ArcticLine FR-550?", {"fr-550"}),
        ("How much does the Freedom 300 plan cost?", {"freedom 300"}),
        ("What is the pass mark for PHY-205?", {"phy-205"}),
        ("How much notice must I give before the tenancy expires?", set()),
    ],
)
def test_question_identifiers(question, expected):
    from amin.covenant import question_identifiers

    assert question_identifiers(question) == expected


def test_sibling_model_number_is_refused_not_answered(amin):
    """A question about a product the corpus does not cover must not be
    answered from the manual of its neighbour, however well the rest matches."""
    answer = amin.ask("What is the recommended freezer temperature on the ZX-9999?")
    assert answer.refused
    assert "zx-9999" in answer.refusal_reason.lower()


def test_identifier_gate_can_be_turned_off(amin, monkeypatch):
    monkeypatch.setattr(settings, "identifier_gate", False)
    answer = amin.ask("What is the recommended freezer temperature on the ZX-9999?")
    assert "zx-9999" not in (answer.refusal_reason or "").lower()
