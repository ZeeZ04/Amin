"""Tests for the eval harness itself.

If the harness is wrong, every number in the README is wrong, so the grader is
tested against hand-built answers rather than only against live pipeline runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amin.evaluate import Item, Result, grade, load_items, metrics
from amin.schema import Answer, Chunk, Claim, Outcome, Retrieved, Verdict

REPO = Path(__file__).resolve().parent.parent


def _answer(**kw) -> Answer:
    return Answer(question=kw.pop("question", "q"), **kw)


def _cited_answer(text: str, doc_id: str) -> Answer:
    chunk = Chunk(chunk_id=f"{doc_id}#001-aaa", doc_id=doc_id, ordinal=1, text=text)
    return _answer(
        outcome=Outcome.ANSWERED,
        claims=[
            Claim(text=text, cited_chunk_ids=[chunk.chunk_id], verdict=Verdict.SUPPORTED)
        ],
        retrieved=[Retrieved(chunk=chunk, score=1.0)],
    )


# ---------------------------------------------------------------------------
# the eval set itself
# ---------------------------------------------------------------------------


def test_eval_set_is_wellformed():
    items = load_items(REPO / "data" / "eval" / "eval_set.jsonl")
    assert len(items) >= 25
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids)), "duplicate eval ids"
    for item in items:
        assert item.kind in {"answerable", "unanswerable", "out_of_scope"}
        if item.kind == "answerable":
            assert item.expect_any, f"{item.id} has no expected fact"
            assert item.expect_doc, f"{item.id} does not pin a source document"
        if item.kind == "out_of_scope":
            assert item.expect_route, f"{item.id} does not pin a route"
        if item.kind == "unanswerable":
            assert item.note, f"{item.id} must explain why it is unanswerable"


def test_eval_set_covers_all_three_kinds_meaningfully():
    items = load_items(REPO / "data" / "eval" / "eval_set.jsonl")
    counts = {k: sum(i.kind == k for i in items) for k in
              ("answerable", "unanswerable", "out_of_scope")}
    # The unanswerable slice is the point of the harness; keep it substantial.
    assert counts["unanswerable"] >= 6
    assert counts["answerable"] >= 12
    assert counts["out_of_scope"] >= 4


def test_every_answerable_item_names_a_document_that_exists():
    items = load_items(REPO / "data" / "eval" / "eval_set.jsonl")
    present = {p.stem for p in (REPO / "data" / "corpus").glob("*.md")}
    # doc ids come from front matter `id`, which may differ from the filename
    import yaml

    for path in (REPO / "data" / "corpus").glob("*.md"):
        head = path.read_text(encoding="utf-8").split("---")
        if len(head) > 2:
            meta = yaml.safe_load(head[1]) or {}
            if isinstance(meta, dict) and meta.get("id"):
                present.add(str(meta["id"]))
    for item in items:
        if item.expect_doc:
            assert item.expect_doc in present, f"{item.id} expects missing doc {item.expect_doc}"


# ---------------------------------------------------------------------------
# grading
# ---------------------------------------------------------------------------


def test_answerable_passes_on_correct_fact_and_correct_source():
    item = Item(id="x", question="q", kind="answerable",
                expect_any=["AED 3,900"], expect_doc="tenancy-agreement")
    passed, why = grade(item, _cited_answer("The deposit is AED 3,900.", "tenancy-agreement"))
    assert passed, why


def test_answerable_fails_when_the_fact_is_right_but_the_source_is_wrong():
    item = Item(id="x", question="q", kind="answerable",
                expect_any=["AED 3,900"], expect_doc="tenancy-agreement")
    passed, why = grade(item, _cited_answer("The deposit is AED 3,900.", "insurance-policy"))
    assert not passed
    assert "cited" in why


def test_answerable_fails_on_refusal():
    item = Item(id="x", question="q", kind="answerable", expect_any=["anything"],
                expect_doc="d")
    passed, _ = grade(item, _answer(outcome=Outcome.REFUSED_NO_EVIDENCE,
                                    refusal_reason="no source"))
    assert not passed


def test_comma_and_case_differences_do_not_fail_a_correct_answer():
    item = Item(id="x", question="q", kind="answerable",
                expect_any=["AED 19,500"], expect_doc="tenancy-agreement")
    passed, _ = grade(item, _cited_answer("each cheque is aed 19500", "tenancy-agreement"))
    assert passed


def test_unanswerable_passes_only_on_refusal():
    item = Item(id="u", question="q", kind="unanswerable", note="no source")
    refused = _answer(outcome=Outcome.REFUSED_NO_EVIDENCE, refusal_reason="no source")
    assert grade(item, refused)[0]
    asserted = _cited_answer("The warranty is 24 months.", "fridge-manual")
    assert not grade(item, asserted)[0]


def test_out_of_scope_requires_the_right_route():
    item = Item(id="o", question="q", kind="out_of_scope", expect_route="medical")
    right = _answer(outcome=Outcome.REFUSED_OUT_OF_SCOPE, routed_to="medical")
    wrong = _answer(outcome=Outcome.REFUSED_OUT_OF_SCOPE, routed_to="legal")
    answered = _cited_answer("Take two.", "fridge-manual")
    assert grade(item, right)[0]
    assert not grade(item, wrong)[0]
    assert not grade(item, answered)[0]


def test_a_no_evidence_refusal_does_not_count_as_correct_routing():
    """An out-of-scope question that merely found nothing is still a failure."""
    item = Item(id="o", question="q", kind="out_of_scope", expect_route="medical")
    passed, why = grade(item, _answer(outcome=Outcome.REFUSED_NO_EVIDENCE))
    assert not passed
    assert "not routed" in why


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def _result(kind: str, passed: bool, answer: Answer) -> Result:
    return Result(item=Item(id=kind, question="q", kind=kind), answer=answer,
                  passed=passed, why="")


def test_hallucination_rate_counts_assertions_on_unanswerable_items():
    results = [
        _result("unanswerable", False, _cited_answer("The warranty is 24 months.", "fridge-manual")),
        _result("unanswerable", True, _answer(outcome=Outcome.REFUSED_NO_EVIDENCE)),
        _result("unanswerable", True, _answer(outcome=Outcome.REFUSED_NO_EVIDENCE)),
        _result("unanswerable", True, _answer(outcome=Outcome.REFUSED_NO_EVIDENCE)),
    ]
    stats = metrics(results)
    assert stats["hallucination_rate"] == pytest.approx(0.25)
    assert stats["correct_refusal"] == pytest.approx(0.75)


def test_metrics_do_not_divide_by_zero_on_an_empty_slice():
    stats = metrics([_result("answerable", True, _cited_answer("x 1", "d"))])
    assert stats["correct_refusal"] == 0.0
    assert stats["routing_accuracy"] == 0.0
    assert stats["grounded_accuracy"] == 1.0


def test_citation_precision_ignores_answers_with_no_citations_at_all():
    uncited = _answer(
        outcome=Outcome.ANSWERED,
        claims=[Claim(text="Probably fine.", verdict=Verdict.UNCITED)],
    )
    stats = metrics([
        _result("answerable", True, _cited_answer("The deposit is AED 3,900.", "tenancy-agreement")),
        _result("answerable", False, uncited),
    ])
    assert stats["citation_precision"] == pytest.approx(1.0)
