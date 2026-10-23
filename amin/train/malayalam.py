"""Malayalam general-chat SFT examples (E32), from human-checked public data.

    aya     CohereLabs/aya_dataset, Malayalam rows written by native speakers
            (Apache-2.0). Every 10th row is the held-out eval set in
            scripts/ml_eval.py and is never exported here.
    dolly   ai4bharat/indic-align, Dolly translated with IndicTrans2
            (CC-BY-4.0). Readable but translated, so it is capped below the
            human rows rather than outnumbering them by ten to one.

Replies are used as written: they are the verified Malayalam this model
should learn to produce. Grounded Malayalam comes from corpus.py's Malayalam
families via the usual distill path, not from here.

    uv run --with pandas --with pyarrow python -m amin.train.malayalam export
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import typer

from ..prompts import GENERAL_SYSTEM

RAW = Path("data/ml/raw")
OUT = Path("data/train/ml_general.jsonl")
DOLLY_CAP = 3000
MAX_CHARS = 2400  # about 800 tokens on a Gemma tokenizer; keeps batches even

app = typer.Typer(add_completion=False, help="Malayalam general-chat SFT examples.")
_ML = re.compile(r"[ഀ-ൿ]")
_LETTER = re.compile(r"[^\W\d_]")


@app.callback()
def _main() -> None:
    """Malayalam general-chat SFT examples."""


def ml_ratio(text: str) -> float:
    return len(_ML.findall(text)) / max(len(_LETTER.findall(text)), 1)


def usable(q: str, a: str) -> bool:
    return (ml_ratio(q) >= 0.6 and ml_ratio(a) >= 0.6
            and 2 <= len(q) and 2 <= len(a) and len(q) + len(a) <= MAX_CHARS)


def example(q: str, a: str, source: str) -> dict:
    return {"messages": [{"role": "system", "content": GENERAL_SYSTEM},
                         {"role": "user", "content": q.strip()},
                         {"role": "assistant", "content": a.strip()}],
            "source": source}


def aya_rows() -> list[tuple[str, str]]:
    import pandas as pd

    aya = pd.read_parquet(RAW / "aya_dataset.parquet")
    aya = aya[aya.language == "Malayalam"].reset_index(drop=True)
    # i % 10 == 0 is scripts/ml_eval.py's held-out set: same rule, same order.
    return [(r.inputs, r.targets) for i, r in aya.iterrows() if i % 10 != 0]


def dolly_rows() -> list[tuple[str, str]]:
    import pandas as pd

    out = []
    for turns in pd.read_parquet(RAW / "dolly.parquet", columns=["mal_Mlym"]).mal_Mlym.dropna():
        flat = [str(x) for t in turns for x in (t.tolist() if hasattr(t, "tolist") else [t])]
        if len(flat) >= 2:
            out.append((flat[0], flat[1]))
    return out


@app.command()
def export(seed: int = 0) -> None:
    rng = random.Random(seed)
    held = {q.strip() for q, _ in held_out()}
    aya = [(q, a) for q, a in aya_rows() if usable(q, a) and q.strip() not in held]
    dolly = [(q, a) for q, a in dolly_rows() if usable(q, a)]
    rng.shuffle(dolly)
    seen: set[str] = set()
    rows = []
    for source, pairs in (("aya", aya), ("dolly", dolly[:DOLLY_CAP])):
        for q, a in pairs:
            key = " ".join(q.split())
            if key in seen or key in held:
                continue
            seen.add(key)
            rows.append(example(q, a, source))
    rng.shuffle(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    n_aya = sum(r["source"] == "aya" for r in rows)
    typer.echo(f"{len(rows)} examples → {OUT} (aya {n_aya}, dolly {len(rows) - n_aya})")


def held_out() -> list[tuple[str, str]]:
    path = Path("data/ml/aya-test.jsonl")
    return [(r["question"], r["gold"]) for r in map(json.loads, path.read_text().splitlines())] if path.exists() else []


if __name__ == "__main__":
    app()
