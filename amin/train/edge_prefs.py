"""Round 2 for the edge student (E38): preference pairs on the fallback decline.

E35's gate failed on one behaviour: 24 of edge-1's 26 main-set unanswerable
failures were general answers to questions about the user's own documents,
some with invented specifics ("three slabs above 5,000 kWh"). The fallback
prompt (`general_prompt(searched=True)`) tells the model to decline those;
edge-1 learnt it from 795 SFT examples, about 40% of which it had seen by its
step-1000 checkpoint.

    sample   the student answers every training unanswerable the SFT fallback
             set did not use (1,564, 235 of them Malayalam) plus the general
             questions it must still answer, under the fallback prompt
    teacher  the 27B answers the prompts the student got wrong. Only its
             declines (for document questions) or its answers (for general
             ones) become `chosen`
    export   DPO pairs in mlx_lm_lora's format: chosen = the right behaviour,
             rejected = the student's own reply. Each decline pair is matched
             by an answer-side pair (a correct general answer chosen over a
             refusal), so the model learns the line, not a lean (TRAINING.md
             round 2)

    AMIN_MLX_HOST=http://127.0.0.1:8081 uv run python -m amin.train.edge_prefs sample
    uv run python -m amin.train.edge_prefs teacher
    uv run python -m amin.train.edge_prefs export
"""

from __future__ import annotations

import json
import random

import typer

from ..config import settings
from ..prompts import GENERAL_SYSTEM, general_prompt, looks_like_refusal
from ..providers import MLXProvider, OllamaProvider
from .general import bank

app = typer.Typer(add_completion=False, help="Edge round 2: fallback-decline preference pairs.")


@app.callback()
def _main() -> None:
    """Edge round 2: fallback-decline preference pairs."""


def _paths() -> dict:
    root = settings.train_path
    return {"student": root / "edge_fallback.jsonl", "teacher": root / "edge_fallback_teacher.jsonl",
            "dpo": root / "dpo-edge"}


