"""Slice m: the amin-3 final test (docs/EXPERIMENTS.md, E30).

Used exactly once. A final test that shares questions with the training
items, the main set, or the slices used before it measures memory, not the
model. So slice m must share no question with the training items, the main
eval set, slice j or slice k - not even a 6-gram.
"""

from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from amin.evaluate import load_items

REPO = Path(__file__).resolve().parent.parent
SLICE_M = REPO / "data" / "eval" / "eval_slice_m.jsonl"

_spec = importlib.util.spec_from_file_location("build_eval_set", REPO / "scripts" / "build_eval_set.py")
bes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bes)


def _rows() -> list[dict]:
    return [json.loads(line) for line in SLICE_M.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_slice_m_file_is_what_the_builder_writes():
    assert _rows() == bes.build_slice_m(), "run: uv run python scripts/build_eval_set.py"


def test_slice_m_has_the_planned_mix():
    items = load_items(SLICE_M)
    by_tag = Counter(i.tags[0] for i in items)
    english = Counter(i.tags[0] for i in items if i.lang == "en")
    assert english == {"adjacent-fact": 30, "adjacent-sibling": 30, "fresh": 30, "doc-silent": 25, "general": 15}
    assert sum(by_tag.values()) - sum(english.values()) == 10  # Arabic, spread across the kinds
    assert all(by_tag[t] > english[t] for t in by_tag)
    assert all(i.id.startswith("m") for i in items)
    assert all(i.expect_general for i in items if "general" in i.tags)
    assert not any(i.expect_general for i in items if "doc-silent" in i.tags or "adjacent-fact" in i.tags)


def test_slice_m_is_valid_and_shares_no_question_with_training_main_or_slices_j_and_k():
    assert bes.validate_slice_m(bes.build_slice_m(), bes.build()) == []


@pytest.mark.parametrize("name", sorted(bes.OTHER_SLICES))
def test_slice_m_overlap_check_sees_the_earlier_slices(name):
    # Slices j and k live on their own branches until merged; the check must still see them.
    if bes.slice_questions(*bes.OTHER_SLICES[name]) is None:
        pytest.skip(f"{name} is neither merged nor reachable through git")
    assert len(bes.slice_questions(*bes.OTHER_SLICES[name])) in {100, 160}


def test_overlap_check_catches_exact_repeats_and_shared_6grams():
    m = [{"id": "m1", "question": "How long is the warranty on the ArcticLine FR-440?"},
         {"id": "m2", "question": "So how long is the warranty on the fridge?"},
         {"id": "m3", "question": "What is the capital of Peru?"}]
    others = {"main": ["How long is the warranty on the ArcticLine FR-440?",
                       "Tell me how long is the warranty on the fridge"]}
    problems = bes.overlaps(m, others)
    assert any(p.startswith("m1 repeats") for p in problems)
    assert any(p.startswith("m2 shares") for p in problems)
    assert not any(p.startswith("m3") for p in problems)
