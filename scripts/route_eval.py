"""Routing eval (E34): keyword patterns vs the single-pass router, per language.

    uv run python scripts/route_eval.py [--host http://127.0.0.1:8080]

data/eval/routing.jsonl holds 76 messages in English, Arabic and Malayalam,
labelled medical | legal | financial | self_harm | none. The `none` items
include document questions that use the routes' vocabulary (insurance cover,
a pharmacy receipt, a pool manual's chlorine dose): a router that fires on
words instead of intent shows up there.
"""

from __future__ import annotations

import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

import typer

from amin.classify import Classifier, Router
from amin.covenant import Covenant

app = typer.Typer(add_completion=False)


@app.command()
def main(host: str = "http://127.0.0.1:8080", out: Path = Path("reports/routing-latest.json")) -> None:
    items = [json.loads(x) for x in Path("data/eval/routing.jsonl").read_text().splitlines()]
    cov = Covenant()
    router = Router([(r.name, r.describe, r.threshold) for r in cov.routes if r.describe], Classifier(host, 30))
    rows, secs = [], []
    for it in items:
        pat = cov.check(it["question"])
        t = time.perf_counter()
        ch = router.route(it["question"])
        secs.append(time.perf_counter() - t)
        both = cov.check(it["question"], _Replay(ch))
        rows.append({**it, "pattern": pat.route.name if pat.route else "none",
                     "router": ch.label or "none", "combined": both.route.name if both.route else "none",
                     "probs": {k: round(v, 3) for k, v in ch.probs.items()}})

    def report(key: str) -> str:
        ok = sum(r[key] == r["expect"] for r in rows)
        by_lang = defaultdict(lambda: [0, 0])
        for r in rows:
            by_lang[r["lang"]][0] += r[key] == r["expect"]
            by_lang[r["lang"]][1] += 1
        crisis = [r for r in rows if r["expect"] == "self_harm"]
        caught = sum(r[key] == "self_harm" for r in crisis)
        false_alarm = sum(r[key] != "none" for r in rows if r["expect"] == "none")
        langs = " · ".join(f"{k} {a}/{b}" for k, (a, b) in sorted(by_lang.items()))
        return (f"{key:9s} {ok}/{len(rows)} correct ({langs}) · crisis caught {caught}/{len(crisis)}"
                f" · false alarms {false_alarm}/{sum(r['expect'] == 'none' for r in rows)}")

    for key in ("pattern", "router", "combined"):
        typer.echo(report(key))
    typer.echo(f"router p50 {statistics.median(secs) * 1000:.0f} ms · max {max(secs) * 1000:.0f} ms")
    for r in rows:
        if r["combined"] != r["expect"]:
            typer.echo(f"  miss {r['id']} [{r['lang']}] expect {r['expect']} got {r['combined']}: {r['question'][:70]}")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1))


class _Replay:
    """Hands covenant.check() a decision already made, so it is timed once."""

    def __init__(self, choice):
        self.choice = choice

    def route(self, _):
        return self.choice


if __name__ == "__main__":
    app()
