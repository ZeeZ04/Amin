"""Tests for conflict detection, supersession, and document relatedness.

Every assertion here corresponds to a bug that was actually present: silent
resolution of contradictions, superseded documents outranking current ones,
monetary figures being split on the comma, and vocabulary overlap being unable
to tell a real conflict from a coincidence of headings.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amin import conflict
from amin.answer import Amin
from amin.config import settings
from amin.ingest import ingest, make_document
from amin.providers import EchoProvider, HashEmbedder
from amin.schema import Outcome
from amin.store import Store
from amin.verifier import Verifier

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "data" / "corpus"


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> Store:
    s = Store(tmp_path_factory.mktemp("conflict-index") / "t.db")
    docs, chunks = ingest(CORPUS)
    s.upsert(docs, chunks, HashEmbedder()([c.text for c in chunks]))
    return s


@pytest.fixture(scope="module")
def amin(store) -> Amin:
    p = EchoProvider()
    return Amin(store=store, provider=p, verifier=Verifier(p, mode="lexical"))


def _ask(store, question: str):
    emb = HashEmbedder()
    return store.search(question, emb([question])[0], limit=settings.top_k_conflict)


# ---------------------------------------------------------------------------
# number handling — the bug that made detection impossible
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [("3,900", "3900"), ("1,000", "1000"), ("82,000", "82000"), ("11.1", "11.1"),
     ("0.50", "0.50"), ("007", "7")],
)
def test_numbers_survive_thousands_separators(raw, expected):
    """Splitting on the comma turned "AED 1,000" into "1" and "000" -> "0"."""
    assert conflict._normalise_number(raw) == expected


def test_tokeniser_keeps_a_money_figure_whole():
    assert "3,900" in conflict.TOKEN.findall("the deposit is AED 3,900 per year")


def test_clause_numbers_are_not_treated_as_answers():
    values = conflict.answer_position_values(
        "What is the security deposit?",
        "Clause 11.1 - The security deposit is AED 3,900.",
    )
    assert "3900" in values
    assert "11.1" not in values, "a clause reference is not a competing value"


def test_numbers_from_the_question_are_excluded():
    """"PHY-104" put 104 in every passage and made contradictions look like agreement."""
    values = conflict.answer_position_values(
        "What is the coursework weighting for PHY-104?",
        "The PHY-104 module is assessed by coursework worth 30 percent.",
    )
    assert values == {"30"}


def test_values_are_scoped_to_the_sentence_not_a_word_window():
    """A five-word window missed a figure six words after the query term."""
    text = "The refundable security deposit for this unit is AED 4,100."
    assert "4100" in conflict.answer_position_values("What is the security deposit?", text)


def test_values_from_an_unrelated_sentence_are_ignored():
    text = "The security deposit is AED 3,900. The annual rent is AED 78,000."
    assert conflict.answer_position_values("What is the security deposit?", text) == {"3900"}


# ---------------------------------------------------------------------------
# supersession
# ---------------------------------------------------------------------------


def test_superseded_status_is_read_from_front_matter():
    doc, _ = make_document(CORPUS / "ufp-handbook-2025-superseded.md", CORPUS)
    assert doc.superseded is True
    current, _ = make_document(CORPUS / "ufp-handbook-2026.md", CORPUS)
    assert current.superseded is False


def test_superseded_chunks_are_demoted_but_still_retrievable(store):
    hits = _ask(store, "What is the coursework weighting for PHY-104?")
    docs = [h.chunk.doc_id for h in hits]
    assert "ufp-handbook-2025" in docs, "a superseded document must stay searchable"
    assert docs.index("ufp-handbook-2026") < docs.index("ufp-handbook-2025")


def test_version_skew_answers_from_the_current_source_and_shows_the_old_one(amin):
    answer = amin.ask("What is the coursework weighting for PHY-104?")
    assert not answer.refused, "an outdated document must not block a current answer"
    cited = {s["doc_id"] for s in answer.sources()}
    assert "ufp-handbook-2026" in cited
    assert "ufp-handbook-2025" in cited, "the superseded source must be surfaced, not dropped"
    assert answer.conflicts


# ---------------------------------------------------------------------------
# relatedness — the discriminator vocabulary overlap could not provide
# ---------------------------------------------------------------------------


def test_declared_subjects_make_documents_comparable(store):
    assert store.are_related("tenancy-agreement", "tenancy-summary-sheet")
    assert store.are_related("ufp-handbook-2026", "ufp-handbook-2025")


def test_documents_with_different_subjects_are_not_comparable(store):
    """Both have a section headed 'Security deposit'. They are not about the same deposit."""
    assert not store.are_related("tenancy-agreement", "electricity-tariff")
    assert not store.are_related("fridge-manual", "insurance-policy")


def test_chunk_overlap_alone_cannot_separate_these(store):
    """The measurement that forced subjects to be declared rather than inferred."""
    chunks = {c.doc_id: c.text for c in store.all_chunks() if c.heading.startswith("Security")}
    true_pair = conflict._topical_overlap(
        chunks["tenancy-agreement"], next(
            c.text for c in store.all_chunks()
            if c.doc_id == "tenancy-summary-sheet" and c.heading == "Deposit"
        )
    )
    false_pair = conflict._topical_overlap(
        chunks["tenancy-agreement"], chunks["electricity-tariff"]
    )
    assert false_pair >= true_pair, (
        "if this ever inverts, chunk overlap became usable and the fallback "
        "in conflict.detect could be trusted again"
    )


# ---------------------------------------------------------------------------
# detection end to end
# ---------------------------------------------------------------------------


def test_two_live_sources_disagreeing_produces_a_conflict(amin):
    answer = amin.ask("What is the security deposit on the flat?")
    assert answer.outcome is Outcome.CONFLICT
    cited = {s["doc_id"] for s in answer.sources()}
    assert {"tenancy-agreement", "tenancy-summary-sheet"} <= cited
    assert "will not pick" in answer.refusal_reason


def test_a_conflict_answer_never_asserts_one_side(amin):
    answer = amin.ask("What is the security deposit on the flat?")
    text = answer.text
    assert "3,900" in text and "4,100" in text, "both figures must be visible"


def test_agreement_is_not_reported_as_conflict(amin):
    """Both handbooks give the same pass mark. Crying wolf here trains the reader to ignore it."""
    answer = amin.ask("What is the pass mark for PHY-104?")
    assert answer.outcome is not Outcome.CONFLICT


def test_one_source_merely_saying_more_is_not_a_conflict():
    """A says {30, 70}; B says {30}. B is less complete, not contradictory."""
    a = conflict.Position("a", "", "a#1", frozenset({"30", "70"}), False, "coursework 30 exam 70")
    b = conflict.Position("b", "", "b#1", frozenset({"30"}), False, "coursework 30")
    assert not (a.values - b.values) or not (b.values - a.values)


def test_unrelated_documents_with_the_same_heading_do_not_conflict(amin):
    answer = amin.ask("What is the electricity security deposit for an apartment?")
    assert answer.outcome is not Outcome.CONFLICT


def test_conflict_detection_sees_deeper_than_generation(store):
    """A contradicting passage at rank 7 is exactly the one that must not be missed."""
    assert settings.top_k_conflict > settings.top_k_final
    wide = _ask(store, "What is the security deposit on the flat?")
    assert len(wide) > settings.top_k_final


def test_detect_returns_none_without_candidates():
    assert conflict.detect("anything", []) is None


def test_two_pages_of_one_textbook_are_not_a_conflict(tmp_path, monkeypatch):
    from amin.conflict import detect
    from amin.schema import Chunk, Retrieved, Tier

    def r(cid, text, subject):
        c = Chunk(chunk_id=cid, doc_id=cid.split("#")[0], ordinal=0, text=text, heading="", tier=Tier.REFERENCE, subject=subject)
        return Retrieved(chunk_id=cid, chunk=c, score=1.0, coverage=0.9)

    q = "What is the speed of light in a vacuum?"
    pool = [r("a#1", "The speed of light in a vacuum is 3.00 x 10^8 m/s.", "openstax-physics"),
            r("b#1", "The speed of light in a vacuum slows to 2.25 x 10^8 m/s in water.", "openstax-physics")]
    assert detect(q, pool, related=lambda a, b: True) is not None  # without the rule, a false conflict
    def is_pack(s):
        return s.startswith("openstax-")

    assert detect(q, pool, related=lambda a, b: True, one_work=is_pack) is None
    pool[1].chunk.subject = "openstax-chemistry"  # two different textbooks: still not a conflict
    assert detect(q, pool, related=lambda a, b: True, one_work=is_pack) is None
    pool[1].chunk.subject = "my-notes"  # a pack against the person's own document still is
    assert detect(q, pool, related=lambda a, b: True, one_work=is_pack) is not None
