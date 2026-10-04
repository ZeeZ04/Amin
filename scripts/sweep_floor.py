"""Sweep the evidence floor and print the trade-off curve.

This is the script behind docs/EXPERIMENTS.md E3. Re-run it whenever the model,
the corpus or the chunker changes - the floor is tuned to a specific pipeline
and does not transfer.

    python scripts/sweep_floor.py
    python scripts/sweep_floor.py --provider ollama --weight 3
"""

from __future__ import annotations

import argparse

from amin.answer import Amin
from amin.config import settings
from amin.evaluate import load_items, run
from amin.providers import get_provider
from amin.store import Store
from amin.verifier import Verifier

DEFAULT_GRID = [0.00, 0.15, 0.25, 0.34, 0.38, 0.45, 0.55, 0.70]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="echo", help="ollama | mlx | echo")
    parser.add_argument("--verifier", default=None, help="llm | lexical | off")
    parser.add_argument(
        "--weight",
        type=float,
        default=3.0,
        help="How many missed answers one hallucination is worth. The project's "
        "trust-first stance uses 3; argue with it rather than inheriting it.",
    )
    parser.add_argument("--grid", type=float, nargs="*", default=DEFAULT_GRID)
    args = parser.parse_args()

    items = load_items()
    store = Store()
    print(f"provider={args.provider} items={len(items)} weight={args.weight}")
    print(f"{'floor':>6} {'g_acc':>7} {'refuse':>7} {'halluc':>7} {'cite_p':>7} {'trust':>8}")

    rows = []
    for floor in args.grid:
        settings.evidence_floor = floor
        provider = get_provider(args.provider)
        amin = Amin(
            store=store,
            provider=provider,
            verifier=Verifier(provider, mode=args.verifier),
        )
        _, m = run(amin=amin, items=items)
        trust = m["grounded_accuracy"] - args.weight * m["hallucination_rate"]
        rows.append((floor, trust, m))
        print(
            f"{floor:6.2f} {m['grounded_accuracy']:7.3f} {m['correct_refusal']:7.3f} "
            f"{m['hallucination_rate']:7.3f} {m['citation_precision']:7.3f} {trust:8.3f}"
        )

    best_floor, best_trust, best_m = max(rows, key=lambda r: r[1])
    print(
        f"\nbest trust score {best_trust:.3f} at evidence_floor={best_floor:.2f} "
        f"(grounded {best_m['grounded_accuracy']:.3f}, "
        f"hallucination {best_m['hallucination_rate']:.3f})"
    )
    print("Record the run in docs/EXPERIMENTS.md before changing the default.")


if __name__ == "__main__":
    main()
