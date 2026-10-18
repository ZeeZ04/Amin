"""Stage 1: distil the teacher into supervised examples.

The teacher is the current `answer_model` (qwen3.6:27b) running the full Amin
pipeline over the training corpus. Every model call is recorded verbatim, and
an exchange is kept only when `evaluate.grade()` passes the final answer:
correct fact, expected document cited, or a correct refusal. A grader-approved
answer is the only kind the student ever imitates.

When a pipeline gate (evidence floor, identifier gate) refused before the
model was called, there is no exchange to record. For those unanswerable items
the prompt the model *would* have seen is built from the retrieved passages and
paired with NO_EVIDENCE, so the student learns to refuse on its own and does
not lean on the gates. Their share is capped so it does not learn to refuse
everything.

    uv run python -m amin.train.distill index     # ingest data/train/corpus
    uv run python -m amin.train.distill run       # teacher pass, resumable
    uv run python -m amin.train.distill export    # -> data/train/sft/{train,valid}.jsonl
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import typer
from rich.console import Console

from ..config import settings
from ..evaluate import Item, grade
from ..prompts import ANSWER_SYSTEM, VERIFY_SYSTEM, answer_prompt
from ..providers import Provider, get_provider
from ..store import Store
from .corpus import household_dir

app = typer.Typer(add_completion=False, help="Distil the teacher into SFT data.")
console = Console()

# Systems whose exchanges are worth imitating. Anything else (a baseline
# prompt, a future utility call) is recorded but never exported.
TRAINABLE = {ANSWER_SYSTEM: "answer", VERIFY_SYSTEM: "verify"}
GATE_REFUSAL = "NO_EVIDENCE"
MAX_REFUSAL_SHARE = 0.35


def paths() -> dict[str, Path]:
    root = settings.train_path
    return {
        "corpus": root / "corpus",
        "items": root / "items.jsonl",
        "index": root / "index",
        "raw": root / "teacher.jsonl",
        "sft": root / "sft",
    }


class RecordingProvider:
    """Passes every call through and keeps a transcript of it."""

    def __init__(self, inner: Provider):
        self.inner = inner
        self.name = inner.name
        self.model_label = getattr(inner, "model_label", settings.answer_model)
        self.calls: list[dict] = []

    def complete(self, prompt: str, *, model: str | None = None, system: str = "") -> str:
        out = self.inner.complete(prompt, model=model, system=system)
        self.calls.append({"system": system, "prompt": prompt, "response": out})
        return out

    def stream(self, prompt: str, *, model: str | None = None, system: str = "") -> Iterator[str]:
        yield self.complete(prompt, model=model, system=system)

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.inner.embed(texts)


def load_train_items(split: str | None = None) -> list[tuple[Item, dict]]:
    p = paths()["items"]
    if not p.exists():
        raise typer.BadParameter(f"{p} missing - run scripts/build_train_corpus.py first")
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [(Item.from_json(r), r) for r in rows if split is None or r["split"] == split]


def train_store(household: int) -> Store:
    return Store(paths()["index"] / f"{household_dir(household)}.db")


class Households:
    """One Amin per household index, built on first use."""

    def __init__(self, provider: Provider):
        from ..answer import Amin

        self._make = lambda h: Amin(store=train_store(h), provider=provider)
        self._cache: dict[int, object] = {}
        self.provider = provider

    def __getitem__(self, household: int):
        if household not in self._cache:
            self._cache[household] = self._make(household)
        return self._cache[household]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def record(amin, item: Item, row: dict) -> dict:
    """Run one item through its household's pipeline and keep what the grader needs."""
    amin.provider.calls.clear()
    answer = amin.ask(item.question)
    result = grade(item, answer)
    calls = [dict(c, role=TRAINABLE[c["system"]]) for c in amin.provider.calls if c["system"] in TRAINABLE]
    out = {
        "id": item.id,
        "split": row["split"],
        "kind": item.kind,
        "lang": item.lang,
        "passed": result.passed,
        "why": result.why,
        "outcome": answer.outcome.value,
        "calls": calls,
    }
    if result.passed and item.kind == "unanswerable" and not calls and answer.retrieved:
        prompt, _ = answer_prompt(item.question, answer.retrieved[: settings.top_k_final])
        out["gate_prompt"] = prompt
    return out


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


