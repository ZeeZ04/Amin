"""Stage 2: preference pairs from the student's own failures.

The SFT student is served by `mlx_lm.server` and sampled several times per
training item, warm, through the real pipeline. A sample the grader fails
becomes `rejected`; the teacher's grader-passed reply to the *same prompt*
becomes `chosen`. Pairs are only formed when the two prompts are byte-equal,
so a pair never compares answers to different passages.

Unanswerable items that a gate refused before any model call are sampled
directly on the prompt the model would have seen: a student that answers there
is exactly the hallucination the gates are covering for.

Hallucinated answers and Arabic items are duplicated in the output, because
hallucination is the metric the ship gate guards and Arabic is the slice with
the least data.

    mlx_lm.server --model data/models/amin-1-sft --port 8080
    uv run python -m amin.train.preferences run --samples 4
    uv run python -m amin.train.preferences export
"""

from __future__ import annotations

import json
import random

import typer
from rich.console import Console

from ..config import settings
from ..prompts import ANSWER_SYSTEM, looks_like_refusal
from ..providers import MLXProvider
from .distill import (
    GATE_REFUSAL,
    Households,
    RecordingProvider,
    load_train_items,
    paths,
    read_jsonl,
    record,
)

app = typer.Typer(add_completion=False, help="Build DPO pairs from the student's failures.")
console = Console()


def pref_paths() -> dict:
    root = settings.train_path
    return {"raw": root / "student.jsonl", "dpo": root / "dpo"}


def teacher_replies(records: list[dict]) -> dict[str, tuple[dict[str, str], str | None]]:
    """item id -> ({prompt: grader-passed answer reply}, gate prompt or None)."""
    out: dict[str, tuple[dict[str, str], str | None]] = {}
    for r in records:
        if not r["passed"]:
            # The corpus is generated, so an unanswerable item is unanswerable
            # by construction: NO_EVIDENCE is right even where the teacher
            # answered. These are the pairs that can take the student past it.
            if r["kind"] == "unanswerable":
                replies = {c["prompt"]: GATE_REFUSAL for c in r["calls"] if c["role"] == "answer"}
                if replies:
                    out[r["id"]] = (replies, None)
            continue
        replies = {c["prompt"]: c["response"] for c in r["calls"] if c["role"] == "answer"}
        gate = r.get("gate_prompt")
        if gate:
            replies[gate] = GATE_REFUSAL
        if replies:
            out[r["id"]] = (replies, gate)
    return out


@app.command()
def run(
    samples: int = typer.Option(4, help="Samples per item."),
    temperature: float = typer.Option(0.7, help="Sampling temperature for the student."),
    host: str = typer.Option(None, help="mlx_lm.server address (default: settings.mlx_host)."),
    limit: int = typer.Option(0, help="Stop after N items - for a smoke test."),
    prefix: str = typer.Option("", help="Only item ids starting with this, e.g. t3- for the traps."),
):
    """Sample the student; keep every failure that has a teacher counterpart."""
    teacher = teacher_replies(read_jsonl(paths()["raw"]))
    out = pref_paths()["raw"]
    done = {r["id"] for r in read_jsonl(out)}
    todo = [(i, r) for i, r in load_train_items()
            if i.id in teacher and i.id not in done and i.id.startswith(prefix)]
    if limit:
        todo = todo[:limit]

    student = MLXProvider(host=host, temperature=temperature)
    homes = Households(RecordingProvider(student))
    console.print(f"student at {student.host} · {len(todo)} items × {samples} samples")

    found = 0
    with out.open("a", encoding="utf-8") as fh, console.status("sampling…") as status:
        for n, (item, row) in enumerate(todo, start=1):
            chosen_by_prompt, gate_prompt = teacher[item.id]
            rejected: list[dict] = []
            for _ in range(samples):
                try:
                    if gate_prompt:
                        # The pipeline would refuse before calling the student,
                        # so ask it directly what the gates are covering for.
                        reply = student.complete(gate_prompt, system=ANSWER_SYSTEM)
                        failed = not (reply.upper().startswith(GATE_REFUSAL) or looks_like_refusal(reply))
                        calls = [{"prompt": gate_prompt, "response": reply}] if failed else []
                    else:
                        rec = record(homes[row["household"]], item, row)
                        failed = not rec["passed"]
                        calls = [c for c in rec["calls"] if c["role"] == "answer"] if failed else []
                except Exception as exc:
                    console.print(f"[yellow]{item.id}: {type(exc).__name__}: {exc}[/yellow]")
                    continue
                for c in calls:
                    if c["prompt"] in chosen_by_prompt and c["response"].strip() != chosen_by_prompt[c["prompt"]].strip():
                        rejected.append({"prompt": c["prompt"], "rejected": c["response"],
                                         "chosen": chosen_by_prompt[c["prompt"]]})
            fh.write(json.dumps({"id": item.id, "split": row["split"], "kind": item.kind, "lang": item.lang,
                                 "pairs": rejected}, ensure_ascii=False) + "\n")
            fh.flush()
            found += bool(rejected)
            status.update(f"[{n}/{len(todo)}] items with failures: {found}")
    console.print(f"[green]done[/green]: the student failed on {found}/{len(todo)} items")


def dpo_rows(records: list[dict], seed: int = 0, balance: list[dict] | None = None) -> dict[str, list[dict]]:
    """Preference rows from the student's failures.

    `balance` holds teacher records for answerable items. Each becomes a pair
    whose rejected side is a refusal, as many as there are refusal-side pairs
    in the split. Without them DPO can lower hallucination the cheap way, by
    refusing more of everything - the ADR-011 trade.
    """
    rng = random.Random(seed)
    out: dict[str, list[dict]] = {"train": [], "valid": []}
    for r in records:
        seen: set[tuple[str, str]] = set()
        for p in r["pairs"]:
            key = (p["prompt"], p["rejected"].strip())
            if key in seen:
                continue
            seen.add(key)
            row = {"system": ANSWER_SYSTEM, "prompt": p["prompt"],
                   "chosen": p["chosen"].strip(), "rejected": p["rejected"].strip()}
            weight = 1 + (r["kind"] == "unanswerable") + (r["lang"] == "ar")
            out[r["split"]].extend([row] * weight)
    for split, rows in out.items():
        refusal_side = sum(r["chosen"] == GATE_REFUSAL for r in rows)
        pool = [
            {"system": ANSWER_SYSTEM, "prompt": c["prompt"], "chosen": c["response"].strip(), "rejected": GATE_REFUSAL}
            for b in balance or [] if b["split"] == split and b["passed"] and b["kind"] == "answerable"
            for c in b["calls"] if c["role"] == "answer"
        ]
        rng.shuffle(pool)
        rows.extend(pool[:refusal_side])
        rng.shuffle(rows)
    return out


@app.command()
def export(
    balance_prefix: str = typer.Option("t3-", help="Answerable teacher items used to balance refusal pairs."),
):
    """Write DPO data in the prompt/chosen/rejected format mlx_lm_lora reads."""
    balance = [r for r in read_jsonl(paths()["raw"]) if r["id"].startswith(balance_prefix)] if balance_prefix else []
    sets = dpo_rows(read_jsonl(pref_paths()["raw"]), balance=balance)
    d = pref_paths()["dpo"]
    d.mkdir(parents=True, exist_ok=True)
    for split, rows in sets.items():
        (d / f"{split}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
        console.print(f"{split}: {len(rows)} pairs → {d / f'{split}.jsonl'}")


if __name__ == "__main__":
    app()
