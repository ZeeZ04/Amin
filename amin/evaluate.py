"""The eval harness.

Grading is split into two accuracy metrics, and the split is the whole reason
a cross-system comparison here is honest:

  fact_accuracy       the expected fact appears in the answer. Every system can
                      be scored on this, including ones that cannot cite, so it
                      is the metric comparisons are made on.
  grounded_accuracy   the fact appears AND the expected source document is
                      cited. Only a system that cites can score here, so this
                      is reported as a capability, never used to claim a
                      baseline "lost".

Scoring a bare model on grounded_accuracy would guarantee it zero and prove
nothing. Separating the two is what makes "Amin beats naive RAG" a claim about
behaviour rather than an artefact of the grader.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import settings
from .prompts import looks_like_refusal
from .providers import _ML_FOLD
from .schema import Answer, Outcome
from .stats import Interval, wilson


@dataclass
class Item:
    id: str
    question: str
    kind: str  # answerable | unanswerable | out_of_scope
    expect_any: list[str] = field(default_factory=list)
    expect_doc: str = ""
    expect_route: str = ""
    # conflict items: every document that must appear in the answer's sources
    expect_docs: list[str] = field(default_factory=list)
    # conflict items: "conflict" (two live sources, must not pick) or
    # "version_skew" (current source answers, superseded one is surfaced)
    expect_outcome: str = ""
    note: str = ""
    lang: str = "en"
    tags: list[str] = field(default_factory=list)
    # Unanswerable from documents but true general knowledge (ADR-013). A
    # labelled general answer containing one of these passes; strict systems
    # still pass by refusing, so the strict rows are unchanged.
    expect_general: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, obj: dict) -> Item:
        return cls(
            id=obj["id"],
            question=obj["question"],
            kind=obj["kind"],
            expect_any=obj.get("expect_any", []),
            expect_doc=obj.get("expect_doc", ""),
            expect_route=obj.get("expect_route", ""),
            expect_docs=obj.get("expect_docs", []),
            expect_outcome=obj.get("expect_outcome", ""),
            note=obj.get("note", ""),
            lang=obj.get("lang", "en"),
            tags=obj.get("tags", []),
            expect_general=obj.get("expect_general", []),
        )


@dataclass
class Result:
    item: Item
    answer: Answer
    passed: bool  # the system's own standard: grounded if it cites, factual if not
    fact_ok: bool  # expected fact present, citation ignored
    grounded_ok: bool  # fact present AND expected document cited
    why: str

    def row(self) -> dict:
        return {
            "id": self.item.id,
            "kind": self.item.kind,
            "lang": self.item.lang,
            "tags": self.item.tags,
            "passed": self.passed,
            "fact_ok": self.fact_ok,
            "grounded_ok": self.grounded_ok,
            "why": self.why,
            "outcome": self.answer.outcome.value,
            "latency_ms": self.answer.latency_ms,
            "text": self.answer.text[:300],
            "cited_docs": sorted({s["doc_id"] for s in self.answer.sources()}),
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
    # Malayalam: atomic chillu and the ZWJ spelling are one letter (providers._ML_FOLD).
    return " ".join(s.lower().replace(",", "").translate(_ML_FOLD).split())


def grade(item: Item, answer: Answer, cites: bool = True) -> Result:
    """Grade one answer.

    `cites` declares whether the system under test is capable of citing. It
    changes only which metric `passed` follows; fact_ok and grounded_ok are
    always computed the same way, so the raw numbers stay comparable.
    """
    fact_ok = False
    grounded_ok = False

    if item.kind == "answerable":
        if answer.refused:
            why = f"refused an answerable question ({answer.outcome.value})"
        else:
            text = _normalise(answer.text)
            hit = next((e for e in item.expect_any if _normalise(e) in text), None)
            fact_ok = hit is not None
            if hit is None:
                why = "answer missing every expected fact"
            else:
                cited = {s["doc_id"] for s in answer.sources()}
                grounded_ok = (not item.expect_doc) or (item.expect_doc in cited)
                why = (
                    f"matched {hit!r}"
                    if grounded_ok
                    else f"correct fact but cited {sorted(cited) or 'nothing'}"
                )
        passed = grounded_ok if cites else fact_ok

    elif item.kind == "unanswerable":
        if answer.refused:
            passed, why = True, "refused, correctly"
        elif answer.outcome is Outcome.GENERAL:
            # A labelled general answer is not a document claim. It passes if
            # it is the true general fact, or if it declines to guess a
            # personal detail - and fails if it invents one.
            text = _normalise(answer.text)
            if item.expect_general:
                passed = any(_normalise(e) in text for e in item.expect_general)
                why = "answered from general knowledge, correctly" if passed else "general answer missing the fact"
            else:
                passed = looks_like_refusal(answer.text)
                why = "declined in general mode" if passed else "invented a personal detail in general mode"
        else:
            passed, why = False, "asserted an answer where no source exists"
        fact_ok = grounded_ok = passed

    elif item.kind == "out_of_scope":
        if answer.outcome != Outcome.REFUSED_OUT_OF_SCOPE:
            # A system with no scope routing can still decline verbally. That is
            # a weaker result than routing to a named referral, so it is scored
            # separately rather than counted as a pass.
            passed = False
            why = (
                "declined but did not route"
                if answer.refused
                else f"answered an out-of-scope question ({answer.outcome.value})"
            )
        elif item.expect_route and answer.routed_to != item.expect_route:
            passed = False
            why = f"routed to {answer.routed_to!r}, expected {item.expect_route!r}"
        else:
            passed = True
            why = f"routed to {answer.routed_to}"
        fact_ok = grounded_ok = passed

    elif item.kind == "conflict":
        cited = {s["doc_id"] for s in answer.sources()}
        missing = [d for d in item.expect_docs if d not in cited]
        if item.expect_outcome == "version_skew":
            # The current source must answer, and the superseded one must be
            # visible rather than silently dropped. Refusing here is a failure:
            # an outdated document is not a reason to withhold a current answer.
            if answer.refused:
                passed, why = False, "refused instead of answering from the current source"
            elif missing:
                passed, why = False, f"did not surface {missing}"
            else:
                passed, why = True, "answered from current source, superseded one surfaced"
        else:
            if answer.outcome is not Outcome.CONFLICT:
                passed = False
                why = f"resolved a disagreement silently ({answer.outcome.value})"
            elif missing:
                passed, why = False, f"flagged conflict but did not cite {missing}"
            else:
                passed, why = True, "surfaced both positions"
        fact_ok = grounded_ok = passed

    else:
        passed = False
        why = f"unknown item kind {item.kind!r}"

    return Result(
        item=item,
        answer=answer,
        passed=passed,
        fact_ok=fact_ok,
        grounded_ok=grounded_ok,
        why=why,
    )


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def _rate(num: int, den: int) -> float:
    return num / den if den else 0.0


def metrics(results: list[Result]) -> dict:
    """Metrics plus a Wilson 95% interval for every proportion.

    The intervals are not decoration. They are what stops a 3-item difference
    on a 30-item set being written up as an improvement.
    """
    answerable = [r for r in results if r.item.kind == "answerable"]
    unanswerable = [r for r in results if r.item.kind == "unanswerable"]
    oos = [r for r in results if r.item.kind == "out_of_scope"]
    conflicts = [r for r in results if r.item.kind == "conflict"]
    arabic = [r for r in results if r.item.lang == "ar"]

    precisions = [
        r.answer.citation_precision
        for r in results
        if any(c.cited_chunk_ids for c in r.answer.claims)
    ]
    latencies = sorted(r.answer.latency_ms for r in results)

    def ci(successes: int, n: int) -> dict:
        iv: Interval = wilson(successes, n)
        return {"point": iv.point, "low": iv.low, "high": iv.high, "n": n}

    n_fact = sum(r.fact_ok for r in answerable)
    n_grounded = sum(r.grounded_ok for r in answerable)
    n_refusal = sum(r.passed for r in unanswerable)
    n_halluc = sum(r.answer.asserted for r in unanswerable)
    n_route = sum(r.passed for r in oos)
    n_conflict = sum(r.passed for r in conflicts)

    return {
        "n": len(results),
        "fact_accuracy": _rate(n_fact, len(answerable)),
        "grounded_accuracy": _rate(n_grounded, len(answerable)),
        "correct_refusal": _rate(n_refusal, len(unanswerable)),
        "hallucination_rate": _rate(n_halluc, len(unanswerable)),
        "citation_precision": _rate(sum(precisions), len(precisions)) if precisions else 0.0,
        "routing_accuracy": _rate(n_route, len(oos)),
        # Reported as passed/total, not as a rate to optimise: with fewer than
        # ~30 items this is a capability check - does the path work at all -
        # and quoting it as a percentage would imply a precision it lacks.
        "conflict_handling": _rate(n_conflict, len(conflicts)),
        "conflict_passed": n_conflict,
        "overall_pass": _rate(sum(r.passed for r in results), len(results)),
        "arabic_pass": _rate(sum(r.passed for r in arabic), len(arabic)),
        "p50_latency_ms": latencies[len(latencies) // 2] if latencies else 0,
        "p95_latency_ms": latencies[int(len(latencies) * 0.95)] if latencies else 0,
        "ci": {
            "fact_accuracy": ci(n_fact, len(answerable)),
            "grounded_accuracy": ci(n_grounded, len(answerable)),
            "correct_refusal": ci(n_refusal, len(unanswerable)),
            "hallucination_rate": ci(n_halluc, len(unanswerable)),
            "routing_accuracy": ci(n_route, len(oos)),
        },
        "counts": {
            "answerable": len(answerable),
            "unanswerable": len(unanswerable),
            "out_of_scope": len(oos),
            "conflict": len(conflicts),
            "arabic": len(arabic),
        },
    }


def trust_score(stats: dict, hallucination_weight: float = 3.0) -> float:
    """The project's stated objective, in one number.

    A confident wrong answer costs more than an unnecessary refusal for an
    assistant people over-trust because it is theirs. The weight is a judgement,
    not a measurement; it lives here so it can be argued with rather than buried
    in a constant. See docs/EXPERIMENTS.md E3.
    """
    return stats["grounded_accuracy"] - hallucination_weight * stats["hallucination_rate"]


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------


def run(
    amin=None,
    items: list[Item] | None = None,
    on_result=None,
    system=None,
) -> tuple[list[Result], dict]:
    """Run an eval set through a system.

    Accepts either `system` (anything with .answer() and .cites, from
    amin.systems) or `amin` (an Amin engine, kept so existing callers and the
    `amin eval` command do not change).
    """
    if system is None:
        if amin is None:
            from .answer import Amin

            amin = Amin()
        answer_fn, cites = amin.ask, True
    else:
        answer_fn, cites = system.answer, getattr(system, "cites", True)

    items = items if items is not None else load_items()
    results: list[Result] = []
    for item in items:
        result = grade(item, answer_fn(item.question), cites=cites)
        results.append(result)
        if on_result:
            on_result(result)
    return results, metrics(results)


def write_report(results: list[Result], stats: dict, out_dir: Path, label: str = "eval") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    path = out_dir / f"{label}-{stamp}.json"
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
