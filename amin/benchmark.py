"""Multi-system benchmark.

Runs the same eval set through several systems and reports the comparison with
confidence intervals and paired significance tests. The design rule: anything
that could flatter one system has to apply to all of them - same retriever,
same model, same items, same grader, same refusal detector.

What the output is for: answering "does the pipeline earn its complexity?" with
a number and a p-value instead of an opinion.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import settings
from .evaluate import Item, Result, grade, load_items, metrics, trust_score
from .stats import Interval, McNemar, bootstrap_delta, mcnemar, required_n
from .systems import build_system


@dataclass
class Run:
    """One system's pass over the eval set."""

    system: str
    provider: str
    model: str
    results: list[Result]
    metrics: dict
    wall_seconds: float
    error: str = ""

    def passes(self) -> list[bool]:
        return [r.passed for r in self.results]

    def facts(self) -> list[bool]:
        return [r.fact_ok for r in self.results]

    def slice_flags(self, kind: str, attr: str = "fact_ok") -> list[bool]:
        """Per-item outcomes for one item kind only.

        Paired tests must compare like with like. `fact_ok` means "the expected
        fact appeared" on an answerable item and "refused correctly" on an
        unanswerable one, so testing across the whole set mixes two different
        questions and the p-value means nothing. Slicing first is not optional.
        """
        return [getattr(r, attr) for r in self.results if r.item.kind == kind]

    def label(self) -> str:
        return f"{self.system} ({self.model})"


@dataclass
class Comparison:
    a: str
    b: str
    metric: str
    test: McNemar
    delta: Interval


@dataclass
class Benchmark:
    runs: list[Run] = field(default_factory=list)
    comparisons: list[Comparison] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)

    def best_by_trust(self) -> Run | None:
        live = [r for r in self.runs if not r.error]
        return max(live, key=lambda r: trust_score(r.metrics)) if live else None


# ---------------------------------------------------------------------------


def stratified_sample(items: list[Item], n: int, seed: int = 0) -> list[Item]:
    """Take n items while preserving the kind proportions.

    A head slice of an ordered eval set is not a sample: `items[:30]` on this
    set returns 30 answerable items and zero unanswerable ones, which silently
    removes the hallucination metric entirely. Sampling has to be stratified or
    it changes what is being measured.
    """
    if n <= 0 or n >= len(items):
        return items
    import random

    rng = random.Random(seed)
    by_kind: dict[str, list[Item]] = {}
    for item in items:
        by_kind.setdefault(item.kind, []).append(item)

    picked: list[Item] = []
    for group in by_kind.values():
        share = max(1, round(n * len(group) / len(items)))
        picked.extend(rng.sample(group, min(share, len(group))))
    order = {item.id: i for i, item in enumerate(items)}
    return sorted(picked, key=lambda x: order[x.id])


def run_benchmark(
    systems: list[str],
    items: list[Item] | None = None,
    provider: str | None = None,
    verifier_mode: str | None = None,
    store=None,
    on_progress=None,
) -> Benchmark:
    from .providers import get_provider
    from .store import Store

    items = items if items is not None else load_items()
    store = store if store is not None else Store()
    # Resolve the provider once and hand the same object to every system, so a
    # comparison can never accidentally run two systems on different models.
    prov = get_provider(provider)
    bench = Benchmark(items=items)

    for kind in systems:
        started = time.perf_counter()
        try:
            system = build_system(kind, store=store, provider=prov, verifier_mode=verifier_mode)
        except Exception as exc:
            bench.runs.append(
                Run(
                    system=kind,
                    provider=prov.name,
                    model=settings.answer_model,
                    results=[],
                    metrics=metrics([]),
                    wall_seconds=0.0,
                    error=f"could not build: {type(exc).__name__}: {exc}",
                )
            )
            continue

        cites = getattr(system, "cites", True)
        results: list[Result] = []
        error = ""
        for i, item in enumerate(items, start=1):
            try:
                answer = system.answer(item.question)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                break
            results.append(grade(item, answer, cites=cites))
            if on_progress:
                on_progress(kind, i, len(items))

        bench.runs.append(
            Run(
                system=kind,
                provider=prov.name,
                model=settings.answer_model,
                results=results,
                metrics=metrics(results),
                wall_seconds=time.perf_counter() - started,
                error=error,
            )
        )

    bench.comparisons = compare_runs(bench.runs)
    return bench


