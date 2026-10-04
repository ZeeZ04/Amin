"""Tests for the eval harness itself.

If the harness is wrong, every number in the README is wrong, so the grader is
tested against hand-built answers rather than only against live pipeline runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amin.evaluate import Item, Result, grade, load_items, metrics, trust_score
from amin.schema import Answer, Chunk, Claim, Outcome, Retrieved, Verdict

REPO = Path(__file__).resolve().parent.parent
EVAL_SET = REPO / "data" / "eval" / "eval_set.jsonl"


def _answer(**kw) -> Answer:
    return Answer(question=kw.pop("question", "q"), **kw)


def _cited_answer(text: str, doc_id: str) -> Answer:
    chunk = Chunk(chunk_id=f"{doc_id}#001-aaa", doc_id=doc_id, ordinal=1, text=text)
    return _answer(
        outcome=Outcome.ANSWERED,
        claims=[Claim(text=text, cited_chunk_ids=[chunk.chunk_id], verdict=Verdict.SUPPORTED)],
        retrieved=[Retrieved(chunk=chunk, score=1.0, coverage=1.0)],
    )


def _uncited_answer(text: str) -> Answer:
    return _answer(
        outcome=Outcome.ANSWERED, claims=[Claim(text=text, verdict=Verdict.UNCITED)]
    )


# ---------------------------------------------------------------------------
# the eval set itself
# ---------------------------------------------------------------------------


def test_eval_set_is_wellformed():
    items = load_items(EVAL_SET)
    assert len(items) >= 150, "too small for ±10pp intervals; see scripts/build_eval_set.py"
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids)), "duplicate eval ids"
    questions = [i.question for i in items]
    assert len(questions) == len(set(questions)), "duplicate questions inflate apparent n"
    for item in items:
        assert item.kind in {"answerable", "unanswerable", "out_of_scope"}
        if item.kind == "answerable":
            assert item.expect_any, f"{item.id} has no expected fact"
            assert item.expect_doc, f"{item.id} does not pin a source document"
        if item.kind == "out_of_scope":
            assert item.expect_route, f"{item.id} does not pin a route"
        if item.kind == "unanswerable":
            assert item.note, f"{item.id} must explain why it is unanswerable"


def test_eval_set_slices_are_large_enough_to_be_useful():
    items = load_items(EVAL_SET)
    counts = {
        k: sum(i.kind == k for i in items)
        for k in ("answerable", "unanswerable", "out_of_scope")
    }
    # The unanswerable slice is the hallucination metric. It is the whole point.
    assert counts["unanswerable"] >= 30
    assert counts["answerable"] >= 97, "below the n needed for a ±10pp interval"
    assert counts["out_of_scope"] >= 20


def test_eval_set_covers_the_designed_traps():
    tags = {t for i in load_items(EVAL_SET) for t in i.tags}
    for trap in ("near-miss", "false-premise", "prior-leak", "silent"):
        assert trap in tags, f"no {trap} items — the set cannot catch that failure mode"


def test_eval_set_has_arabic_on_both_sides():
    items = load_items(EVAL_SET)
    ar = [i for i in items if i.lang == "ar"]
    assert len(ar) >= 10
    assert any(i.kind == "answerable" for i in ar)
    assert any(i.kind == "unanswerable" for i in ar), (
        "Arabic answerable items without Arabic unanswerable items would measure "
        "retrieval but not refusal"
    )


def test_every_answerable_item_names_a_document_that_exists():
    import yaml

    present = {p.stem for p in (REPO / "data" / "corpus").glob("*.md")}
    for path in (REPO / "data" / "corpus").glob("*.md"):
        parts = path.read_text(encoding="utf-8").split("---")
        if len(parts) > 2:
            meta = yaml.safe_load(parts[1]) or {}
            if isinstance(meta, dict) and meta.get("id"):
                present.add(str(meta["id"]))
    for item in load_items(EVAL_SET):
        if item.expect_doc:
            assert item.expect_doc in present, f"{item.id} expects missing doc {item.expect_doc}"


# ---------------------------------------------------------------------------
# grading
# ---------------------------------------------------------------------------


def test_answerable_passes_on_correct_fact_and_correct_source():
    item = Item(id="x", question="q", kind="answerable",
                expect_any=["AED 3,900"], expect_doc="tenancy-agreement")
    r = grade(item, _cited_answer("The deposit is AED 3,900.", "tenancy-agreement"))
    assert r.passed and r.fact_ok and r.grounded_ok, r.why


def test_answerable_fails_when_the_fact_is_right_but_the_source_is_wrong():
    item = Item(id="x", question="q", kind="answerable",
                expect_any=["AED 3,900"], expect_doc="tenancy-agreement")
    r = grade(item, _cited_answer("The deposit is AED 3,900.", "insurance-policy"))
    assert r.fact_ok, "the fact was present"
    assert not r.grounded_ok and not r.passed
    assert "cited" in r.why


def test_a_non_citing_system_is_graded_on_facts_not_citations():
    """Scoring a bare model on grounded accuracy would guarantee zero and prove nothing."""
    item = Item(id="x", question="q", kind="answerable",
                expect_any=["AED 3,900"], expect_doc="tenancy-agreement")
    answer = _uncited_answer("The deposit is AED 3,900.")
    citing = grade(item, answer, cites=True)
    non_citing = grade(item, answer, cites=False)
    assert citing.fact_ok and non_citing.fact_ok
    assert not citing.passed, "a citing system that failed to cite has not passed"
    assert non_citing.passed, "a non-citing system must be judged on the fact alone"


def test_answerable_fails_on_refusal():
    item = Item(id="x", question="q", kind="answerable", expect_any=["anything"], expect_doc="d")
    r = grade(item, _answer(outcome=Outcome.REFUSED_NO_EVIDENCE, refusal_reason="no source"))
    assert not r.passed and not r.fact_ok


def test_comma_and_case_differences_do_not_fail_a_correct_answer():
    item = Item(id="x", question="q", kind="answerable",
                expect_any=["AED 19,500"], expect_doc="tenancy-agreement")
    assert grade(item, _cited_answer("each cheque is aed 19500", "tenancy-agreement")).passed


def test_unanswerable_passes_only_on_refusal():
    item = Item(id="u", question="q", kind="unanswerable", note="no source")
    assert grade(item, _answer(outcome=Outcome.REFUSED_NO_EVIDENCE)).passed
    assert not grade(item, _cited_answer("The warranty is 24 months.", "fridge-manual")).passed


def test_out_of_scope_requires_the_right_route():
    item = Item(id="o", question="q", kind="out_of_scope", expect_route="medical")
    assert grade(item, _answer(outcome=Outcome.REFUSED_OUT_OF_SCOPE, routed_to="medical")).passed
    assert not grade(
        item, _answer(outcome=Outcome.REFUSED_OUT_OF_SCOPE, routed_to="legal")
    ).passed
    assert not grade(item, _cited_answer("Take two.", "fridge-manual")).passed


def test_declining_without_routing_is_not_a_pass():
    """A baseline that says 'I don't know' has not routed to a referral."""
    item = Item(id="o", question="q", kind="out_of_scope", expect_route="medical")
    r = grade(item, _answer(outcome=Outcome.REFUSED_NO_EVIDENCE))
    assert not r.passed
    assert "did not route" in r.why


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def _result(kind: str, answer: Answer, cites: bool = True) -> Result:
    return grade(Item(id=kind, question="q", kind=kind, note="n"), answer, cites=cites)


