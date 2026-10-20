"""Slice k: the amin-2 checkpoint-selection slice (docs/TRAINING.md, Round 2).

A checkpoint chosen on questions the model trained on, or on the final test's
questions, is chosen on memory. So slice k must share no question with the
training items, the main eval set or slice j - not even a 6-gram.
"""

from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from amin.evaluate import load_items

REPO = Path(__file__).resolve().parent.parent
SLICE_K = REPO / "data" / "eval" / "eval_slice_k.jsonl"

_spec = importlib.util.spec_from_file_location("build_eval_set", REPO / "scripts" / "build_eval_set.py")
bes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bes)


def _rows() -> list[dict]:
    return [json.loads(line) for line in SLICE_K.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_slice_k_file_is_what_the_builder_writes():
    assert _rows() == bes.build_slice_k(), "run: uv run python scripts/build_eval_set.py"


def test_slice_k_has_the_planned_mix():
    items = load_items(SLICE_K)
    assert Counter(i.tags[0] for i in items) == {
        "adjacent-fact": 40, "adjacent-sibling": 40, "fresh": 40, "general": 20, "personal": 20,
    }
    assert all(i.id.startswith("k") for i in items)
    assert all(i.expect_general for i in items if "general" in i.tags)
    assert not any(i.expect_general for i in items if "personal" in i.tags)


def test_slice_k_is_valid_and_shares_no_question_with_training_main_or_slice_j():
    assert bes.validate_slice_k(bes.build_slice_k(), bes.build()) == []


def test_slice_k_overlap_check_runs_against_slice_j():
    # Slice j lives on its own branch until merged; the check must still see it.
    if bes.slice_j_questions() is None:
        pytest.skip("slice j is neither merged nor reachable through git")
    assert len(bes.slice_j_questions()) == 100


def test_overlap_check_catches_exact_repeats_and_shared_6grams():
    k = [{"id": "k1", "question": "How long is the warranty on the ArcticLine FR-440?"},
         {"id": "k2", "question": "So how long is the warranty on the fridge?"},
         {"id": "k3", "question": "What is the capital of Mongolia?"}]
    others = {"main": ["How long is the warranty on the ArcticLine FR-440?",
                       "Tell me how long is the warranty on the fridge"]}
    problems = bes.overlaps(k, others)
    assert any(p.startswith("k1 repeats") for p in problems)
    assert any(p.startswith("k2 shares") for p in problems)
    assert not any(p.startswith("k3") for p in problems)
