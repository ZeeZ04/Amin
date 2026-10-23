"""The on-device student's SFT set (ADR-014): amin-3's mix plus Malayalam.

    data/train/sft/          distill export: grounded en/ar/ml + general + fallback
    data/train/ml_general.jsonl   amin.train.malayalam export: Aya + Dolly
        → data/train/edge/{train,valid}.jsonl

    uv run python -m amin.train.edge assemble
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import typer

SFT = Path("data/train/sft")
ML = Path("data/train/ml_general.jsonl")
OUT = Path("data/train/edge")

app = typer.Typer(add_completion=False, help="On-device student SFT set.")


@app.callback()
def _main() -> None:
    """On-device student SFT set."""


def _read(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


@app.command()
def assemble(seed: int = 0) -> None:
    rng = random.Random(seed)
    sets = {s: _read(SFT / f"{s}.jsonl") for s in ("train", "valid")}
    for i, row in enumerate(_read(ML)):  # 1 in 10 held out, like every other source
        row = {"messages": row["messages"]}
        sets["valid" if i % 10 == 9 else "train"].append(row)
    OUT.mkdir(parents=True, exist_ok=True)
    for split, rows in sets.items():
        rng.shuffle(rows)
        (OUT / f"{split}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        typer.echo(f"{split}: {len(rows)} → {OUT / f'{split}.jsonl'}")
    typer.echo(f"1 epoch at batch 4 = --iters {len(sets['train']) // 4}")


if __name__ == "__main__":
    app()