def test_hallucination_rate_counts_assertions_on_unanswerable_items():
    results = [
        _result("unanswerable", _cited_answer("The warranty is 24 months.", "fridge-manual")),
        *[_result("unanswerable", _answer(outcome=Outcome.REFUSED_NO_EVIDENCE)) for _ in range(3)],
    ]
    stats = metrics(results)
    assert stats["hallucination_rate"] == pytest.approx(0.25)
    assert stats["correct_refusal"] == pytest.approx(0.75)


def test_every_proportion_carries_a_confidence_interval():
    results = [_result("unanswerable", _answer(outcome=Outcome.REFUSED_NO_EVIDENCE))]
    ci = metrics(results)["ci"]
    for key in ("fact_accuracy", "grounded_accuracy", "correct_refusal", "hallucination_rate"):
        assert key in ci
        assert ci[key]["low"] <= ci[key]["point"] <= ci[key]["high"]


def test_a_single_item_produces_a_uselessly_wide_interval():
    """The guard against reading a 1-item result as a finding."""
    ci = metrics([_result("unanswerable", _answer(outcome=Outcome.REFUSED_NO_EVIDENCE))])["ci"]
    width = ci["correct_refusal"]["high"] - ci["correct_refusal"]["low"]
    assert width > 0.5


def test_metrics_do_not_divide_by_zero_on_an_empty_slice():
    stats = metrics([])
    assert stats["correct_refusal"] == 0.0
    assert stats["routing_accuracy"] == 0.0
    assert stats["n"] == 0


def test_trust_score_punishes_hallucination_harder_than_a_missed_answer():
    confident = {"grounded_accuracy": 0.9, "hallucination_rate": 0.3}
    cautious = {"grounded_accuracy": 0.6, "hallucination_rate": 0.0}
    assert trust_score(cautious) > trust_score(confident)
    # and the weight is what does it, so it must be adjustable
    assert trust_score(confident, hallucination_weight=0.0) > trust_score(
        cautious, hallucination_weight=0.0
    )
