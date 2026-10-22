"""Tests for the statistics, the three systems, and the benchmark runner.

The statistics are the part most worth testing: if `wilson` or `mcnemar` is
wrong, the project reports confident conclusions from noise, which is exactly
the failure the whole repo is supposed to be about.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amin.benchmark import compare_runs, run_benchmark, stratified_sample, to_markdown
from amin.evaluate import load_items
from amin.ingest import ingest
from amin.prompts import looks_like_refusal as _looks_like_refusal
from amin.providers import EchoProvider, HashEmbedder
from amin.stats import bootstrap_delta, mcnemar, required_n, wilson
from amin.store import Store
from amin.systems import BareSystem, NaiveRagSystem, build_system

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "data" / "corpus"


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> Store:
    s = Store(tmp_path_factory.mktemp("bench-index") / "t.db")
    docs, chunks = ingest(CORPUS)
    s.upsert(docs, chunks, HashEmbedder()([c.text for c in chunks]))
    return s


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------


def test_wilson_stays_inside_zero_and_one_at_the_extremes():
    """The normal approximation returns negative bounds here. Wilson must not."""
    for successes, n in [(0, 10), (10, 10), (0, 1), (1, 1)]:
        iv = wilson(successes, n)
        assert 0.0 <= iv.low <= iv.point <= iv.high <= 1.0, (successes, n, iv)


def test_wilson_interval_narrows_as_n_grows():
    widths = [wilson(n // 2, n).half_width for n in (10, 50, 200, 1000)]
    assert widths == sorted(widths, reverse=True)
    assert widths[-1] < 0.05


def test_wilson_on_an_empty_slice_is_maximally_uncertain():
    iv = wilson(0, 0)
    assert iv.n == 0 and iv.low == 0.0 and iv.high == 1.0


def test_required_n_matches_the_textbook_values():
    assert required_n(0.10) == 97
    assert required_n(0.05) == 385


def test_mcnemar_ignores_items_both_systems_got_right():
    """Adding items both systems pass must not manufacture significance."""
    a = [True] * 3 + [False] * 7
    b = [False] * 10
    small = mcnemar(a, b)
    padded = mcnemar(a + [True] * 100, b + [True] * 100)
    assert small.p_value == padded.p_value
    assert small.n_discordant == padded.n_discordant == 3


def test_mcnemar_calls_a_three_item_lead_insignificant():
    """3-0 is p=0.25. Reporting it as a win is the error this project is about."""
    test = mcnemar([True] * 3 + [False] * 7, [False] * 10)
    assert not test.significant
    assert "not significant" in test.verdict("A", "B")


def test_mcnemar_calls_a_ten_item_lead_significant():
    test = mcnemar([True] * 10 + [False] * 5, [False] * 15)
    assert test.significant and test.p_value < 0.01


def test_mcnemar_is_symmetric_in_its_p_value():
    a, b = [True] * 6 + [False] * 4, [False] * 6 + [True] * 4
    assert mcnemar(a, b).p_value == pytest.approx(mcnemar(b, a).p_value)


def test_mcnemar_on_identical_systems_is_not_significant():
    test = mcnemar([True, False] * 10, [True, False] * 10)
    assert test.n_discordant == 0 and test.p_value == 1.0
    assert "identical" in test.verdict()


def test_mcnemar_rejects_unpaired_inputs():
    with pytest.raises(ValueError, match="equal lengths"):
        mcnemar([True, False], [True])


def test_bootstrap_delta_straddles_zero_for_a_tiny_difference():
    """Items must disagree in both directions for the interval to cross zero.

    a and b each win on one item and tie on the rest, so the true delta is zero
    and the interval must admit that.
    """
    a = [True, False] + [True] * 9 + [False] * 9
    b = [False, True] + [True] * 9 + [False] * 9
    iv = bootstrap_delta(a, b, iterations=4000, seed=7)
    assert iv.low < 0 < iv.high, f"a tied result must not look conclusive: {iv}"


def test_bootstrap_delta_does_not_cross_zero_when_one_system_is_never_worse():
    """A correct property of the *paired* bootstrap, not a bug.

    If a succeeds on every item b succeeds on, plus one more, no resample of the
    pairs can make b look better. An unpaired test would wrongly show overlap
    here; preserving the pairing is the whole reason this is a paired bootstrap.
    """
    a = [True] * 11 + [False] * 9
    b = [True] * 10 + [False] * 10
    iv = bootstrap_delta(a, b, iterations=3000, seed=7)
    assert iv.low >= 0 and iv.point > 0


def test_bootstrap_delta_is_deterministic_for_a_fixed_seed():
    a, b = [True] * 12 + [False] * 8, [True] * 4 + [False] * 16
    first = bootstrap_delta(a, b, iterations=2000, seed=3)
    second = bootstrap_delta(a, b, iterations=2000, seed=3)
    assert (first.low, first.high) == (second.low, second.high)


# ---------------------------------------------------------------------------
# refusal detection — applied identically to every system
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "I don't know.",
        "NO_EVIDENCE",
        "The context does not contain that information.",
        "That is not specified in the documents.",
        "لا توجد معلومات في المستند",
    ],
)
def test_verbal_refusals_are_detected(text):
    assert _looks_like_refusal(text)


@pytest.mark.parametrize(
    "text",
    ["The warranty is 24 months.", "AED 3,900.", "الضمان 24 شهرا"],
)
def test_assertions_are_not_mistaken_for_refusals(text):
    assert not _looks_like_refusal(text)


# ---------------------------------------------------------------------------
# systems
# ---------------------------------------------------------------------------


def test_bare_system_does_not_retrieve(store):
    system = BareSystem(provider=EchoProvider())
    answer = system.answer("What is the part number for the fridge water filter?")
    assert answer.retrieved == [], "the bare baseline must not touch the index"
    assert system.cites is False


def test_naive_system_retrieves_but_never_cites(store):
    system = NaiveRagSystem(store=store, provider=EchoProvider())
    answer = system.answer("What is the part number for the fridge water filter cartridge?")
    assert answer.retrieved, "naive RAG must retrieve"
    assert answer.sources() == [], "naive RAG has no citations to resolve"
    assert system.cites is False


def test_naive_system_has_no_scope_routing(store):
    """The baseline answers a medical question; that is the gap Amin closes."""
    system = NaiveRagSystem(store=store, provider=EchoProvider())
    answer = system.answer("Should I take ibuprofen for this headache?")
    assert answer.routed_to == ""


def test_amin_system_cites_and_routes(store):
    system = build_system("amin", store=store, provider=EchoProvider(), verifier_mode="lexical")
    assert system.cites is True
    routed = system.answer("Can I sue the landlord for not repairing the AC?")
    assert routed.routed_to == "legal"


def test_unknown_system_name_is_rejected(store):
    with pytest.raises(ValueError, match="unknown system"):
        build_system("gpt9", store=store, provider=EchoProvider())


# ---------------------------------------------------------------------------
# sampling
# ---------------------------------------------------------------------------


def test_stratified_sample_keeps_every_kind():
    """items[:n] on an ordered set silently deletes the hallucination metric."""
    items = load_items()
    naive_head = items[:30]
    assert len({i.kind for i in naive_head}) == 1, "precondition: the set is ordered by kind"

    sample = stratified_sample(items, 30)
    assert {"answerable", "unanswerable", "out_of_scope"} <= {i.kind for i in sample}
    assert 25 <= len(sample) <= 45


def test_stratified_sample_is_a_noop_when_n_exceeds_the_set():
    items = load_items()
    assert stratified_sample(items, 10_000) is items
    assert stratified_sample(items, 0) is items


# ---------------------------------------------------------------------------
# the benchmark end to end
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bench(store):
    return run_benchmark(
        ["bare", "naive", "amin"],
        items=stratified_sample(load_items(), 40),
        provider="echo",
        verifier_mode="lexical",
        store=store,
    )


def test_benchmark_runs_every_system_on_identical_items(bench):
    assert len(bench.runs) == 3
    for run in bench.runs:
        assert not run.error, run.error
        assert len(run.results) == len(bench.items)


def test_only_amin_produces_citations(bench):
    by_name = {r.system: r for r in bench.runs}
    assert by_name["amin"].metrics["citation_precision"] > 0
    assert by_name["bare"].metrics["citation_precision"] == 0
    assert by_name["naive"].metrics["citation_precision"] == 0


def test_naive_rag_hallucinates_more_than_amin(bench):
    """The ablation's central claim. If this inverts, the pipeline is not earning its keep."""
    by_name = {r.system: r for r in bench.runs}
    assert by_name["naive"].metrics["hallucination_rate"] > by_name["amin"].metrics[
        "hallucination_rate"
    ]


def test_paired_tests_are_run_per_slice_not_across_the_whole_set(bench):
    metrics_tested = {c.metric for c in bench.comparisons}
    assert metrics_tested == {"fact_accuracy", "correct_refusal"}
    # Three systems -> three pairs -> two tests each.
    assert len(bench.comparisons) == 6


def test_markdown_report_warns_about_sample_size_and_explains_the_zeros(bench):
    md = to_markdown(bench)
    assert "Sample size" in md
    assert "missing capability, not a defeat" in md
    assert "| metric |" in md


def test_comparisons_are_skipped_for_runs_of_unequal_length(bench):
    truncated = bench.runs[0]
    import copy

    short = copy.copy(truncated)
    short.results = truncated.results[:5]
    short.system = "short"
    assert all(c.a != "short" and c.b != "short" for c in compare_runs([*bench.runs, short]))


def test_amin_treats_paraphrased_abstention_as_refusal():
    """E19 u076: the model wrote 'the passages do not contain…' instead of
    NO_EVIDENCE, and it was scored and shown as an answer."""
    assert _looks_like_refusal("The provided passages do not contain information on that.")
    assert _looks_like_refusal("The context does not specify a fee for that.")
    assert not _looks_like_refusal("The deposit is AED 5,000 [S1].")
