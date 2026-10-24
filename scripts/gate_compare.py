"""Paired comparison of two bench runs on the same items, per kind (the ADR-012 gate).

    uv run python scripts/gate_compare.py reports/bench-A.json reports/bench-B.json [--tags]

Kinds are the eval set's own (answerable, unanswerable, out_of_scope, ...).
With --tags, slice m's tag groups (adjacent-fact traps, doc-silent declines)
are split out too. Each row is a McNemar test on items both runs saw.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from amin.stats import mcnemar  # noqa: E402


def results(path: str) -> tuple[str, dict[str, dict]]:
    d = json.loads(Path(path).read_text())
    run = d["runs"][0]
    return run.get("model") or d["config"].get("answer_model"), {r["id"]: r for r in run["results"]}


def main() -> None:
    a_path, b_path, *flags = sys.argv[1:]
    (a_name, a), (b_name, b) = results(a_path), results(b_path)
    groups: dict[str, list[str]] = defaultdict(list)
    for i, r in a.items():
        if i not in b:
            continue
        groups[r["kind"]].append(i)
        if "--tags" in flags:
            for t in r.get("tags", []):
                groups[f"  tag:{t}"].append(i)
        if r.get("lang") == "ar":
            groups["  arabic"].append(i)
    print(f"{'':28s} {a_name:>18s} {b_name:>18s}      p")
    for g, ids in sorted(groups.items(), key=lambda kv: (kv[0].startswith(" "), kv[0])):
        pa = [a[i]["passed"] for i in ids]
        pb = [b[i]["passed"] for i in ids]
        test = mcnemar(pa, pb)
        print(f"{g:28s} {sum(pa):>11d}/{len(ids):<6d} {sum(pb):>11d}/{len(ids):<6d} {test.p_value:6.3f}")


if __name__ == "__main__":
    main()