def compare_runs(runs: list[Run]) -> list[Comparison]:
    """Pairwise paired tests, run separately on each item slice.

    Two comparisons per pair, because they answer different questions:

      fact_accuracy    on answerable items only — can it find the fact?
      correct_refusal  on unanswerable items only — does it know when to stop?

    A system can win decisively on one and lose decisively on the other; naive
    RAG does exactly that, which is the finding the ablation exists to surface.
    Testing `passed` across the whole set would average those two opposite
    results into a single meaningless number.
    """
    live = [r for r in runs if r.results and not r.error]
    out: list[Comparison] = []
    slices = [("fact_accuracy", "answerable", "fact_ok"), ("correct_refusal", "unanswerable", "passed")]
    for i, a in enumerate(live):
        for b in live[i + 1 :]:
            if len(a.results) != len(b.results):
                continue
            for metric, kind, attr in slices:
                av, bv = a.slice_flags(kind, attr), b.slice_flags(kind, attr)
                if not av or len(av) != len(bv):
                    continue
                out.append(
                    Comparison(
                        a=a.system,
                        b=b.system,
                        metric=metric,
                        test=mcnemar(av, bv),
                        delta=bootstrap_delta(av, bv),
                    )
                )
    return out


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

METRIC_ROWS = [
    ("fact_accuracy", "fact accuracy", "higher", True),
    ("grounded_accuracy", "grounded accuracy", "higher", True),
    ("correct_refusal", "correct refusal", "higher", True),
    ("hallucination_rate", "hallucination rate", "LOWER", True),
    ("citation_precision", "citation precision", "higher", False),
    ("routing_accuracy", "routing accuracy", "higher", True),
    ("arabic_pass", "arabic pass", "higher", False),
]