@app.command()
def index(provider: str = typer.Option(None, help="Embeddings provider (default: settings).")):
    """Ingest each training household into its own index, never the eval one."""
    from ..ingest import ingest

    prov = get_provider(provider)
    homes = sorted(p for p in paths()["corpus"].glob("h*") if p.is_dir())
    total_docs = total_chunks = 0
    with console.status("embedding…") as status:
        for n, home in enumerate(homes, start=1):
            store = train_store(int(home.name[1:]))
            store.reset()
            docs, chunks = ingest(home)
            store.upsert(docs, chunks, prov.embed([c.text for c in chunks]))
            total_docs, total_chunks = total_docs + len(docs), total_chunks + len(chunks)
            status.update(f"[{n}/{len(homes)}] {home.name}")
    console.print(f"[green]+[/green] {len(homes)} households, {total_docs} docs, {total_chunks} chunks "
                  f"→ {paths()['index']}")


@app.command()
def run(
    provider: str = typer.Option(None, help="Teacher provider (default: settings)."),
    limit: int = typer.Option(0, help="Stop after N new items - for a smoke test."),
    split: str = typer.Option(None, help="train | valid (default: both)."),
    stride: int = typer.Option(1, help="Take every Nth item - a smoke test that spans every family."),
):
    """Teacher pass. Appends to teacher.jsonl and skips ids already there."""
    out = paths()["raw"]
    done = {r["id"] for r in read_jsonl(out)}
    todo = [(i, r) for i, r in load_train_items(split)[::stride] if i.id not in done]
    if limit:
        todo = todo[:limit]
    homes = Households(RecordingProvider(get_provider(provider)))
    console.print(f"teacher {homes.provider.name}:{settings.answer_model} · {len(done)} done · {len(todo)} to go")

    kept = 0
    with out.open("a", encoding="utf-8") as fh, console.status("distilling…") as status:
        for n, (item, row) in enumerate(todo, start=1):
            try:
                rec = record(homes[row["household"]], item, row)
            except Exception as exc:  # one timeout must not lose the night's run
                console.print(f"[yellow]{item.id}: {type(exc).__name__}: {exc}[/yellow]")
                continue
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            kept += rec["passed"]
            status.update(f"[{n}/{len(todo)}] passed {kept}/{n}")
    console.print(f"[green]done[/green]: {kept}/{len(todo)} passed the grader")


def sft_examples(records: list[dict], seed: int = 0) -> dict[str, list[dict]]:
    """Grader-passed exchanges as chat examples, refusals capped."""
    rng = random.Random(seed)
    out: dict[str, list[dict]] = {"train": [], "valid": []}
    for split in out:
        model_made, gate_made = [], []
        for r in records:
            if r["split"] != split or not r["passed"]:
                continue
            for c in r["calls"]:
                if c["response"].strip():  # an empty reply is nothing to imitate
                    model_made.append(_chat(c["system"], c["prompt"], c["response"]))
            if "gate_prompt" in r:
                gate_made.append(_chat(ANSWER_SYSTEM, r["gate_prompt"], GATE_REFUSAL))
        refusals = sum(_is_refusal(e) for e in model_made)
        # refusals / total <= cap  =>  extra gate refusals allowed:
        room = int((MAX_REFUSAL_SHARE * len(model_made) - refusals) / (1 - MAX_REFUSAL_SHARE))
        rng.shuffle(gate_made)
        rows = model_made + gate_made[: max(room, 0)]
        rng.shuffle(rows)
        out[split] = rows
    return out


def _chat(system: str, prompt: str, response: str) -> dict:
    return {"messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": response.strip()},
    ]}


def _is_refusal(example: dict) -> bool:
    return example["messages"][-1]["content"].upper().startswith(GATE_REFUSAL)


@app.command()
def export():
    """Write SFT data in the chat format mlx_lm.lora reads."""
    sets = sft_examples(read_jsonl(paths()["raw"]))
    d = paths()["sft"]
    d.mkdir(parents=True, exist_ok=True)
    for split, rows in sets.items():
        (d / f"{split}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
        refusals = sum(_is_refusal(r) for r in rows)
        console.print(f"{split}: {len(rows)} examples ({refusals} refusals) → {d / f'{split}.jsonl'}")
    n = len(sets["train"])
    console.print(f"[dim]2 epochs at batch 4 ≈ --iters {max(2 * n // 4, 1)}[/dim]")


if __name__ == "__main__":
    app()
