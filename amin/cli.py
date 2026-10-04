"""Command line interface.

    amin ingest                build the index from data/corpus (and private/)
    amin ask "question"        one grounded answer with sources
    amin eval                  run the eval set and print the metrics table
    amin stats                 what is in the index
    amin serve                 start the HTTP API
    amin doctor                check the local model server is reachable
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .config import settings
from .schema import Outcome, Verdict

app = typer.Typer(add_completion=False, help="Amin — a local assistant that cites its sources.")
console = Console()


def _amin(provider: str | None = None):
    from .answer import Amin
    from .providers import get_provider

    return Amin(provider=get_provider(provider) if provider else None)


# ---------------------------------------------------------------------------


@app.command()
def ingest(
    path: Path = typer.Argument(None, help="Folder or file to ingest. Defaults to data/corpus."),
    include_private: bool = typer.Option(False, "--private", help="Also ingest ./private."),
    reset: bool = typer.Option(False, "--reset", help="Wipe the index first."),
    provider: str = typer.Option(None, help="ollama | mlx | echo (for embeddings)."),
):
    """Load documents, chunk them, embed them, index them."""
    from .ingest import ingest as run_ingest
    from .providers import get_provider
    from .store import Store

    roots = [path or settings.corpus_path]
    if include_private and settings.private_path.exists():
        roots.append(settings.private_path)

    store = Store()
    if reset:
        store.reset()
        console.print("[dim]index reset[/dim]")

    prov = get_provider(provider)
    total_docs = total_chunks = 0
    for root in roots:
        if not root.exists():
            console.print(f"[yellow]skipped missing path {root}[/yellow]")
            continue
        docs, chunks = run_ingest(root)
        if not chunks:
            console.print(f"[yellow]no ingestible documents in {root}[/yellow]")
            continue
        with console.status(f"embedding {len(chunks)} chunks from {root.name}…"):
            vectors = prov.embed([c.text for c in chunks])
        store.upsert(docs, chunks, vectors)
        total_docs += len(docs)
        total_chunks += len(chunks)
        console.print(f"[green]+[/green] {root}: {len(docs)} docs, {len(chunks)} chunks")

    console.print(
        Panel(
            f"{total_docs} documents, {total_chunks} chunks indexed\n"
            f"embeddings via [bold]{prov.name}[/bold] → {settings.index_path}",
            title="ingest complete",
            border_style="green",
        )
    )


@app.command()
def ask(
    question: str = typer.Argument(..., help="The question."),
    provider: str = typer.Option(None, help="ollama | mlx | echo."),
    show_retrieved: bool = typer.Option(False, "--retrieved", help="Show all retrieved passages."),
    debug: bool = typer.Option(False, "--debug", help="Show verifier notes per claim."),
):
    """Ask Amin one question."""
    answer = _amin(provider).ask(question)

    if answer.outcome == Outcome.REFUSED_OUT_OF_SCOPE:
        console.print(
            Panel(
                answer.refusal_reason,
                title=f"out of scope → {answer.routed_to}",
                border_style="yellow",
            )
        )
    elif answer.outcome == Outcome.REFUSED_NO_EVIDENCE:
        console.print(Panel(answer.refusal_reason, title="no evidence", border_style="yellow"))
    else:
        body = Text()
        for claim in answer.claims:
            if claim.verdict == Verdict.SUPPORTED:
                body.append(claim.text + " ")
                body.append(
                    "".join(f"[{c.split('#')[0]}]" for c in claim.cited_chunk_ids) + "\n",
                    style="bold cyan",
                )
            else:
                body.append(claim.text + " ", style="italic")
                body.append("(unverified reasoning)\n", style="dim yellow")
        title = "conflict between sources" if answer.outcome == Outcome.CONFLICT else "answer"
        console.print(
            Panel(
                body,
                title=title,
                border_style="red" if answer.outcome == Outcome.CONFLICT else "green",
            )
        )

        if sources := answer.sources():
            table = Table(title="sources", show_lines=False, title_justify="left")
            table.add_column("doc", style="cyan", no_wrap=True)
            table.add_column("section")
            table.add_column("tier", no_wrap=True)
            table.add_column("quoted passage", overflow="fold")
            for s in sources:
                table.add_row(s["doc_id"], s["heading"] or "—", s["tier"], s["text"][:260])
            console.print(table)

    if debug:
        for claim in answer.claims:
            console.print(f"[dim]{claim.verdict.value:12s} {claim.verifier_note}[/dim]")
    if show_retrieved:
        for r in answer.retrieved:
            console.print(
                f"[dim]{r.score:.5f} d={r.dense_rank} l={r.lexical_rank} "
                f"{r.chunk.doc_id} §{r.chunk.heading}[/dim]"
            )
    console.print(
        f"[dim]{answer.outcome.value} · {answer.latency_ms} ms · {answer.model} · "
        f"citation precision {answer.citation_precision:.0%}[/dim]"
    )


@app.command("eval")
def eval_cmd(
    provider: str = typer.Option(None, help="ollama | mlx | echo."),
    eval_set: Path = typer.Option(None, help="Path to a .jsonl eval set."),
    save: bool = typer.Option(True, help="Write a JSON report into ./reports."),
    failures_only: bool = typer.Option(False, "--failures", help="Only print failing items."),
    system: str = typer.Option("amin", help="amin | naive | bare — which system to evaluate."),
):
    """Run the eval set and print the metrics that matter."""
    from .evaluate import load_items, metrics, run, write_report
    from .stats import required_n
    from .systems import build_system

    items = load_items(eval_set)
    sysobj = build_system(system, provider=_provider_or_none(provider))

    rows = []
    with console.status(f"running {len(items)} eval items through {system}…") as status:
        def on_result(result):
            rows.append(result)
            status.update(f"[{len(rows)}/{len(items)}] {result.item.id}")

        results, _ = run(system=sysobj, items=items, on_result=on_result)
    stats = metrics(results)

    detail = Table(title="eval detail", title_justify="left")
    detail.add_column("id", no_wrap=True)
    detail.add_column("kind", no_wrap=True)
    detail.add_column("", no_wrap=True)
    detail.add_column("why", overflow="fold")
    shown = 0
    for r in results:
        if failures_only and r.passed:
            continue
        if shown >= 40:
            break
        shown += 1
        detail.add_row(
            r.item.id,
            r.item.kind,
            "[green]pass[/green]" if r.passed else "[red]FAIL[/red]",
            r.why,
        )
    console.print(detail)
    if shown >= 40:
        console.print("[dim]…truncated. Full detail is in the JSON report.[/dim]")

    _print_metrics(stats, title=f"metrics — {system}")

    need = required_n(0.10)
    thin = [k for k, v in stats["counts"].items() if k != "arabic" and 0 < v < need]
    if thin:
        console.print(
            f"[yellow]Sample size: {', '.join(thin)} below {need} items, so those "
            f"intervals are wide. Read the ± column before claiming an improvement.[/yellow]"
        )

    if save:
        path = write_report(results, stats, Path("reports"), label=f"eval-{system}")
        console.print(f"[dim]report → {path}[/dim]")


def _provider_or_none(provider: str | None):
    from .providers import get_provider

    return get_provider(provider) if provider else None


def _print_metrics(stats: dict, title: str = "metrics") -> None:
    from .evaluate import trust_score

    table = Table(title=title, title_justify="left")
    table.add_column("metric", no_wrap=True)
    table.add_column("value", justify="right", no_wrap=True)
    table.add_column("95% CI", justify="right", no_wrap=True)
    table.add_column("direction", no_wrap=True, style="dim")
    rows = [
        ("fact_accuracy", "higher is better"),
        ("grounded_accuracy", "higher is better"),
        ("correct_refusal", "higher is better"),
        ("hallucination_rate", "LOWER is better"),
        ("citation_precision", "higher is better"),
        ("routing_accuracy", "higher is better"),
        ("overall_pass", "higher is better"),
        ("arabic_pass", "higher is better"),
    ]
    for key, direction in rows:
        ci = stats.get("ci", {}).get(key)
        ci_text = f"[{ci['low']:.1%}, {ci['high']:.1%}]" if ci else "—"
        table.add_row(key, f"{stats.get(key, 0.0):.1%}", ci_text, direction)
    table.add_row("trust_score", f"{trust_score(stats):+.3f}", "—", "higher is better")
    table.add_row("p50 / p95 latency", f"{stats['p50_latency_ms']} / {stats['p95_latency_ms']} ms", "—", "")
    table.add_row("items", str(stats["n"]), "—", str(stats["counts"]))
    console.print(table)


@app.command("bench")
def bench_cmd(
    systems: str = typer.Option("bare,naive,amin", help="Comma-separated: bare | naive | amin."),
    provider: str = typer.Option(None, help="ollama | mlx | echo."),
    eval_set: Path = typer.Option(None, help="Path to a .jsonl eval set."),
    verifier: str = typer.Option(None, help="llm | lexical | off (amin only)."),
    sample: int = typer.Option(0, help="Run only the first N items — for a quick smoke test."),
    save: bool = typer.Option(True, help="Write JSON + markdown into ./reports."),
):
    """Compare systems on one eval set, with confidence intervals and paired tests.

    The ablation that answers 'does the pipeline earn its complexity?':
    bare measures the model's priors, naive is a conventional RAG baseline,
    amin is the full pipeline. Same retriever, same model, same items.
    """
    from .benchmark import run_benchmark, stratified_sample, to_markdown, write_benchmark
    from .evaluate import load_items

    kinds = [s.strip() for s in systems.split(",") if s.strip()]
    items = load_items(eval_set)
    if sample > 0:
        items = stratified_sample(items, sample)
        console.print(
            f"[yellow]stratified sample of {len(items)} items — a smoke test, "
            f"not a publishable run[/yellow]"
        )

    total = len(items) * len(kinds)
    with console.status("benchmarking…") as status:
        done = {"n": 0}

        def on_progress(system: str, i: int, n: int):
            done["n"] += 1
            status.update(f"[{done['n']}/{total}] {system} {i}/{n}")

        bench = run_benchmark(
            kinds,
            items=items,
            provider=provider,
            verifier_mode=verifier,
            on_progress=on_progress,
        )

    live = [r for r in bench.runs if r.results and not r.error]
    if not live:
        console.print("[red]no system completed — check `amin doctor`[/red]")
        for r in bench.runs:
            if r.error:
                console.print(f"[red]{r.system}: {r.error}[/red]")
        raise typer.Exit(1)

    summary = Table(title="system comparison", title_justify="left")
    summary.add_column("metric", no_wrap=True)
    for r in live:
        summary.add_column(r.system, justify="right", no_wrap=True)
    summary.add_column("direction", no_wrap=True, style="dim")

    from .benchmark import METRIC_ROWS
    from .evaluate import trust_score

    for key, label, direction, _ in METRIC_ROWS:
        cells = []
        for r in live:
            ci = r.metrics.get("ci", {}).get(key)
            point = r.metrics.get(key, 0.0)
            cells.append(
                f"{point:.1%} ±{(ci['high'] - ci['low']) / 2:.0%}" if ci else f"{point:.1%}"
            )
        style = "red" if direction == "LOWER" else ""
        summary.add_row(label, *cells, f"[{style}]{direction}[/{style}]" if style else direction)
    summary.add_row("trust score", *[f"{trust_score(r.metrics):+.3f}" for r in live], "higher")
    summary.add_row("wall clock", *[f"{r.wall_seconds:.1f}s" for r in live], "lower")
    console.print(summary)

    if bench.comparisons:
        paired = Table(title="paired tests — McNemar, per slice", title_justify="left")
        paired.add_column("comparison", no_wrap=True)
        paired.add_column("metric", no_wrap=True)
        paired.add_column("A only", justify="right", no_wrap=True)
        paired.add_column("B only", justify="right", no_wrap=True)
        paired.add_column("delta (95% CI)", justify="right", no_wrap=True)
        paired.add_column("p", justify="right", no_wrap=True)
        paired.add_column("verdict")
        for c in bench.comparisons:
            straddles = c.delta.low < 0 < c.delta.high
            ok = c.test.significant and not straddles
            paired.add_row(
                f"{c.a} vs {c.b}",
                c.metric,
                str(c.test.b),
                str(c.test.c),
                f"{c.delta.point:+.1%} [{c.delta.low:+.1%}, {c.delta.high:+.1%}]",
                f"{c.test.p_value:.3f}",
                "[green]significant[/green]" if ok else "[yellow]inconclusive[/yellow]",
            )
        console.print(paired)

    for r in bench.runs:
        if r.error:
            console.print(f"[red]{r.system} did not complete: {r.error}[/red]")

    console.print(
        "[dim]grounded accuracy and citation precision need a system that cites — a 0% there "
        "for bare/naive is a missing capability, not a defeat. Cross-system claims are made "
        "on fact accuracy and hallucination rate.[/dim]"
    )

    if save:
        json_path, md_path = write_benchmark(bench, Path("reports"))
        console.print(f"[dim]reports → {json_path}  ·  {md_path}[/dim]")
    else:
        console.print(to_markdown(bench))



@app.command()
def stats():
    """What is currently in the index."""
    from .store import Store

    s = Store().stats()
    console.print(
        Panel(
            f"documents: {s['documents']}\nchunks: {s['chunks']}\nby tier: {s['by_tier']}",
            title=str(settings.index_path),
            border_style="cyan",
        )
    )


@app.command()
def doctor():
    """Check that the local model server and models are actually there."""
    from .providers import OllamaProvider

    console.print(f"amin {__version__} · provider [bold]{settings.provider}[/bold]")
    if settings.provider == "ollama":
        prov = OllamaProvider()
        if prov.available():
            console.print(f"[green]ok[/green] ollama reachable at {prov.host}")
            try:
                import httpx

                tags = httpx.get(f"{prov.host}/api/tags", timeout=5).json().get("models", [])
                names = {m["name"] for m in tags}
                for want in {settings.answer_model, settings.utility_model, settings.embed_model}:
                    hit = any(n == want or n.startswith(want.split(":")[0]) for n in names)
                    mark = "[green]ok[/green]" if hit else "[red]missing[/red]"
                    console.print(f"{mark} {want}")
                if names:
                    console.print(f"[dim]installed: {', '.join(sorted(names))}[/dim]")
            except Exception as exc:
                console.print(f"[yellow]could not list models: {exc}[/yellow]")
        else:
            console.print(
                f"[red]ollama not reachable at {prov.host}[/red]\n"
                "start it with `ollama serve`, or run with --provider echo"
            )
    console.print(f"index: {settings.index_path} "
                  f"({'present' if settings.index_path.exists() else 'not built'})")


if __name__ == "__main__":
    app()
