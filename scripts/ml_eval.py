"""Malayalam eval (E32): grounded reading and general answering, before and after training.

Two sets, both from public, human-written data:

    indicqa   ai4bharat/IndicQA, Malayalam. Wikipedia passages with questions
              written by people; 488 of 1,589 have no answer in the passage.
              Scored like Amin's main bench: answerable items must contain the
              gold span, unanswerable ones must say NO_EVIDENCE.
    aya       CohereLabs/aya_dataset, the Malayalam rows written by native
              speakers. Every 10th row is held out here and never trained on.
              Scored on answering in Malayalam and on chrF against the human
              reply; that is a weak signal, which is why this set is also the
              one a fluent reviewer reads (ml_review.md).

IndicQA is split by article: even articles select checkpoints, odd articles
are the final test, used once. Nothing from either half is trained on.

    uv run python scripts/ml_eval.py split
    uv run python scripts/ml_eval.py run --set indicqa-sel --limit 200 --model amin-3
"""

from __future__ import annotations

import json
import random
import re
import statistics
import time
from collections import Counter
from pathlib import Path

import httpx
import typer

from amin.prompts import ANSWER_SYSTEM, GENERAL_SYSTEM, looks_like_refusal
from amin.providers import content_tokens

ROOT = Path("data/ml")
RAW = ROOT / "raw"
app = typer.Typer(add_completion=False)

ML = re.compile(r"[ഀ-ൿ]")
LETTER = re.compile(r"[^\W\d_]")
CHUNK = 900
TOP_K = 6


def ml_ratio(text: str) -> float:
    letters = LETTER.findall(text)
    return len(ML.findall(text)) / max(len(letters), 1)


def chunks(text: str) -> list[str]:
    """Paragraph-ish pieces of at most CHUNK characters, split at sentence ends."""
    out, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        if cur and len(cur) + len(sent) > CHUNK:
            out.append(cur.strip())
            cur = ""
        cur += sent + " "
    if cur.strip():
        out.append(cur.strip())
    return out


