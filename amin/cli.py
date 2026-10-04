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
):
    """Run the eval set and print the metrics that matter."""
    from .evaluate import load_items, metrics, run, write_report

    items = load_items(eval_set)
    amin = _amin(provider)

    rows = []
    with console.status(f"running {len(items)} eval items…") as status:
        def on_result(result):
            rows.append(result)
            status.update(f"[{len(rows)}/{len(items)}] {result.item.id}")

        results, _ = run(amin=amin, items=items, on_result=on_result)
    stats = metrics(results)

    detail = Table(title="eval detail", title_justify="left")
    detail.add_column("id", no_wrap=True)
    detail.add_column("kind", no_wrap=True)
    detail.add_column("", no_wrap=True)
    detail.add_column("why", overflow="fold")
    for r in results:
        if failures_only and r.passed:
            continue
        detail.add_row(
            r.item.id,
            r.item.kind,
            "[green]pass[/green]" if r.passed else "[red]FAIL[/red]",
            r.why,
        )
    console.print(detail)

    summary = Table(title="metrics", title_justify="left")
    summary.add_column("metric", no_wrap=True)
    summary.add_column("value", justify="right", no_wrap=True)
    summary.add_column("direction", no_wrap=True, style="dim")
    for key, value, direction in [
        ("grounded_accuracy", stats["grounded_accuracy"], "higher is better"),
        ("correct_refusal", stats["correct_refusal"], "higher is better"),
        ("hallucination_rate", stats["hallucination_rate"], "LOWER is better"),
        ("citation_precision", stats["citation_precision"], "higher is better"),
        ("routing_accuracy", stats["routing_accuracy"], "higher is better"),
        ("overall_pass", stats["overall_pass"], "higher is better"),
    ]:
        summary.add_row(key, f"{value:.1%}", direction)
    summary.add_row("p50 latency", f"{stats['p50_latency_ms']} ms", "")
    summary.add_row("items", str(stats["n"]), str(stats["counts"]))
    console.print(summary)

    if save:
        path = write_report(results, stats, Path("reports"))
        console.print(f"[dim]report → {path}[/dim]")


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
