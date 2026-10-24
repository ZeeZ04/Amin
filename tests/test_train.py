"""Tests for the post-training data (ADR-012).

The one that matters most is contamination: if training data overlaps the eval
set, every benchmark after training measures memory, not behaviour. That is
checked here on every commit rather than promised in a doc.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from amin.covenant import Covenant
from amin.evaluate import Item, grade, load_items
from amin.ingest import split_front_matter
from amin.prompts import ANSWER_SYSTEM, answer_prompt
from amin.providers import EchoProvider
from amin.schema import Answer, Chunk, Outcome, Retrieved
from amin.train import corpus
from amin.train.distill import RecordingProvider, _shuffle_passages, sft_examples
from amin.train.preferences import dpo_rows, teacher_replies

REPO = Path(__file__).resolve().parent.parent
EVAL_CORPUS = REPO / "data" / "corpus"


@pytest.fixture(scope="module")
def built():
    return corpus.build(seed=7)


def _ngrams(text: str, n: int = 8) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.lower())
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def _norm(q: str) -> str:
    return " ".join(re.findall(r"\w+", q.lower()))


# ---------------------------------------------------------------------------
# contamination
# ---------------------------------------------------------------------------


def test_no_training_document_shares_an_id_with_the_eval_corpus(built):
    docs, _ = built
    eval_ids = {split_front_matter(p.read_text()).meta["id"] for p in EVAL_CORPUS.glob("*.md")}
    assert not eval_ids & {d.doc_id for d in docs}


def test_no_training_question_appears_in_the_eval_set(built):
    _, items = built
    eval_qs = {_norm(i.question) for i in load_items()}
    assert not eval_qs & {_norm(i["question"]) for i in items}


def test_no_training_question_appears_in_the_fresh_slice(built):
    # E25: the held-out slice exists to test what training did not target.
    _, items = built
    slice_qs = {_norm(i.question) for i in load_items(REPO / "data" / "eval" / "eval_slice_j.jsonl")}
    assert len(slice_qs) == 100
    assert not slice_qs & {_norm(i["question"]) for i in items}


def test_no_training_document_copies_eval_text(built):
    docs, _ = built
    eval_grams = set().union(*(_ngrams(split_front_matter(p.read_text()).body) for p in EVAL_CORPUS.glob("*.md")))
    for d in docs:
        shared = _ngrams("\n".join(t for _, t in d.sections)) & eval_grams
        assert not shared, f"{d.doc_id} shares eval text: {' '.join(next(iter(shared)))}"


def test_eval_names_never_appear_in_training_documents(built):
    docs, _ = built
    for name in ("Al Noor", "ArcticLine", "FR-440", "Metro Utilities", "HomeGuard", "Vertex",
                 "Nova Mobile", "PHY-104", "برج النور"):
        assert not any(name in d.markdown() for d in docs), name


# ---------------------------------------------------------------------------
# the corpus itself
# ---------------------------------------------------------------------------


def test_build_is_deterministic():
    a, b = corpus.build(seed=7), corpus.build(seed=7)
    assert [d.markdown() for d in a[0]] == [d.markdown() for d in b[0]]
    assert a[1] == b[1]


def test_every_expected_fact_is_in_its_document(built):
    docs, items = built
    text = {d.doc_id: " ".join(d.markdown().lower().replace(",", "").split()) for d in docs}
    for i in items:
        if i["kind"] != "answerable":
            continue
        body = text[i["expect_doc"]]
        assert any(" ".join(e.lower().replace(",", "").split()) in body for e in i["expect_any"]), i


def test_unanswerable_items_explain_themselves(built):
    _, items = built
    assert all(i.get("note") for i in items if i["kind"] == "unanswerable")


def test_no_two_documents_share_a_key_within_a_family(built):
    docs, _ = built
    live = [d for d in docs if d.status != "superseded"]
    keys = [(d.doc_id.rsplit("-", 1)[0], d.key) for d in live]
    assert len(keys) == len(set(keys))


def test_split_is_by_document_and_old_versions_follow_their_live_one(built):
    docs, items = built
    split = {d.doc_id: d.split for d in docs}
    for d in docs:
        if d.doc_id.endswith("-old"):
            assert d.status == "superseded"
            assert d.split == split[d.doc_id.removesuffix("-old")]
    for i in items:
        if i.get("expect_doc"):
            assert i["split"] == split[i["expect_doc"]]
    assert {"train", "valid"} == set(split.values())


def test_a_household_holds_one_document_per_kind_in_one_language(built):
    """Two tenancy contracts in one index would make rent questions unanswerable."""
    docs, items = built
    homes: dict[int, list] = {}
    for d in docs:
        if d.status != "superseded":
            homes.setdefault(d.household, []).append(d)
    for h, ds in homes.items():
        kinds = [re.sub(r"-ar$", "", d.doc_id.rsplit("-", 1)[0]) for d in ds]
        assert len(kinds) == len(set(kinds)), (h, kinds)
        assert len({d.lang for d in ds}) == 1, h
    home = {d.doc_id: d.household for d in docs}
    assert all(i["household"] == home[i["expect_doc"]] for i in items if i.get("expect_doc"))


def test_training_questions_stay_in_scope(built):
    """Out-of-scope routing is code; an accidental route would waste the item."""
    _, items = built
    cov = Covenant()
    routed = [i["question"] for i in items if not cov.check(i["question"]).allowed]
    assert not routed, routed[:5]


def test_items_load_with_the_eval_item_schema(built):
    _, items = built
    for row in items[:50]:
        assert Item.from_json(row).question == row["question"]


# ---------------------------------------------------------------------------
# export formats
# ---------------------------------------------------------------------------


def _passage(doc_id: str, text: str) -> Retrieved:
    return Retrieved(chunk=Chunk(chunk_id=f"{doc_id}#001", doc_id=doc_id, ordinal=1, text=text),
                     score=1.0, coverage=1.0)


def _record(id_: str, split: str, passed: bool, calls: list[dict], **kw) -> dict:
    return {"id": id_, "split": split, "kind": kw.pop("kind", "answerable"), "lang": kw.pop("lang", "en"),
            "passed": passed, "why": "", "outcome": "answered", "calls": calls, **kw}


def test_recording_provider_keeps_the_exact_exchange():
    rec = RecordingProvider(EchoProvider())
    prompt, _ = answer_prompt("What is the rent?", [_passage("d", "The rent is AED 5,000.")])
    out = rec.complete(prompt, system=ANSWER_SYSTEM)
    assert rec.calls == [{"system": ANSWER_SYSTEM, "prompt": prompt, "response": out}]


def test_sft_export_keeps_only_passed_and_uses_the_real_prompt():
    prompt, _ = answer_prompt("What is the rent?", [_passage("d", "The rent is AED 5,000.")])
    good = {"system": ANSWER_SYSTEM, "prompt": prompt, "response": "The rent is AED 5,000 [S1].", "role": "answer"}
    bad = dict(good, response="The rent is AED 9,000 [S1].")
    sets = sft_examples([_record("a", "train", True, [good]), _record("b", "train", False, [bad])])
    assert len(sets["train"]) == 1
    msgs = sets["train"][0]["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
    assert msgs[0]["content"] == ANSWER_SYSTEM and msgs[1]["content"] == prompt
    assert "<question>What is the rent?</question>" in msgs[1]["content"]
    assert msgs[2]["content"] == "The rent is AED 5,000 [S1]."  # one passage: nothing to shuffle


def test_gate_refusals_are_capped():
    answers = [_record(f"a{i}", "train", True, [{"system": ANSWER_SYSTEM, "prompt": f"p{i}",
                                                   "response": f"x [S1]. {i}", "role": "answer"}])
               for i in range(10)]
    gates = [_record(f"u{i}", "train", True, [], kind="unanswerable", gate_prompt=f"g{i}") for i in range(50)]
    rows = sft_examples(answers + gates)["train"]
    refusals = sum(r["messages"][-1]["content"] == "NO_EVIDENCE" for r in rows)
    assert refusals / len(rows) <= 0.35 + 1e-9
    assert refusals > 0


def test_dpo_pairs_share_a_prompt_and_weight_hallucinations_and_arabic():
    teacher = teacher_replies([
        _record("a", "train", True, [{"prompt": "P", "response": "good [S1].", "role": "answer", "system": ANSWER_SYSTEM}]),
        _record("u", "train", True, [], kind="unanswerable", gate_prompt="G"),
    ])
    assert teacher["a"] == ({"P": "good [S1]."}, None)
    assert teacher["u"] == ({"G": "NO_EVIDENCE"}, "G")

    student = [
        {"id": "a", "split": "train", "kind": "answerable", "lang": "en",
         "pairs": [{"prompt": "P", "chosen": "good [S1].", "rejected": "bad [S1]."}] * 2},
        {"id": "u", "split": "train", "kind": "unanswerable", "lang": "ar",
         "pairs": [{"prompt": "G", "chosen": "NO_EVIDENCE", "rejected": "made up [S1]."}]},
    ]
    rows = dpo_rows(student)["train"]
    assert sum(r["prompt"] == "P" for r in rows) == 1  # duplicate samples collapse
    assert sum(r["prompt"] == "G" for r in rows) == 3  # 1 + unanswerable + arabic
    assert all(set(r) == {"system", "prompt", "chosen", "rejected"} for r in rows)


def test_grader_accepts_a_correct_cited_answer_on_a_training_item(built):
    docs, items = built
    item_row = next(i for i in items if i["kind"] == "answerable")
    doc = next(d for d in docs if d.doc_id == item_row["expect_doc"])
    from amin.schema import Claim, Verdict

    chunk = Chunk(chunk_id=f"{doc.doc_id}#001", doc_id=doc.doc_id, ordinal=1, text=doc.markdown())
    ans = Answer(question=item_row["question"], outcome=Outcome.ANSWERED,
                 claims=[Claim(text=f"It is {item_row['expect_any'][0]}.", cited_chunk_ids=[chunk.chunk_id],
                               verdict=Verdict.SUPPORTED)],
                 retrieved=[Retrieved(chunk=chunk, score=1.0, coverage=1.0)])
    assert grade(Item.from_json(item_row), ans).passed


def test_written_files_round_trip(tmp_path):
    n_docs, n_items = corpus.write(tmp_path, seed=7)
    assert len(list((tmp_path / "corpus").glob("h*/*.md"))) == n_docs
    rows = [json.loads(x) for x in (tmp_path / "items.jsonl").read_text().splitlines()]
    assert len(rows) == n_items


def test_shuffled_passages_keep_every_tag_pointing_at_the_same_text():
    import random as _r

    passages = [_passage(f"d{i}", f"Fact number {i} is {i * 11}.") for i in range(1, 7)]
    prompt, _ = answer_prompt("What is fact 2 and fact 5?", passages)
    ex = {"messages": [{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": prompt},
                       {"role": "assistant", "content": "Fact 2 is 22 [S2]. Fact 5 is 55 [S5]."}]}
    moved = 0
    for seed in range(20):
        out = _shuffle_passages(ex, _r.Random(seed))
        p, reply = out["messages"][1]["content"], out["messages"][2]["content"]
        assert p.count("[S") == 6 and "<question>What is fact 2 and fact 5?</question>" in p
        for sentence, n in re.findall(r"(Fact \d is \d+) \[S(\d)\]", reply):
            block = re.search(rf"\[S{n}\] [^\n]*\n([^\n]*)", p).group(1)
            assert block.split(" is ")[1].rstrip(".") == sentence.split(" is ")[1]
        moved += reply != ex["messages"][2]["content"]
    assert moved > 10


def test_shuffle_leaves_refusals_and_bad_tags_alone():
    import random as _r

    prompt, _ = answer_prompt("q", [_passage("a", "x"), _passage("b", "y")])
    bad = {"messages": [{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": prompt},
                        {"role": "assistant", "content": "z [S7]."}]}
    assert _shuffle_passages(bad, _r.Random(0)) == bad
    ref = dict(bad, messages=bad["messages"][:2] + [{"role": "assistant", "content": "NO_EVIDENCE"}])
    out = _shuffle_passages(ref, _r.Random(1))
    assert out["messages"][2]["content"] == "NO_EVIDENCE"


def test_dpo_balance_adds_one_answer_pair_per_refusal_pair():
    student = [{"id": "u", "split": "train", "kind": "unanswerable", "lang": "en",
                "pairs": [{"prompt": "G", "chosen": "NO_EVIDENCE", "rejected": "made up [S1]."}]}]
    teacher = [_record(f"s{i}", "train", True, [{"prompt": f"P{i}", "response": f"fact {i} [S1].",
                                                  "role": "answer", "system": ANSWER_SYSTEM}]) for i in range(5)]
    rows = dpo_rows(student, balance=teacher)["train"]
    refuse = [r for r in rows if r["chosen"] == "NO_EVIDENCE"]
    answer = [r for r in rows if r["rejected"] == "NO_EVIDENCE"]
    assert len(refuse) == 2 and len(answer) == 2  # unanswerable weighted x2, matched one for one
    assert all(r["chosen"].endswith("[S1].") for r in answer)


def test_dpo_balance_ratio_three():
    student = [{"id": "u", "split": "train", "kind": "unanswerable", "lang": "en",
                "pairs": [{"prompt": "G", "chosen": "NO_EVIDENCE", "rejected": "made up [S1]."}]}]
    teacher = [_record("s", "train", True, [{"prompt": "P", "response": "fact [S1].", "role": "answer",
                                              "system": ANSWER_SYSTEM}])]
    rows = dpo_rows(student, balance=teacher, ratio=3.0)["train"]
    assert sum(r["chosen"] == "NO_EVIDENCE" for r in rows) == 2
    assert sum(r["rejected"] == "NO_EVIDENCE" for r in rows) == 6


def test_general_bank_stays_clear_of_the_main_eval_set():
    from amin.config import settings
    from amin.train.general import bank, overlaps

    hits = overlaps(bank(), [settings.eval_set])
    # The run drops these; this pins how many the bank collides with today.
    assert len(hits) <= 6, hits


def test_malayalam_households_are_appended_without_moving_anything():
    from amin.train.corpus import ML_FAMILIES, build, inr

    docs, items = build()
    ml = [d for d in docs if d.lang == "ml"]
    assert len(ml) == sum(c for _, c in ML_FAMILIES)
    assert docs[-len(ml):] == ml, "Malayalam documents come after every earlier one"
    assert all(i["id"].startswith("t4-") for i in items if i["lang"] == "ml")
    assert min(d.household for d in ml) > max(d.household for d in docs if d.lang != "ml")
    assert inr(125000) == "1,25,000" and inr(8500) == "8,500" and inr(12345678) == "1,23,45,678"


def test_grader_folds_malayalam_spellings():
    from amin.evaluate import _normalise

    # atomic chillu (ൻ) and the older ZWJ spelling are the same letter
    assert _normalise("1,25,000 രൂപ അവൻ") == _normalise("125000 രൂപ അവന്‍")