@app.command()
def split() -> None:
    raw = json.loads((RAW / "indicqa.ml.json").read_text())["data"]
    sel, test = [], []
    for i, art in enumerate(raw):
        for para in art["paragraphs"]:
            for qa in para["qas"]:
                gold = (qa["answers"][0]["text"] if qa["answers"] else "").strip()
                start = qa["answers"][0]["answer_start"] if gold else -1
                item = {"id": f"iqa-{i}-{qa['id']}", "question": qa["question"].strip(),
                        "context": para["context"], "gold": gold, "start": start}
                (sel if i % 2 == 0 else test).append(item)
    _write(ROOT / "indicqa-sel.jsonl", sel)
    _write(ROOT / "indicqa-test.jsonl", test)

    import pandas as pd

    aya = pd.read_parquet(RAW / "aya_dataset.parquet")
    aya = aya[aya.language == "Malayalam"].reset_index(drop=True)
    held = [{"id": f"aya-{i}", "question": r.inputs.strip(), "gold": r.targets.strip()}
            for i, r in aya.iterrows() if i % 10 == 0]
    _write(ROOT / "aya-test.jsonl", held)
    typer.echo(f"indicqa sel {len(sel)} · test {len(test)} · aya held-out {len(held)}")


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def grounded_prompt(item: dict) -> str:
    """The passages Amin's retriever would hand over: the answer's piece and its neighbours."""
    pieces = chunks(item["context"])
    if item["start"] >= 0:
        pos, at = 0, 0
        for j, p in enumerate(pieces):
            if pos + len(p) >= item["start"]:
                at = j
                break
            pos += len(p) + 1
        lo = max(0, min(at - TOP_K // 2, len(pieces) - TOP_K))
        pieces = pieces[lo : lo + TOP_K]
    else:
        pieces = pieces[:TOP_K]
    body = "\n\n".join(f"[S{i}] wikipedia (tier: reference)\n{p}" for i, p in enumerate(pieces, 1))
    return (f"{body}\n\n<question>{item['question']}</question>\n\n"
            "Answer using only the passages above, tagging every sentence.")


def _norm(s: str) -> list[str]:
    return sorted(content_tokens(s))


def recall(pred: str, gold: str) -> float:
    """Share of the gold span's words the reply contains. Amin answers in full
    sentences, so precision against a two-word span would punish the format,
    not the fact; the main bench grades containment for the same reason."""
    g = set(_norm(gold))
    return len(g & set(_norm(pred))) / len(g) if g else 0.0


def chrf(pred: str, gold: str, n: int = 6, beta: float = 2.0) -> float:
    """chrF (Popović 2015) on characters, spaces removed."""
    a, b = re.sub(r"\s+", "", pred), re.sub(r"\s+", "", gold)
    ps, rs = [], []
    for k in range(1, n + 1):
        pa = Counter(a[i : i + k] for i in range(len(a) - k + 1))
        pb = Counter(b[i : i + k] for i in range(len(b) - k + 1))
        hit = sum((pa & pb).values())
        if pa:
            ps.append(hit / sum(pa.values()))
        if pb:
            rs.append(hit / sum(pb.values()))
    p, r = (statistics.mean(ps) if ps else 0), (statistics.mean(rs) if rs else 0)
    return 0.0 if not p + r else (1 + beta**2) * p * r / (beta**2 * p + r) * 100


ENDPOINTS = {"mlx": "http://127.0.0.1:8080/v1", "ollama": "http://127.0.0.1:11434/v1"}


def chat(base: str, model: str, system: str, user: str) -> tuple[str, float]:
    t = time.perf_counter()
    if "11434" in base:
        # Ollama's OpenAI endpoint ignores "think": false, so Qwen3 spends the whole
        # token budget thinking and returns nothing. The native API honours it, and
        # it is what Amin's own OllamaProvider calls.
        r = httpx.post(f"{base.removesuffix('/v1')}/api/generate", timeout=600, json={
            "model": model, "system": system, "prompt": user, "stream": False, "think": False,
            "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 600},
        })
        r.raise_for_status()
        return r.json().get("response", "").strip(), time.perf_counter() - t
    r = httpx.post(f"{base}/chat/completions", timeout=300, json={
        # mlx_lm.server serves one model whatever is asked; "default_model" means that one.
        "model": "default_model", "temperature": 0, "max_tokens": 600,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "chat_template_kwargs": {"enable_thinking": False},
    })
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"] or ""
    return re.sub(r"(?s)<think>.*?</think>", "", text).strip(), time.perf_counter() - t


@app.command()
def run(
    set_: str = typer.Option("indicqa-sel", "--set"),
    model: str = "amin-3",
    server: str = "mlx",
    limit: int = 200,
    seed: int = 0,
) -> None:
    rows = [json.loads(x) for x in (ROOT / f"{set_}.jsonl").read_text().splitlines()]
    random.Random(seed).shuffle(rows)
    rows = rows[:limit]
    out = ROOT / "runs" / f"{set_}--{model.replace('/', '_')}.jsonl"
    out.parent.mkdir(exist_ok=True)
    done = {json.loads(x)["id"] for x in out.read_text().splitlines()} if out.exists() else set()
    base = ENDPOINTS.get(server, server)  # a name above, or a full URL
    with out.open("a") as fh:
        for item in rows:
            if item["id"] in done:
                continue
            grounded = set_.startswith("indicqa")
            system, user = (ANSWER_SYSTEM, grounded_prompt(item)) if grounded else (GENERAL_SYSTEM, item["question"])
            reply, secs = chat(base, model, system, user)
            fh.write(json.dumps({**{k: item[k] for k in ("id", "question", "gold")},
                                 "reply": reply, "secs": round(secs, 2)}, ensure_ascii=False) + "\n")
            fh.flush()
    report(set_, model)


@app.command()
def report(set_: str = typer.Option("indicqa-sel", "--set"), model: str = "amin-3") -> None:
    rows = [json.loads(x) for x in (ROOT / "runs" / f"{set_}--{model.replace('/', '_')}.jsonl").read_text().splitlines()]
    secs = statistics.median(r["secs"] for r in rows)
    if set_.startswith("indicqa"):
        ans = [r for r in rows if r["gold"]]
        una = [r for r in rows if not r["gold"]]
        correct = [r for r in ans if not looks_like_refusal(r["reply"]) and recall(r["reply"], r["gold"]) >= 0.5]
        wrong_refusal = [r for r in ans if looks_like_refusal(r["reply"])]
        declined = [r for r in una if looks_like_refusal(r["reply"])]
        cited = [r for r in ans if not looks_like_refusal(r["reply"]) and re.search(r"\[S\d+\]", r["reply"])]
        in_ml = [r for r in rows if not looks_like_refusal(r["reply"]) and ml_ratio(r["reply"]) >= 0.6]
        answered = [r for r in rows if not looks_like_refusal(r["reply"])]
        typer.echo(
            f"{model} on {set_} (n={len(rows)}, p50 {secs:.1f}s)\n"
            f"  answerable correct (gold recall≥.5)  {len(correct)}/{len(ans)} = {len(correct)/max(len(ans),1):.1%}\n"
            f"  answerable wrongly refused   {len(wrong_refusal)}/{len(ans)}\n"
            f"  answerable cited             {len(cited)}/{max(len(ans)-len(wrong_refusal),1)}\n"
            f"  unanswerable declined        {len(declined)}/{len(una)} = {len(declined)/max(len(una),1):.1%}\n"
            f"  replies in Malayalam         {len(in_ml)}/{len(answered)}"
        )
    else:
        in_ml = [r for r in rows if ml_ratio(r["reply"]) >= 0.6]
        typer.echo(
            f"{model} on {set_} (n={len(rows)}, p50 {secs:.1f}s)\n"
            f"  replies in Malayalam  {len(in_ml)}/{len(rows)} = {len(in_ml)/len(rows):.1%}\n"
            f"  chrF vs human reply   {statistics.mean(chrf(r['reply'], r['gold']) for r in rows):.1f}"
        )


if __name__ == "__main__":
    app()
