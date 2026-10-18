"""Write the synthetic training corpus and its graded questions to data/train/.

Deterministic for a given seed; the output is gitignored and rebuildable.

Run:  uv run python scripts/build_train_corpus.py [--seed 7]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from amin.config import settings  # noqa: E402
from amin.train.corpus import write  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    n_docs, n_items = write(settings.train_path, seed=args.seed)
    items = [json.loads(x) for x in (settings.train_path / "items.jsonl").read_text().splitlines()]
    print(f"wrote {n_docs} documents, {n_items} items -> {settings.train_path.relative_to(REPO)}")
    for (kind, split), n in sorted(Counter((i["kind"], i["split"]) for i in items).items()):
        print(f"  {kind:14s} {split:5s} {n:5d}")
    print(f"  arabic               {sum(i['lang'] == 'ar' for i in items):5d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
