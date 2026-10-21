"""General-chat examples for amin-2's SFT (ADR-013, TRAINING.md round 2).

Every round-1 example used ANSWER_SYSTEM, so a LoRA trained only on them can
erode what the base model does well under GENERAL_SYSTEM. These questions are
answered by the teacher under the general prompt and mixed into the SFT set:

    general   everyday knowledge, answered        (kept unless the teacher declined)
    personal  the user's own details, no document (kept only if the teacher declined)

The teacher's answers are not graded for truth (there is no answer key), so
this is plain distillation of a skill the teacher already has. The bank is
checked against every eval set, by exact question and by shared 6-gram.

    uv run python -m amin.train.general run       # teacher pass, resumable
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import typer
from rich.console import Console

from ..config import settings
from ..prompts import GENERAL_SYSTEM, general_prompt, looks_like_refusal
from ..providers import get_provider

app = typer.Typer(add_completion=False, help="General-chat SFT examples.")
console = Console()


@app.callback()
def _main() -> None:
    """General-chat SFT examples (subcommands keep `run` explicit, like distill)."""

GENERAL_EN = """
How does a refrigerator keep food cold?
Why is the sky blue?
What causes the seasons on Earth?
How do vaccines train the immune system?
What is the difference between weather and climate?
How does a credit score work in general?
What is compound interest? Give a short example.
Explain what inflation means in simple terms.
What does a VPN do?
How do I make a strong password I can remember?
What is the difference between RAM and storage on a computer?
How does GPS work?
What is machine learning, in two sentences?
Write a Python function that reverses a string.
What does HTTP 404 mean?
What is the difference between a list and a tuple in Python?
How do I convert Celsius to Fahrenheit?
What is 15 percent of 240?
If a train travels 180 km in 2 hours, what is its average speed?
What is the Pythagorean theorem?
How many seconds are in an hour?
What is a prime number? Give three examples.
Who was the first woman to win a Nobel Prize?
When did the First World War begin?
Who built the pyramids of Giza?
What was the Silk Road?
Who invented the telephone?
What is the Great Barrier Reef?
Which is the longest river in Africa?
What is the capital of Japan?
What is the capital of Kenya?
Which ocean lies between Africa and Australia?
What are the seven emirates of the UAE?
What is the tallest building in the world?
What language is spoken in Argentina?
How do I boil an egg so the yolk stays soft?
How long should rice be cooked?
What is a good way to store fresh herbs?
How can I remove a coffee stain from a shirt?
How often should I change a car's engine oil, generally?
What is the difference between a debit card and a credit card?
How do solar panels produce electricity?
Why do we have leap years?
What is photosynthesis?
How do bees make honey?
What is the boiling point of water at sea level in Celsius?
What is the chemical formula for water?
How far is the Moon from the Earth, roughly?
How many planets are in the solar system?
What is a black hole?
What is DNA?
What does a thermostat do?
How do I write a polite email asking for a deadline extension?
Summarise what a tenancy contract usually covers.
What is the difference between a warranty and a guarantee?
What should I check before signing a phone contract?
What is a security deposit on a rental?
How do noise-cancelling headphones work?
What is the difference between AC and DC electricity?
Why does ice float on water?
How does a microwave oven heat food?
What is the internet, in simple terms?
What is cloud storage?
What is two-factor authentication?
How do I take a screenshot on a Mac?
What is a spreadsheet formula to add up a column?
Explain recursion with a simple example.
What is the speed of sound in air, roughly?
What is the largest planet in the solar system?
What is the smallest country in the world?
Who wrote Pride and Prejudice?
Who composed the Four Seasons?
What is the main ingredient in hummus?
What is Ramadan?
What is Eid al-Fitr?
What is the difference between a virus and a bacterium?
How much water should an adult drink a day, generally?
What is a healthy amount of sleep for an adult?
Translate "good morning" into Arabic.
Translate "thank you very much" into French.
What does the word "Amin" mean in Arabic?
Give me three tips for saving electricity at home.
How can I lower my water bill?
What is a budget, and how do I start one?
What is the 50/30/20 budgeting rule?
What is the difference between gross and net salary?
How do I calculate a monthly payment from an annual amount?
How many days are in a year, and in a leap year?
What time zone is the UAE in?
What is the population of the world, roughly?
What is a desert?
Why does the Gulf get so humid in summer?
How do air conditioners cool a room?
What is the best way to clean an air conditioner filter?
What is a hybrid car?
How does an electric car battery charge?
What is the difference between a lease and a licence?
What does "force majeure" mean?
What is a notarised document?
What is an invoice?
What is the difference between a receipt and an invoice?
How do I read an electricity meter, in general?
What is kWh?
Explain what a kilowatt-hour measures.
What is the difference between a will and a trust, in general terms?
""".strip().splitlines()

GENERAL_AR = """
لماذا السماء زرقاء؟
كيف تعمل الثلاجة؟
ما هو التضخم بكلمات بسيطة؟
ما الفرق بين الطقس والمناخ؟
كم عدد إمارات دولة الإمارات وما أسماؤها؟
ما هي عاصمة اليابان؟
ما هي عاصمة مصر؟
من مخترع الهاتف؟
ما هو التمثيل الضوئي؟
كيف أحفظ الأعشاب الطازجة؟
كيف أسلق بيضة؟
ما هو شهر رمضان؟
ما هو عيد الفطر؟
كيف أوفر الكهرباء في المنزل؟
ما معنى كلمة أمين؟
ما الفرق بين بطاقة الخصم وبطاقة الائتمان؟
ما هي الفائدة المركبة؟
كيف تعمل الألواح الشمسية؟
ما هو الكيلوواط ساعة؟
ما هي المنطقة الزمنية لدولة الإمارات؟
كيف يعمل المكيف؟
ما هو التأمين على الإيجار؟
كيف أكتب رسالة بريد إلكتروني رسمية؟
ما هي السنة الكبيسة؟
""".strip().splitlines()

PERSONAL_EN = """
What is my landlord's phone number?
When does my car insurance renew?
How much did I pay for electricity last month?
What is my Emirates ID number?
Which school does my daughter go to?
What is my gym membership number?
When is my next rent cheque due?
What is the serial number of my washing machine?
How much is my internet bill?
What did my doctor say at my last appointment?
What is the PIN for my electricity account?
When does my passport expire?
How much is left on my car loan?
What is my policy number for home insurance?
What is my employer's address?
""".strip().splitlines()

PERSONAL_AR = """
ما رقم هاتف المالك؟
متى يتجدد تأمين سيارتي؟
كم دفعت للكهرباء الشهر الماضي؟
ما رقم هويتي الإماراتية؟
متى موعد شيك الإيجار القادم؟
متى تنتهي صلاحية جواز سفري؟
""".strip().splitlines()


def bank() -> list[dict]:
    rows = []
    for kind, lang, qs in (("general", "en", GENERAL_EN), ("general", "ar", GENERAL_AR),
                           ("personal", "en", PERSONAL_EN), ("personal", "ar", PERSONAL_AR)):
        for q in qs:
            q = q.strip()
            if q:
                rows.append({"id": f"g-{len(rows) + 1:04d}", "kind": kind, "lang": lang, "question": q})
    return rows


def _grams(q: str, n: int = 6) -> set[tuple[str, ...]]:
    w = re.findall(r"\w+", q.lower())
    return {tuple(w[i : i + n]) for i in range(len(w) - n + 1)}


def _norm(q: str) -> str:
    return " ".join(re.findall(r"\w+", q.lower()))


def overlaps(rows: list[dict], eval_files: list[Path]) -> list[str]:
    """Questions in `rows` that repeat, or share a 6-gram with, any eval question."""
    qs = []
    for f in eval_files:
        if f.exists():
            qs += [json.loads(line)["question"] for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
    exact = {_norm(q) for q in qs}
    grams = set().union(*(_grams(q) for q in qs)) if qs else set()
    return [r["question"] for r in rows if _norm(r["question"]) in exact or _grams(r["question"]) & grams]


def out_path() -> Path:
    return settings.train_path / "general.jsonl"


@app.command()
def run(provider: str = typer.Option(None), exclude: list[Path] = typer.Option([], help="Extra eval files to keep clear of.")):
    """Teacher answers under GENERAL_SYSTEM. Overlapping questions are dropped first."""
    rows = bank()
    bad = set(overlaps(rows, [settings.eval_set, *exclude]))
    if bad:
        console.print(f"[yellow]dropping {len(bad)} that overlap an eval set: {sorted(bad)[:5]}[/yellow]")
    rows = [r for r in rows if r["question"] not in bad]
    out = out_path()
    done = {json.loads(x)["id"] for x in out.read_text().splitlines()} if out.exists() else set()
    prov = get_provider(provider)
    kept = 0
    with out.open("a", encoding="utf-8") as fh:
        for r in rows:
            if r["id"] in done:
                continue
            prompt = general_prompt(r["question"], searched=r["kind"] == "personal")
            reply = prov.complete(prompt, system=GENERAL_SYSTEM).strip()
            declined = looks_like_refusal(reply)
            ok = bool(reply) and (declined if r["kind"] == "personal" else not declined)
            kept += ok
            fh.write(json.dumps({**r, "prompt": prompt, "response": reply, "kept": ok}, ensure_ascii=False) + "\n")
            fh.flush()
    console.print(f"[green]done[/green]: kept {kept} of {len(rows) - len(done)} new")


def fallback_path() -> Path:
    return settings.train_path / "fallback.jsonl"


@app.command()
def fallback(
    provider: str = typer.Option(None),
    declines: int = typer.Option(600, help="Cap on decline examples (3:1 against answers)."),
    seed: int = typer.Option(3),
):
    """amin-3 (E29): the hybrid fallback prompt, after documents were searched.

    In the app, a general answer with `searched=True` follows a document
    search that found nothing. amin-2 hedged there ("it depends on your
    provider") where the teacher declined. This teaches the line between
    them: training unanswerables about the user's documents -> decline,
    genuine general questions asked inside a project -> answer.
    """
    import random

    items = [json.loads(x) for x in (settings.train_path / "items.jsonl").read_text(encoding="utf-8").splitlines()]
    unans = [i for i in items if i["kind"] == "unanswerable"]
    decline = [i for i in unans if "general" not in i.get("tags", [])]
    answer = [i for i in unans if "general" in i.get("tags", [])]
    answer += [{"id": r["id"] + "-s", "question": r["question"], "lang": r["lang"], "split": "train"}
               for r in bank() if r["kind"] == "general"]
    rng = random.Random(seed)
    rng.shuffle(decline)
    rows = [dict(i, want="decline") for i in decline[:declines]] + [dict(i, want="answer") for i in answer]
    out = fallback_path()
    done = {json.loads(x)["id"] for x in out.read_text().splitlines()} if out.exists() else set()
    prov = get_provider(provider)
    kept = n = 0
    with out.open("a", encoding="utf-8") as fh:
        for r in rows:
            if r["id"] in done:
                continue
            prompt = general_prompt(r["question"], searched=True)
            reply = prov.complete(prompt, system=GENERAL_SYSTEM).strip()
            declined = looks_like_refusal(reply)
            ok = bool(reply) and (declined if r["want"] == "decline" else not declined)
            kept += ok
            n += 1
            fh.write(json.dumps({"id": r["id"], "split": r.get("split", "train"), "want": r["want"],
                                 "question": r["question"], "prompt": prompt, "response": reply, "kept": ok},
                                ensure_ascii=False) + "\n")
            fh.flush()
    console.print(f"[green]done[/green]: kept {kept} of {n} new")


def examples() -> list[dict]:
    """Kept rows (general bank + fallback) as chat examples for distill.export."""
    rows = []
    for out in (out_path(), fallback_path()):
        if out.exists():
            rows += [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [
        {"messages": [{"role": "system", "content": GENERAL_SYSTEM}, {"role": "user", "content": r["prompt"]},
                      {"role": "assistant", "content": r["response"]}]}
        for r in rows if r["kept"]
    ]


if __name__ == "__main__":
    app()