def to_markdown(bench: Benchmark) -> str:
    live = [r for r in bench.runs if r.results and not r.error]
    counts = live[0].metrics["counts"] if live else {}
    lines: list[str] = []
    ap = "\n".join

    lines.append("# Benchmark")
    lines.append("")
    lines.append(
        f"{len(bench.items)} items "
        f"({counts.get('answerable', 0)} answerable / "
        f"{counts.get('unanswerable', 0)} unanswerable / "
        f"{counts.get('out_of_scope', 0)} out-of-scope), "
        f"provider `{settings.provider}`, model `{settings.answer_model}`, "
        f"run {time.strftime('%Y-%m-%d %H:%M')}."
    )
    lines.append("")

    # -- sample size warning, first, before any number is read -------------
    n_ans = counts.get("answerable", 0)
    n_un = counts.get("unanswerable", 0)
    need10 = required_n(0.10)
    if n_ans < need10 or n_un < need10:
        lines.append(
            f"> **Sample size.** {need10} items per slice are needed for a 95% interval of "
            f"±10 points at the worst case. This set has {n_ans} answerable and {n_un} "
            f"unanswerable. Treat every interval below as the real precision of the claim, "
            f"and do not report a difference whose interval straddles zero."
        )
        lines.append("")

    # -- main table ---------------------------------------------------------
    header = "| metric | " + " | ".join(r.system for r in live) + " | direction |"
    sep = "|---|" + "---|" * (len(live) + 1)
    lines += [header, sep]
    for key, label, direction, _ in METRIC_ROWS:
        cells = []
        for r in live:
            point = r.metrics.get(key, 0.0)
            ci = r.metrics.get("ci", {}).get(key)
            cells.append(
                f"{point:.1%} ±{(ci['high'] - ci['low']) / 2:.0%}" if ci else f"{point:.1%}"
            )
        lines.append(f"| {label} | " + " | ".join(cells) + f" | {direction} |")

    lines.append(
        "| trust score | "
        + " | ".join(f"{trust_score(r.metrics):+.3f}" for r in live)
        + " | higher |"
    )
    lines.append(
        "| p50 latency | "
        + " | ".join(f"{r.metrics['p50_latency_ms']} ms" for r in live)
        + " | lower |"
    )
    lines.append(
        "| wall clock | " + " | ".join(f"{r.wall_seconds:.1f} s" for r in live) + " | lower |"
    )
    lines.append("")
    lines.append(
        "`grounded accuracy` and `citation precision` require a system that cites, so a "
        "`bare` or `naive` column of 0% there is a missing capability, not a defeat. "
        "Cross-system claims are made on `fact accuracy` and `hallucination rate`."
    )
    lines.append("")

    # -- paired tests -------------------------------------------------------
    if bench.comparisons:
        lines.append("## Paired tests (McNemar on identical items, per slice)")
        lines.append("")
        lines.append("| comparison | metric | A only | B only | delta (95% CI) | p | verdict |")
        lines.append("|---|---|---|---|---|---|---|")
        for c in bench.comparisons:
            straddles = c.delta.low < 0 < c.delta.high
            verdict = "inconclusive" if straddles or not c.test.significant else "significant"
            lines.append(
                f"| {c.a} vs {c.b} | {c.metric} | {c.test.b} | {c.test.c} | "
                f"{c.delta.point:+.1%} [{c.delta.low:+.1%}, {c.delta.high:+.1%}] | "
                f"{c.test.p_value:.3f} | {verdict} |"
            )
        lines.append("")
        lines.append(
            "*A only* / *B only* are the items where exactly one system succeeded; items both "
            "got right or both got wrong carry no information about which is better and are "
            "excluded by the test."
        )
        lines.append("")

    # -- failures and errors ------------------------------------------------
    for r in bench.runs:
        if r.error:
            lines.append(f"**{r.system} did not complete:** `{r.error}`")
            lines.append("")

    best = bench.best_by_trust()
    if best:
        lines.append(
            f"Best trust score: **{best.system}** at {trust_score(best.metrics):+.3f} "
            f"(grounded {best.metrics['grounded_accuracy']:.1%}, "
            f"hallucination {best.metrics['hallucination_rate']:.1%})."
        )
    return ap(lines) + "\n"


def write_benchmark(bench: Benchmark, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")

    json_path = out_dir / f"bench-{stamp}.json"
    json_path.write_text(
        json.dumps(
            {
                "timestamp": stamp,
                "config": {
                    "provider": settings.provider,
                    "answer_model": settings.answer_model,
                    "verifier": settings.verifier,
                    "evidence_floor": settings.evidence_floor,
                    "top_k_final": settings.top_k_final,
                },
                "n_items": len(bench.items),
                "runs": [
                    {
                        "system": r.system,
                        "model": r.model,
                        "metrics": r.metrics,
                        "wall_seconds": r.wall_seconds,
                        "error": r.error,
                        "results": [x.row() for x in r.results],
                    }
                    for r in bench.runs
                ],
                "comparisons": [
                    {
                        "a": c.a,
                        "b": c.b,
                        "metric": c.metric,
                        "a_only": c.test.b,
                        "b_only": c.test.c,
                        "p_value": c.test.p_value,
                        "delta": c.delta.point,
                        "delta_low": c.delta.low,
                        "delta_high": c.delta.high,
                        "significant": c.test.significant and not (c.delta.low < 0 < c.delta.high),
                    }
                    for c in bench.comparisons
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md_path = out_dir / f"bench-{stamp}.md"
    md_path.write_text(to_markdown(bench), encoding="utf-8")
    return json_path, md_path
