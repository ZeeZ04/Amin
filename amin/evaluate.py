"""The eval harness — the centrepiece of this project.

A grounded assistant is only as good as the number you can quote for it. The
harness runs a fixed question set through the full pipeline and reports five
metrics. Three of them are about honesty rather than accuracy, which is the
whole point:

  grounded_accuracy    answerable items answered correctly AND cited correctly
  correct_refusal      unanswerable items where Amin refused
  hallucination_rate   unanswerable items where Amin asserted something anyway
  citation_precision   claims whose citation survived verification
  routing_accuracy     out-of-scope items routed to the right referral

Item types in the eval set:
  answerable    expect_any (substrings, any one matches) + expect_doc
  unanswerable  no answer exists, or the premise is false. Refusal is correct.
  out_of_scope  must be routed, not answered. `expect_route` names the route.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .answer import Amin
from .config import settings
from .schema import Answer, Outcome


@dataclass
class Item:
    id: str
    question: str
    kind: str  # answerable | unanswerable | out_of_scope
    expect_any: list[str] = field(default_factory=list)
    expect_doc: str = ""
    expect_route: str = ""
    note: str = ""

    @classmethod
    def from_json(cls, obj: dict) -> Item:
        return cls(
            id=obj["id"],
            question=obj["question"],
            kind=obj["kind"],
            expect_any=obj.get("expect_any", []),
            expect_doc=obj.get("expect_doc", ""),
            expect_route=obj.get("expect_route", ""),
            note=obj.get("note", ""),
        )


@dataclass
class Result:
    item: Item
    answer: Answer
    passed: bool
    why: str

    def row(self) -> dict:
        return {
            "id": self.item.id,
            "kind": self.item.kind,
            "passed": self.passed,
            "why": self.why,
            "outcome": self.answer.outcome.value,
            "latency_ms": self.answer.latency_ms,
            "text": self.answer.text[:300],
            "cited_docs": sorted(
                {s["doc_id"] for s in self.answer.sources()}
            ),
        }


def load_items(path: Path | None = None) -> list[Item]:
    p = Path(path or settings.eval_set)
    items = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            items.append(Item.from_json(json.loads(line)))
    return items


# ---------------------------------------------------------------------------
# grading
# ---------------------------------------------------------------------------


def _normalise(s: str) -> str:
    return " ".join(s.lower().replace(",", "").split())


def grade(item: Item, answer: Answer) -> tuple[bool, str]:
    if item.kind == "answerable":
        if answer.refused:
            return False, f"refused an answerable question ({answer.outcome.value})"
        text = _normalise(answer.text)
        hit = next((e for e in item.expect_any if _normalise(e) in text), None)
        if hit is None:
            return False, "answer missing every expected fact"
        if item.expect_doc:
            cited = {s["doc_id"] for s in answer.sources()}
            if item.expect_doc not in cited:
                return False, f"correct fact but cited {sorted(cited) or 'nothing'}"
        return True, f"matched {hit!r}"

    if item.kind == "unanswerable":
        if answer.refused:
            return True, "refused, correctly"
        return False, "asserted an answer where no source exists"

    if item.kind == "out_of_scope":
        if answer.outcome != Outcome.REFUSED_OUT_OF_SCOPE:
            return False, f"not routed (outcome: {answer.outcome.value})"
        if item.expect_route and answer.routed_to != item.expect_route:
            return False, f"routed to {answer.routed_to!r}, expected {item.expect_route!r}"
        return True, f"routed to {answer.routed_to}"

    return False, f"unknown item kind {item.kind!r}"


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def _rate(num: int, den: int) -> float:
    return num / den if den else 0.0


def metrics(results: list[Result]) -> dict:
    answerable = [r for r in results if r.item.kind == "answerable"]
    unanswerable = [r for r in results if r.item.kind == "unanswerable"]
    oos = [r for r in results if r.item.kind == "out_of_scope"]

    precisions = [
        r.answer.citation_precision
        for r in results
        if any(c.cited_chunk_ids for c in r.answer.claims)
    ]
    latencies = sorted(r.answer.latency_ms for r in results)

    return {
        "n": len(results),
        "grounded_accuracy": _rate(sum(r.passed for r in answerable), len(answerable)),
        "correct_refusal": _rate(sum(r.passed for r in unanswerable), len(unanswerable)),
        "hallucination_rate": _rate(
            sum(r.answer.asserted for r in unanswerable), len(unanswerable)
        ),
        "citation_precision": _rate(sum(precisions), len(precisions)) if precisions else 0.0,
        "routing_accuracy": _rate(sum(r.passed for r in oos), len(oos)),
        "overall_pass": _rate(sum(r.passed for r in results), len(results)),
        "p50_latency_ms": latencies[len(latencies) // 2] if latencies else 0,
        "counts": {
            "answerable": len(answerable),
            "unanswerable": len(unanswerable),
            "out_of_scope": len(oos),
        },
    }


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------


def run(
    amin: Amin | None = None,
    items: list[Item] | None = None,
    on_result=None,
) -> tuple[list[Result], dict]:
    amin = amin or Amin()
    items = items if items is not None else load_items()
    results: list[Result] = []
    for item in items:
        answer = amin.ask(item.question)
        passed, why = grade(item, answer)
        result = Result(item=item, answer=answer, passed=passed, why=why)
        results.append(result)
        if on_result:
            on_result(result)
    return results, metrics(results)


def write_report(results: list[Result], stats: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    path = out_dir / f"eval-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "timestamp": stamp,
                "config": {
                    "provider": settings.provider,
                    "answer_model": settings.answer_model,
                    "utility_model": settings.utility_model,
                    "embed_model": settings.embed_model,
                    "verifier": settings.verifier,
                    "evidence_floor": settings.evidence_floor,
                    "top_k_final": settings.top_k_final,
                    "chunk_chars": settings.chunk_chars,
                },
                "metrics": stats,
                "results": [r.row() for r in results],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path
