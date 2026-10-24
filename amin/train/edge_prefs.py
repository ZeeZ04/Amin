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
    """The 27B on every prompt the student got wrong, plus the general ones (for balance pairs)."""
    p = _paths()
    todo = [r for r in _read(p["student"]) if not r["right"] or r["want"] == "answer"]
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
    student = {r["id"]: r for r in _read(p["student"])}
    teach = {r["id"]: r for r in _read(p["teacher"]) if r["right"]}
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
        part = [r for k, r in enumerate(rows_) if (k % 10 == 9) == (split == "valid")]
        (d / f"{split}.jsonl").write_text("".join(json.dumps({k: r[k] for k in ("system", "prompt", "chosen", "rejected")},
                                                             ensure_ascii=False) + "\n" for r in part), encoding="utf-8")
        typer.echo(f"{split}: {len(part)} pairs → {d / f'{split}.jsonl'}")
    typer.echo(f"mistake pairs {len(pairs)} (declines {declines}) · answer-side balance pairs {len(balance)}")


if __name__ == "__main__":
    app()