def _read(path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def rows() -> list[dict]:
    items = [json.loads(x) for x in (settings.train_path / "items.jsonl").read_text(encoding="utf-8").splitlines()]
    used = {r["id"] for r in _read(settings.train_path / "fallback.jsonl")}
    out = []
    for i in items:
        if i["kind"] != "unanswerable" or i["id"] in used:
            continue
        want = "answer" if "general" in i.get("tags", []) else "decline"
        out.append({"id": i["id"], "question": i["question"], "lang": i["lang"], "split": i["split"], "want": want})
    # General questions asked inside a document space: these must still be answered.
    out += [{"id": r["id"] + "-e", "question": r["question"], "lang": r.get("lang", "en"), "split": "train",
             "want": "answer" if r["kind"] == "general" else "decline"}
            for r in bank() if r["id"] + "-s" not in used]
    # Answer-side anchors for balance pairs: general questions asked inside a
    # document space must still be answered, in every language. The bank was
    # all used by round-1 SFT, so it is reused here as anchors only, with
    # Malayalam native-speaker questions (amin.train.malayalam) alongside.
    out += [{"id": r["id"] + "-b", "question": r["question"], "lang": r.get("lang", "en"), "split": "train",
             "want": "answer"} for r in bank() if r["kind"] == "general"]
    ml = settings.train_path / "ml_general.jsonl"
    if ml.exists():
        qs = [json.loads(x)["messages"][1]["content"] for x in ml.read_text(encoding="utf-8").splitlines()
              if '"source": "aya"' in x]
        out += [{"id": f"aya-b{k}", "question": q, "lang": "ml", "split": "valid" if k % 10 == 9 else "train",
                 "want": "answer"} for k, q in enumerate(qs[:150]) if len(q) < 400]
    return out


def _right(reply: str, want: str) -> bool:
    declined = looks_like_refusal(reply)
    return bool(reply.strip()) and (declined if want == "decline" else not declined)


def _run(provider, target, todo: list[dict]) -> int:
    done = {r["id"] for r in _read(target)}
    n = 0
    with target.open("a", encoding="utf-8") as fh:
        for r in todo:
            if r["id"] in done:
                continue
            prompt = general_prompt(r["question"], searched=True)
            reply = provider.complete(prompt, system=GENERAL_SYSTEM).strip()
            fh.write(json.dumps({**r, "prompt": prompt, "reply": reply, "right": _right(reply, r["want"])},
                                ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
    return n


@app.command()
def sample() -> None:
    """The student (on settings.mlx_host) under the fallback prompt."""
    p = _paths()
    n = _run(MLXProvider(), p["student"], rows())
    got = _read(p["student"])
    wrong = [r for r in got if not r["right"]]
    typer.echo(f"sampled {n} new · {len(wrong)}/{len(got)} wrong "
               f"(decline missed {sum(r['want'] == 'decline' for r in wrong)}, "
               f"answer missed {sum(r['want'] == 'answer' for r in wrong)})")


@app.command()
def teacher() -> None:
    """The 27B on every prompt the student got wrong."""
    p = _paths()
    # Only the student's mistakes need the teacher; its right general answers anchor the balance pairs.
    todo = [r for r in _read(p["student"]) if not _right(r["reply"], r["want"])]
    n = _run(OllamaProvider(), p["teacher"], todo)
    got = _read(p["teacher"])
    typer.echo(f"teacher: {n} new · right on {sum(r['right'] for r in got)}/{len(got)}")


REFUSAL = {
    "en": "Your documents don't cover this, so I can't answer it from them.",
    "ar": "لا تغطي مستنداتك هذا السؤال، لذلك لا يمكنني الإجابة عنه منها.",
    "ml": "നിങ്ങളുടെ രേഖകളിൽ ഇതിനെക്കുറിച്ച് ഒന്നും പറയുന്നില്ല, അതിനാൽ അവയിൽ നിന്ന് ഉത്തരം നൽകാൻ കഴിയില്ല.",
}


@app.command()
def export(seed: int = 0) -> None:
    p = _paths()
    # Re-grade from the replies, not the stored flag: the refusal markers
    # change (E38 added Malayalam), and a stale flag would mislabel pairs.
    student = {r["id"]: {**r, "right": _right(r["reply"], r["want"])} for r in _read(p["student"])}
    teach = {r["id"]: r for r in _read(p["teacher"]) if _right(r["reply"], r["want"])}
    pairs, balance = [], []
    for i, s in student.items():
        t = teach.get(i)
        if not s["right"] and t:  # the student's own mistake, against the teacher's right reply
            pairs.append({"system": GENERAL_SYSTEM, "prompt": s["prompt"], "chosen": t["reply"],
                          "rejected": s["reply"], "split": s["split"], "lang": s["lang"]})
        if s["want"] == "answer" and (good := t or (s if s["right"] else None)):
            # The line has two sides: a right general answer is preferred to declining it.
            balance.append({"system": GENERAL_SYSTEM, "prompt": s["prompt"], "chosen": good["reply"],
                            "rejected": REFUSAL.get(s["lang"], REFUSAL["en"]), "split": s["split"], "lang": s["lang"]})
    rng = random.Random(seed)
    declines = sum(1 for x in pairs if looks_like_refusal(x["chosen"]))
    rows_ = pairs + balance
    rng.shuffle(rows_)
    d = p["dpo"]
    d.mkdir(parents=True, exist_ok=True)
    for split in ("train", "valid"):
        part = [r for r in rows_ if (r["split"] == "valid") == (split == "valid")]
        (d / f"{split}.jsonl").write_text("".join(json.dumps({k: r[k] for k in ("system", "prompt", "chosen", "rejected")},
                                                             ensure_ascii=False) + "\n" for r in part), encoding="utf-8")
        typer.echo(f"{split}: {len(part)} pairs → {d / f'{split}.jsonl'}")
    typer.echo(f"mistake pairs {len(pairs)} (declines {declines}) · answer-side balance pairs {len(balance)}")


if __name__ == "__main__":
    app()


@app.command()
def probe(label: str = typer.Option(..., help="Name for this run, e.g. edge-2-100")) -> None:
    """Held-out fallback check (valid-split rows) on the model at settings.mlx_host, per language.

    The main bench is English-heavy and cannot see E38's failure: Malayalam
    questions about the user's own documents answered with invented details."""
    out = settings.train_path / f"edge_probe-{label}.jsonl"
    held = [r for r in rows() if r["split"] == "valid"]
    _run(MLXProvider(), out, held)
    got = _read(out)
    from collections import defaultdict

    tally: dict = defaultdict(lambda: [0, 0])
    for r in got:
        key = (r["want"], r["lang"])
        tally[key][0] += _right(r["reply"], r["want"])
        tally[key][1] += 1
    typer.echo(f"{label}: " + " · ".join(f"{w} {lang} {a}/{n}" for (w, lang), (a, n) in sorted(tally.items())))
