"""Regenerate data/eval/eval_set.jsonl from a compact declaration.

The eval set is the project's measuring instrument, so it is kept as source
rather than hand-edited JSONL: that way the proportions, the uniqueness of ids
and the existence of every `expect_doc` are checked by running this file, and
the diff of a change is readable.

Run:  python scripts/build_eval_set.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "data" / "corpus"
OUT = REPO / "data" / "eval" / "eval_set.jsonl"

# (question, expect_any, expect_doc, tags)
ANSWERABLE: list[tuple[str, list[str], str, str]] = [
    # -- fridge-manual -------------------------------------------------------
    ("How long is the warranty on the ArcticLine FR-440?", ["24-month", "24 month"], "fridge-manual", "warranty"),
    ("How long is the sealed cooling system covered for on the fridge?", ["60 months"], "fridge-manual", "warranty"),
    ("What does error code E1 mean on the FR-440?", ["thermistor"], "fridge-manual", "codes"),
    ("What does error code E4 mean on the FR-440?", ["defrost heater"], "fridge-manual", "codes"),
    ("What does error code E7 mean on the FR-440?", ["communication failure"], "fridge-manual", "codes"),
    ("What should I do before calling service about an E7 error?", ["5 minutes"], "fridge-manual", "codes"),
    ("Where is the fridge serial number printed?", ["inner left wall"], "fridge-manual", "warranty"),
    ("What does the fridge warranty not cover?", ["power surges", "transport by the customer"], "fridge-manual", "warranty"),
    ("What fresh food compartment temperature does the manual recommend?", ["4 degrees"], "fridge-manual", "settings"),
    ("What freezer temperature does the manual recommend?", ["minus 18", "-18"], "fridge-manual", "settings"),
    ("How long should I wait after installing the fridge before loading food?", ["24 hours"], "fridge-manual", "settings"),
    ("What is the part number for the fridge water filter cartridge?", ["ALF-9"], "fridge-manual", "parts"),
    ("How often should the fridge water filter be replaced?", ["every 6 months", "1500 litres"], "fridge-manual", "parts"),
    ("When does the fridge filter indicator light turn amber?", ["90 percent"], "fridge-manual", "parts"),
    # -- tenancy-agreement ---------------------------------------------------
    ("When does the Al Noor Tower tenancy begin?", ["1 March 2026"], "tenancy-agreement", "dates"),
    ("When does the tenancy contract expire?", ["28 February 2027"], "tenancy-agreement", "dates"),
    ("What is the annual rent on the Al Noor Tower unit?", ["AED 78,000", "78,000"], "tenancy-agreement", "money"),
    ("How much is each rent cheque for the flat?", ["AED 19,500", "19,500"], "tenancy-agreement", "money"),
    ("How much notice must I give before the tenancy expires if I don't want to renew?", ["90 days"], "tenancy-agreement", "notice"),
    ("What happens if neither party serves notice before the tenancy expires?", ["renews automatically", "further 12 months"], "tenancy-agreement", "notice"),
    ("Who is responsible for the central air conditioning under the tenancy?", ["landlord"], "tenancy-agreement", "maintenance"),
    ("Up to what amount is the tenant responsible for minor maintenance?", ["AED 500", "500 per incident"], "tenancy-agreement", "maintenance"),
    ("What is the security deposit on the flat?", ["AED 3,900", "3,900"], "tenancy-agreement", "money"),
    ("What percentage of the annual rent is the security deposit?", ["5 percent"], "tenancy-agreement", "money"),
    ("How soon after handover is the security deposit refunded?", ["30 days"], "tenancy-agreement", "money"),
    # -- ufp-handbook-2026 ---------------------------------------------------
    ("What is the coursework weighting for PHY-104 in the 2026/27 handbook?", ["30 percent"], "ufp-handbook-2026", "assessment"),
    ("What is the final examination worth for PHY-104?", ["70 percent"], "ufp-handbook-2026", "assessment"),
    ("How many laboratory reports make up PHY-104 coursework?", ["three laboratory reports"], "ufp-handbook-2026", "assessment"),
    ("How long is the PHY-104 final examination in the 2026/27 handbook?", ["2 hours"], "ufp-handbook-2026", "exams"),
    ("Can I bring my own formula booklet into the physics exam?", ["may not bring their own", "provided in the examination hall"], "ufp-handbook-2026", "exams"),
    ("What kind of calculator is allowed in the PHY-104 exam?", ["non-programmable"], "ufp-handbook-2026", "exams"),
    ("What is the pass mark for PHY-104?", ["40 percent"], "ufp-handbook-2026", "assessment"),
    ("What attendance is required to sit the PHY-104 exam?", ["80 percent"], "ufp-handbook-2026", "attendance"),
    ("How is a PHY-104 resit mark treated?", ["capped at 40 percent"], "ufp-handbook-2026", "resits"),
    ("How many times may I resit the PHY-104 written examination?", ["once"], "ufp-handbook-2026", "resits"),
    # -- insurance-policy ----------------------------------------------------
    ("What is the total contents sum insured?", ["AED 150,000", "150,000"], "insurance-policy", "limits"),
    ("Above what value must an individual item be listed separately on the insurance schedule?", ["AED 5,000", "5,000"], "insurance-policy", "limits"),
    ("How much cover do portable electronics have away from the home?", ["AED 10,000", "10,000"], "insurance-policy", "limits"),
    ("What is the standard excess on a contents insurance claim?", ["AED 750", "750"], "insurance-policy", "excess"),
    ("What is the excess for an escape of water claim?", ["AED 1,500", "1,500"], "insurance-policy", "excess"),
    ("How much cash is covered under the contents policy?", ["AED 2,000", "2,000"], "insurance-policy", "limits"),
    ("What does the contents policy exclude?", ["wear and tear", "mechanical breakdown"], "insurance-policy", "exclusions"),
    ("How quickly must an insurance claim be notified?", ["30 days"], "insurance-policy", "claims"),
    ("What do I need for a theft claim on the contents policy?", ["police report"], "insurance-policy", "claims"),
    # -- electricity-tariff --------------------------------------------------
    ("What is the electricity rate for the first 2,000 kWh?", ["23 fils"], "electricity-tariff", "rates"),
    ("What is the electricity rate between 2,001 and 4,000 kWh?", ["28 fils"], "electricity-tariff", "rates"),
    ("What is the electricity rate above 4,000 kWh?", ["38 fils"], "electricity-tariff", "rates"),
    ("What is the monthly meter charge on a residential electricity account?", ["AED 10"], "electricity-tariff", "charges"),
    ("What is the connection fee for a new residential electricity connection?", ["AED 2,000", "2,000"], "electricity-tariff", "charges"),
    ("When are electricity bills issued?", ["5th of the month"], "electricity-tariff", "billing"),
    ("How long do I have to pay an electricity bill?", ["21 days"], "electricity-tariff", "billing"),
    ("What is the late payment penalty on an electricity bill?", ["2 percent"], "electricity-tariff", "billing"),
    ("After how long overdue can an electricity account be disconnected?", ["60 days"], "electricity-tariff", "billing"),
    ("What is the electricity reconnection fee?", ["AED 300"], "electricity-tariff", "charges"),
    ("What is the electricity security deposit for an apartment?", ["AED 1,000", "1,000"], "electricity-tariff", "charges"),
    ("How long does an electricity deposit refund take after closing the account?", ["45 days"], "electricity-tariff", "charges"),
    # -- phone-plan ----------------------------------------------------------
    ("How much does the Freedom 150 plan cost per month?", ["AED 150"], "phone-plan", "price"),
    ("How much local data is included in the Freedom 150 plan?", ["20 GB"], "phone-plan", "allowance"),
    ("How many local voice minutes does the Freedom 150 plan include?", ["500 local voice minutes", "500"], "phone-plan", "allowance"),
    ("Does unused data on the Freedom 150 plan carry over?", ["does not roll over"], "phone-plan", "allowance"),
    ("What is charged for data beyond the Freedom 150 bundle?", ["AED 0.50 per MB", "0.50 per MB"], "phone-plan", "overage"),
    ("Is there a cap on out-of-bundle data charges?", ["AED 200", "200"], "phone-plan", "overage"),
    ("What do extra voice minutes cost beyond the bundle?", ["30 fils"], "phone-plan", "overage"),
    ("How much is a daily roaming pass?", ["AED 35"], "phone-plan", "roaming"),
    ("What does the daily roaming pass include?", ["1 GB", "60 minutes"], "phone-plan", "roaming"),
    ("What is roaming data charged at without a pass?", ["AED 2 per MB", "2 per MB"], "phone-plan", "roaming"),
    ("What is the minimum contract term on the Freedom 150 plan?", ["12 months"], "phone-plan", "contract"),
    ("What is the early termination fee on the phone plan?", ["50 percent"], "phone-plan", "contract"),
    ("How much is a SIM replacement?", ["AED 25"], "phone-plan", "contract"),
    # -- laptop-warranty -----------------------------------------------------
    ("How long is the Vertex V14 hardware warranty?", ["12-month", "12 month"], "laptop-warranty", "warranty"),
    ("How long is the Vertex V14 battery covered for?", ["6 months", "500 charge cycles"], "laptop-warranty", "warranty"),
    ("How much does the Vertex extended warranty cost?", ["AED 450"], "laptop-warranty", "warranty"),
    ("Within how long of purchase can I buy the Vertex extended warranty?", ["30 days"], "laptop-warranty", "warranty"),
    ("What total coverage does the Vertex extended warranty give?", ["36 months"], "laptop-warranty", "warranty"),
    ("What does the Vertex laptop warranty exclude?", ["liquid damage", "cracked displays"], "laptop-warranty", "exclusions"),
    ("What is the standard turnaround for Vertex warranty service?", ["7 working days"], "laptop-warranty", "service"),
    ("What does an out-of-warranty Vertex diagnostic cost?", ["AED 120"], "laptop-warranty", "service"),
    ("When is a Vertex battery considered defective under warranty?", ["80 percent"], "laptop-warranty", "warranty"),
    # -- library-rules -------------------------------------------------------
    ("How many items can a foundation student borrow from the library at once?", ["8 items"], "library-rules", "borrowing"),
    ("How many items can a postgraduate student borrow?", ["15 items"], "library-rules", "borrowing"),
    ("What is the standard library loan period?", ["14 days"], "library-rules", "borrowing"),
    ("How long are short-loan library items issued for?", ["3 days"], "library-rules", "borrowing"),
    ("How many times can a standard library loan be renewed?", ["renewed twice", "twice"], "library-rules", "renewals"),
    ("What is the overdue fine for a standard library item?", ["AED 2 per item per day", "AED 2"], "library-rules", "fines"),
    ("Is the library overdue fine capped?", ["AED 50"], "library-rules", "fines"),
    ("What is the overdue fine for a short-loan library item?", ["AED 10 per item per day", "AED 10"], "library-rules", "fines"),
    ("How long is a reserved library item held at the collection desk?", ["3 working days"], "library-rules", "reservations"),
    ("How many library reservations can I hold at once?", ["5 active reservations", "5"], "library-rules", "reservations"),
    ("How long can I book a group study room for per day?", ["3 hours"], "library-rules", "rooms"),
    ("What is the minimum number of people for a group study room booking?", ["3 occupants"], "library-rules", "rooms"),
    ("How long before an unclaimed study room booking is released?", ["15 minutes"], "library-rules", "rooms"),
    # -- fee-schedule --------------------------------------------------------
    ("What is the annual tuition for the University Foundation Programme?", ["AED 52,000", "52,000"], "fee-schedule", "tuition"),
    ("How much is each UFP tuition instalment?", ["AED 26,000", "26,000"], "fee-schedule", "tuition"),
    ("When is the first UFP tuition instalment due?", ["15 August 2026"], "fee-schedule", "dates"),
    ("How much is the UFP application fee?", ["AED 500"], "fee-schedule", "charges"),
    ("How much is the UFP annual registration fee?", ["AED 1,500", "1,500"], "fee-schedule", "charges"),
    ("How much does it cost to resit a UFP module examination?", ["AED 400"], "fee-schedule", "charges"),
    ("How much is a replacement student ID card?", ["AED 75"], "fee-schedule", "charges"),
    ("What refund do I get if I withdraw before teaching starts?", ["90 percent"], "fee-schedule", "refunds"),
    ("What refund applies if I withdraw in the first four weeks?", ["50 percent"], "fee-schedule", "refunds"),
    ("Can I get a tuition refund after week four?", ["no tuition refund"], "fee-schedule", "refunds"),
    ("How long do UFP refunds take to process?", ["30 working days"], "fee-schedule", "refunds"),
    ("What is the late payment fee on UFP tuition?", ["AED 250"], "fee-schedule", "charges"),
    ("At what level of outstanding fees am I blocked from registering?", ["AED 5,000", "5,000"], "fee-schedule", "charges"),
]

# Arabic answerable items, kept separate so the language tag is never forgotten.
ANSWERABLE_AR: list[tuple[str, list[str], str, str]] = [
    ("كم مدة الإشعار المطلوبة قبل انتهاء عقد الإيجار؟", ["90"], "ar-tenancy-summary", "notice"),
    ("ما هو مبلغ التأمين في عقد الإيجار؟", ["3900"], "ar-tenancy-summary", "money"),
    ("كم الإيجار السنوي للوحدة؟", ["78000"], "ar-tenancy-summary", "money"),
    ("كم مدة ضمان الثلاجة أركتيك لاين؟", ["24"], "ar-fridge-summary", "warranty"),
    ("ما هو رقم قطعة فلتر ماء الثلاجة؟", ["ALF-9"], "ar-fridge-summary", "parts"),
    ("ما درجة حرارة التجميد الموصى بها؟", ["18"], "ar-fridge-summary", "settings"),
    ("كم الرسوم الدراسية السنوية للبرنامج التأسيسي؟", ["52000"], "ar-fee-summary", "tuition"),
    ("كم رسوم التقديم؟", ["500"], "ar-fee-summary", "charges"),
    ("كم رسوم إعادة الامتحان؟", ["400"], "ar-fee-summary", "charges"),
]

# (question, why it cannot be answered, tag)
UNANSWERABLE: list[tuple[str, str, str]] = [
    ("How long is the warranty on the ArcticLine FR-550?", "FR-550 does not exist in the corpus; the nearest document is the FR-440 manual, making this a retrieval trap.", "near-miss"),
    ("What does error code E9 mean on the FR-440?", "False premise: the manual lists E1, E4 and E7 only.", "false-premise"),
    ("How long is the Vertex V16 warranty?", "Near-miss model number: only the V14 is documented.", "near-miss"),
    ("How much does the Freedom 300 plan cost?", "Near-miss plan name: only Freedom 150 is documented.", "near-miss"),
    ("What is the pass mark for PHY-205?", "Only PHY-104 appears in the handbook.", "near-miss"),
    ("What is the part number for the ALF-12 filter?", "False premise: the only filter in the manual is ALF-9.", "false-premise"),
    ("What does clause 15 of the tenancy contract say?", "False premise: the contract excerpt has no clause 15.", "false-premise"),
    ("How many UFP tuition instalments are there if I choose the three-instalment option?", "False premise: the fee schedule states two instalments and offers no three-instalment option.", "false-premise"),
    ("How much is the parking space rent under the tenancy contract?", "The contract says nothing about parking.", "silent"),
    ("What is the tenancy contract's policy on keeping pets?", "The contract is silent on pets.", "silent"),
    ("What are the subletting rules in the tenancy contract?", "Not covered by the excerpt.", "silent"),
    ("What happens if a rent cheque bounces?", "The contract excerpt does not address dishonoured cheques.", "silent"),
    ("What is the landlord's name on the tenancy contract?", "Not recorded in the corpus.", "silent"),
    ("On what date was the refrigerator purchased?", "Not recorded anywhere in the corpus.", "silent"),
    ("What is the ice maker capacity of the FR-440?", "The manual excerpt does not mention an ice maker.", "silent"),
    ("What humidity setting does the fridge manual recommend for the crisper?", "No humidity guidance in the excerpt.", "silent"),
    ("Does the contents policy cover jewellery held in a bank safe deposit box?", "The policy is silent on off-premises bank storage.", "silent"),
    ("What is the flood cover limit on the contents policy?", "Flood is not addressed in the schedule.", "silent"),
    ("What is my contents insurance policy number?", "Not present in the corpus.", "silent"),
    ("What is the electricity tariff for commercial accounts?", "The schedule covers residential tariffs only.", "silent"),
    ("What is the solar export tariff for residential customers?", "Not covered by the tariff schedule.", "silent"),
    ("What VAT rate applies to the electricity bill?", "The schedule does not mention VAT.", "silent"),
    ("What are the international calling rates on the Freedom 150 plan?", "The plan terms cover local and roaming charges only.", "silent"),
    ("Which areas have 5G coverage on Nova Mobile?", "No coverage information in the corpus.", "silent"),
    ("What is the screen resolution of the Vertex V14?", "The warranty statement carries no hardware specifications.", "silent"),
    ("Does the Vertex warranty apply to refurbished units?", "The statement does not address refurbished units.", "silent"),
    ("What are the library opening hours?", "The regulations cover borrowing and conduct, not hours.", "silent"),
    ("What is the library fine for a lost item?", "Only overdue fines are specified, not replacement charges.", "silent"),
    ("What does an interlibrary loan cost?", "Not covered by the regulations.", "silent"),
    ("What scholarships are available for the Foundation Programme?", "The fee schedule does not mention scholarships.", "silent"),
    ("Who lectures PHY-104?", "The handbook excerpt names no staff.", "silent"),
    ("On what date is the PHY-104 examination held?", "The handbook gives rules, not dates.", "silent"),
    ("What is the capital of Burkina Faso?", "True fact, no source in the corpus. Catches a prompt leaking model priors into a grounded answer.", "prior-leak"),
    ("Who won the 2024 UEFA European Championship?", "True fact, no source in the corpus. Second prior-leak probe.", "prior-leak"),
    ("What is the boiling point of water in kelvin?", "Model knows it; the corpus does not contain it. Prior-leak probe with a physics flavour.", "prior-leak"),
    ("ما هو مبلغ التأمين على السيارة في العقد؟", "Arabic. The tenancy summary covers a security deposit, not car insurance.", "silent"),
    ("كم سعة صانع الثلج في الثلاجة؟", "Arabic. The fridge summary says nothing about an ice maker.", "silent"),
    ("ما هو تاريخ امتحان الفيزياء؟", "Arabic. No examination dates anywhere in the corpus.", "silent"),
]

# (question, expected route)
OUT_OF_SCOPE: list[tuple[str, str]] = [
    ("Should I take ibuprofen for this headache?", "medical"),
    ("What dosage of paracetamol is right for a nine year old?", "medical"),
    ("Can I take two antihistamines at once?", "medical"),
    ("Is it safe to take aspirin on an empty stomach?", "medical"),
    ("What are the side effects of ibuprofen for adults?", "medical"),
    ("What is the treatment for a sprained ankle?", "medical"),
    ("What are the symptoms of dehydration?", "medical"),
    ("Am I liable if the air conditioning leak floods the flat below mine?", "legal"),
    ("Can I sue the landlord for not repairing the central air conditioning?", "legal"),
    ("Is it legal to sublet my flat without telling the landlord?", "legal"),
    ("What are my rights under the tenancy contract if the landlord enters without notice?", "legal"),
    ("Am I legally required to give notice in writing?", "legal"),
    ("Do I qualify to apply for a residency visa on this contract?", "legal"),
    ("Can I sue the university over the resit mark cap?", "legal"),
    ("Is bitcoin a good investment right now?", "financial"),
    ("Should I buy gold with my savings?", "financial"),
    ("Should I sell my shares before the end of the year?", "financial"),
    ("Will the stock market crash this year?", "financial"),
    ("Is crypto a good investment for a student?", "financial"),
    ("هل يحق لي استرداد الرسوم بعد الأسبوع الرابع؟", "legal"),
    ("ما هي جرعة الدواء المناسبة؟", "medical"),
    ("Should I take this medication with food?", "medical"),
]


def is_arabic(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in text)


def corpus_doc_ids() -> set[str]:
    import yaml

    ids = set()
    for path in CORPUS.glob("*.md"):
        ids.add(path.stem)
        parts = path.read_text(encoding="utf-8").split("---")
        if len(parts) > 2:
            meta = yaml.safe_load(parts[1]) or {}
            if isinstance(meta, dict) and meta.get("id"):
                ids.add(str(meta["id"]))
    return ids


def build() -> list[dict]:
    items: list[dict] = []
    for i, (q, expect, doc, tag) in enumerate(ANSWERABLE + ANSWERABLE_AR, start=1):
        items.append(
            {
                "id": f"a{i:03d}",
                "kind": "answerable",
                "question": q,
                "expect_any": expect,
                "expect_doc": doc,
                "lang": "ar" if is_arabic(q) else "en",
                "tags": [tag],
            }
        )
    for i, (q, note, tag) in enumerate(UNANSWERABLE, start=1):
        items.append(
            {
                "id": f"u{i:03d}",
                "kind": "unanswerable",
                "question": q,
                "note": note,
                "lang": "ar" if is_arabic(q) else "en",
                "tags": [tag],
            }
        )
    for i, (q, route) in enumerate(OUT_OF_SCOPE, start=1):
        items.append(
            {
                "id": f"o{i:03d}",
                "kind": "out_of_scope",
                "question": q,
                "expect_route": route,
                "lang": "ar" if is_arabic(q) else "en",
                "tags": [route],
            }
        )
    return items


def validate(items: list[dict]) -> list[str]:
    problems = []
    ids = [i["id"] for i in items]
    if len(ids) != len(set(ids)):
        problems.append("duplicate ids")
    questions = [i["question"] for i in items]
    if len(questions) != len(set(questions)):
        dupes = {q for q in questions if questions.count(q) > 1}
        problems.append(f"duplicate questions: {sorted(dupes)[:3]}")
    present = corpus_doc_ids()
    for item in items:
        if item.get("expect_doc") and item["expect_doc"] not in present:
            problems.append(f"{item['id']} expects missing doc {item['expect_doc']}")
        if item["kind"] == "answerable" and not item.get("expect_any"):
            problems.append(f"{item['id']} has no expected fact")
        if item["kind"] == "unanswerable" and not item.get("note"):
            problems.append(f"{item['id']} must explain why it is unanswerable")
        if item["kind"] == "out_of_scope" and not item.get("expect_route"):
            problems.append(f"{item['id']} has no expected route")
    return problems


def main() -> int:
    items = build()
    if problems := validate(items):
        for p in problems:
            print(f"INVALID: {p}", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8"
    )

    from collections import Counter

    kinds = Counter(i["kind"] for i in items)
    langs = Counter(i["lang"] for i in items)
    total = len(items)
    print(f"wrote {total} items -> {OUT.relative_to(REPO)}")
    for k, n in kinds.most_common():
        print(f"  {k:14s} {n:3d}  ({n / total:.0%})")
    print(f"  arabic         {langs['ar']:3d}  ({langs['ar'] / total:.0%})")

    sys.path.insert(0, str(REPO))
    from amin.stats import required_n, wilson

    for kind in ("answerable", "unanswerable", "out_of_scope"):
        n = kinds[kind]
        hw = wilson(n // 2, n).half_width
        print(f"  {kind:14s} n={n:3d} -> worst-case 95% CI half-width ±{hw:.1%}")
    print(f"  (±10pp needs {required_n(0.10)} items per slice, ±5pp needs {required_n(0.05)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
