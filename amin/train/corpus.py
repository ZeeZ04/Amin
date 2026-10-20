"""A synthetic training corpus, disjoint from the eval set.

The eval set is the measuring instrument; training on it, or on anything that
shares its documents, would make every number after this point a measurement
of memory. So the training corpus is generated here from its own templates,
with its own fictional names and freshly drawn numbers, and
`tests/test_train.py` checks the separation instead of trusting it.

Documents are grouped into households, each with at most one document of a
kind (one tenancy, one car, one school's fees...), and each household gets its
own index - about the size of the eval corpus. One index holding sixty tenancy
contracts would be unanswerable by design: a contract's rent clause does not
repeat its unit number, so nothing tells sixty rent clauses apart.

Every document is rendered from a set of facts, so every question about it has
a known answer and a known source. That is what lets `evaluate.grade()` judge
the teacher's output without a human in the loop.

Out-of-scope routing and live-source conflicts are decided in code before the
model is called (covenant.py, conflict.py, ADR-009), so they would yield no
training examples and are not generated. Version skew is: the model answers
from the live passages, and the superseded document is a distractor in the index.

Run:  uv run python scripts/build_train_corpus.py
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

VALID_EVERY = 10  # every 10th document, and all its questions, is held out
_EASTERN = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
_MONTHS = "January February March April May June July August September October November December".split()
_MONTHS_AR = "يناير فبراير مارس أبريل مايو يونيو يوليو أغسطس سبتمبر أكتوبر نوفمبر ديسمبر".split()


@dataclass
class Fact:
    questions: list[str]
    expect: list[str]
    tag: str


@dataclass
class Doc:
    doc_id: str
    title: str
    lang: str
    about: str
    sections: list[tuple[str, str]]
    facts: list[Fact]
    # Questions the document invites but does not answer: (question, why) or
    # (question, why, probe) where probe must appear in no document at all.
    absent: list[tuple] = field(default_factory=list)
    status: str = ""
    tier: str = "primary"
    split: str = "train"
    # What makes this document unique within its family; every question names it.
    key: str = ""
    # Which household's library it belongs to. A household holds at most one
    # document of each family, as a real one does; each is indexed on its own.
    household: int = 0
    # False-premise questions: they assert a figure the document contradicts.
    premises: list[tuple[str, str]] = field(default_factory=list)
    # Adjacent-fact traps: (question, why unanswerable, sibling question the
    # document does answer, its expected facts). The nearest passage holds a
    # related figure; the right reply is a refusal, and the sibling is there
    # so a model cannot pass by refusing everything that looks like it.
    traps: list[tuple[str, str, str, list[str]]] = field(default_factory=list)

    def markdown(self) -> str:
        meta = [
            "---",
            f"id: {self.doc_id}",
            f"title: {self.title}",
            f"tier: {self.tier}",
            f"lang: {self.lang}",
            f"about: {self.about}",
        ]
        if self.status:
            meta.append(f"status: {self.status}")
        meta += ["note: Synthetic training document (amin/train/corpus.py). Not part of the eval.", "---", ""]
        body = "\n\n".join(f"# {h}\n\n{t}" for h, t in self.sections)
        return "\n".join(meta) + body + "\n"


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------


def money(n: int) -> str:
    return f"{n:,}"


def money_expect(n: int, lang: str = "en") -> list[str]:
    out = [money(n)]
    if lang == "ar":
        out.append(str(n).translate(_EASTERN))
    return out


def en_date(d: date) -> str:
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def ar_date(d: date) -> str:
    return f"{d.day} {_MONTHS_AR[d.month - 1]} {d.year}"


def ar_date_expect(d: date) -> list[str]:
    m = _MONTHS_AR[d.month - 1]
    return [f"{m} {d.year}", f"{m} {str(d.year).translate(_EASTERN)}"]


def days_expect(n: int, lang: str = "en") -> list[str]:
    if lang == "ar":
        return [f"{n} يوم", f"{str(n).translate(_EASTERN)} يوم"]
    return [f"{n} days", f"{n}-day"]


# ---------------------------------------------------------------------------
# names — fictional, and deliberately disjoint from data/corpus
# ---------------------------------------------------------------------------

BUILDINGS = [
    "Palm Grove Residences", "Marina Crest", "Sahara Heights", "Corniche View", "Al Waha Court",
    "Desert Rose Tower", "Creekside Lofts", "Jasmine Gardens", "Pearl Bay Apartments", "Saffron Court",
    "Lagoon Terraces", "Falcon Ridge", "Coral Sands Tower", "Olive Grove Villas", "Seaview Plaza",
]
BUILDINGS_AR = ["برج الياسمين", "أبراج الواحة", "برج اللؤلؤ", "مساكن النخيل", "برج الصقر", "أبراج المرجان"]
PEOPLE = [
    "Khalid Al Mansoori", "Fatima Rahman", "Omar Haddad", "Mariam Saeed", "Rashid Al Ketbi",
    "Layla Nasser", "Yousef Darwish", "Aisha Karim", "Hamad Al Suwaidi", "Noura Bakr",
]
PEOPLE_AR = ["خالد المنصوري", "فاطمة رحمن", "عمر حداد", "مريم سعيد", "راشد الكتبي", "ليلى ناصر"]
UTILITIES = ["Gulf Coast Power & Water", "Oasis Energy Services", "Northern Emirates Utilities", "Dunes Power Company"]
UTILITIES_AR = ["شركة الساحل للكهرباء والماء", "طاقة الواحة", "مرافق الإمارات الشمالية"]
SCHOOLS = ["Greenfield International School", "Bayside British Academy", "Crescent Primary School",
           "Horizon American School", "Al Rawda Bilingual School", "Silver Palm Academy"]
SCHOOLS_AR = ["مدرسة الروضة ثنائية اللغة", "أكاديمية الأفق", "مدرسة الهلال الابتدائية", "مدرسة النخلة الفضية"]
GYMS = ["IronPeak Fitness", "Pulse Gym", "Oasis Wellness Club", "CoreFit Studio", "Summit Athletics"]
TELCOS = ["Skyline Telecom", "Wavelink", "Mirage Mobile", "FalconNet"]
BRANDS = [("Kelvora", "WM"), ("Brisa", "AC"), ("Torvik", "DW"), ("Halvo", "OV"), ("Zentra", "TV")]
APPLIANCES = {"WM": "washing machine", "AC": "split air conditioner", "DW": "dishwasher",
              "OV": "built-in oven", "TV": "television"}
CARS = [("Toyota", "Corolla"), ("Nissan", "Patrol"), ("Hyundai", "Tucson"), ("Kia", "Sportage"),
        ("Mitsubishi", "Pajero"), ("Honda", "Accord")]
INSURERS = ["Crescent Insurance", "Shield Gulf Insurance", "Anchor Mutual", "Palm Assurance"]
SERVICERS = ["CoolAir Technical Services", "BreezeCare", "Polar Maintenance", "FreshFlow Services"]


def _start_date(rng: random.Random) -> date:
    return date(rng.choice([2025, 2026, 2027]), rng.randint(1, 12), 1)


# ---------------------------------------------------------------------------
# document families
# ---------------------------------------------------------------------------


def tenancy_en(rng: random.Random, n: int) -> Doc:
    b, unit = rng.choice(BUILDINGS), rng.randint(101, 2405)
    landlord, tenant = rng.sample(PEOPLE, 2)
    start = _start_date(rng)
    end = start.replace(year=start.year + 1) - timedelta(days=1)
    rent = rng.randrange(45_000, 180_000, 500)
    cheques = rng.choice([1, 2, 4, 6, 12])
    dep_pct = rng.choice([5, 10])
    notice = rng.choice([60, 90])
    cap = rng.choice([300, 500, 750, 1000])
    parking = rng.choice([0, 1, 2])
    pets = rng.random() < 0.5
    sections = [
        ("Parties and premises",
         f"This tenancy contract is between {landlord} (landlord) and {tenant} (tenant) for "
         f"Unit {unit}, {b}."),
        ("Term and rent",
         f"The term is twelve months from {en_date(start)} to {en_date(end)}. Rent for the year: "
         f"AED {money(rent)}, settled by {cheques} cheque{'s' if cheques > 1 else ''} of "
         f"AED {money(rent // cheques)} each."),
        ("Security deposit",
         f"The tenant pays a security deposit of {dep_pct} percent of the annual rent, "
         f"AED {money(rent * dep_pct // 100)}, refundable within 30 days of handover."),
        ("Renewal and notice",
         f"Either party must give {notice} days written notice before expiry if it does not "
         "wish to renew. Without notice the contract renews for a further twelve months."),
        ("Maintenance",
         f"Small repairs are the tenant's cost, capped at AED {money(cap)} for each repair. Major "
         "repairs, including the air conditioning plant, fall to the landlord."),
    ]
    extra = []
    if parking:
        extra.append(f"The unit includes {parking} allocated parking bay{'s' if parking > 1 else ''}.")
    extra.append("Pets are permitted with the landlord's written consent." if pets
                 else "No pets are permitted in the unit.")
    sections.append(("Parking and pets", " ".join(extra)))
    where = f"Unit {unit} at {b}"
    facts = [
        Fact([f"When does the tenancy for {where} start?", f"What is the start date of the lease for {where}?"],
             [en_date(start)], "dates"),
        Fact([f"When does the {where} tenancy end?", f"What is the expiry date of the contract for {where}?"],
             [en_date(end)], "dates"),
        Fact([f"What is the annual rent for {where}?", f"How much is the yearly rent for {where}?"],
             money_expect(rent), "money"),
        Fact([f"How much is each rent cheque for {where}?", f"What is the amount of one rent cheque for {where}?"],
             money_expect(rent // cheques), "money"),
        Fact([f"How much is the security deposit for {where}?", f"What deposit did the tenant pay for {where}?"],
             money_expect(rent * dep_pct // 100), "money"),
        Fact([f"How much notice is needed to end the tenancy for {where}?", f"How many days notice before expiry for {where}?"],
             days_expect(notice), "notice"),
        Fact([f"Up to what amount does the tenant pay for minor repairs at {where}?"],
             money_expect(cap), "maintenance"),
        Fact([f"Who is the landlord for {where}?"], [landlord], "parties"),
        Fact([f"Are pets allowed in {where}?"], ["written consent"] if pets else ["no pets"], "rules"),
    ]
    if parking:
        facts.append(Fact([f"How many parking bays come with {where}?"], [str(parking)], "parking"))
    other = unit + rng.choice([1, 2, 100])
    absent = [
        (f"What is the annual rent for Unit {other} at {b}?",
         f"Only Unit {unit} is in the library; Unit {other} is a near-miss identifier.", f"Unit {other}, {b}"),
        (f"What is the service charge for {where}?", "The contract states no service charge."),
        (f"What is the internet speed included with the tenancy for {where}?", "No internet terms in the contract."),
        (f"Is the rent for {where} subject to VAT?", "The contract is silent on VAT."),
    ]
    if not parking:
        absent.append((f"How many parking bays come with {where}?", "The contract allocates no parking."))
    wrong = 30 if notice != 30 else 45
    d = Doc(f"tr-tenancy-{n:03d}", f"Tenancy Contract — Unit {unit}, {b}", "en",
            f"tr-tenancy-{n:03d}", sections, facts, absent, key=where)
    d.premises = [(f"Why is the notice period for {where} only {wrong} days?",
                   f"False premise: the contract requires {notice} days.")]
    d.traps = [
        (f"What will the rent be for {where} after the contract renews?",
         "Only the current year's rent is stated; renewal rent is not.",
         f"What is the annual rent for {where} this term?", money_expect(rent)),
        (f"What is the late fee if a rent cheque for {where} is paid late?",
         "No late payment fee is stated.",
         f"How many rent cheques are there for {where}?", [f"{cheques} cheque", f"{cheques} rent cheque"]),
    ]
    return d


def tenancy_ar(rng: random.Random, n: int) -> Doc:
    b, unit = rng.choice(BUILDINGS_AR), rng.randint(101, 2405)
    ref = f"الوحدة {unit} في {b}"
    landlord, tenant = rng.sample(PEOPLE_AR, 2)
    start = _start_date(rng)
    end = start.replace(year=start.year + 1) - timedelta(days=1)
    rent = rng.randrange(45_000, 180_000, 500)
    cheques = rng.choice([1, 2, 4, 6])
    notice = rng.choice([60, 90])
    deposit = rent // 20
    sections = [
        ("الأطراف والعقار", f"هذا العقد بين {landlord} (المالك) و{tenant} (المستأجر) للوحدة {unit} في {b}."),
        ("المدة والإيجار",
         f"مدة العقد اثنا عشر شهراً من {ar_date(start)} إلى {ar_date(end)}. الإيجار السنوي "
         f"{money(rent)} درهم، يُدفع على {cheques} شيكات قيمة كل منها {money(rent // cheques)} درهم."),
        ("التأمين", f"يدفع المستأجر تأميناً قدره {money(deposit)} درهم يُسترد خلال 30 يوماً من تسليم الوحدة."),
        ("التجديد والإشعار",
         f"على الطرف الذي لا يرغب في التجديد إرسال إشعار كتابي قبل {notice} يوماً من انتهاء العقد."),
    ]
    facts = [
        Fact([f"متى يبدأ عقد إيجار {ref}؟"], ar_date_expect(start), "dates"),
        Fact([f"متى ينتهي عقد إيجار {ref}؟"], ar_date_expect(end), "dates"),
        Fact([f"كم الإيجار السنوي {ref}؟", f"ما قيمة الإيجار السنوي {ref}؟"],
             money_expect(rent, "ar"), "money"),
        Fact([f"كم قيمة الشيك الواحد لإيجار {ref}؟"], money_expect(rent // cheques, "ar"), "money"),
        Fact([f"كم مبلغ التأمين لعقد {ref}؟"], money_expect(deposit, "ar"), "money"),
        Fact([f"كم يوماً قبل انتهاء عقد {ref} يجب إرسال الإشعار؟"], days_expect(notice, "ar"), "notice"),
        Fact([f"من هو مالك {ref}؟"], [landlord], "parties"),
    ]
    absent = [
        (f"هل يشمل إيجار {ref} رسوم الخدمات؟", "العقد لا يذكر رسوم الخدمات."),
        (f"كم عدد مواقف السيارات المخصصة {ref}؟", "العقد لا يذكر مواقف السيارات."),
        (f"هل يُسمح بالحيوانات الأليفة في {ref}؟", "العقد لا يذكر الحيوانات الأليفة."),
    ]
    d = Doc(f"tr-tenancy-ar-{n:03d}", f"عقد إيجار — الوحدة {unit}، {b}", "ar",
            f"tr-tenancy-ar-{n:03d}", sections, facts, absent, key=ref)
    d.premises = [(f"لماذا مدة الإشعار في عقد {ref} {notice + 30} يوماً فقط؟",
                   f"False premise: the contract requires {notice} days.")]
    d.traps = [(f"كم سيكون الإيجار السنوي {ref} بعد تجديد العقد؟",
                "Only the current rent is stated; renewal rent is not.",
                f"كم الإيجار السنوي الحالي {ref}؟", money_expect(rent, "ar"))]
    return d


def utility_bill_en(rng: random.Random, n: int) -> Doc:
    co = rng.choice(UTILITIES)
    acct = f"{rng.randint(10, 99)}-{rng.randint(100000, 999999)}"
    month = _start_date(rng)
    ref = f"{co} bill for {_MONTHS[month.month - 1]} {month.year}"
    kwh = rng.randint(400, 4800)
    rate = rng.choice([23, 25, 28])
    water = rng.randint(800, 6000)
    elec = kwh * rate // 100
    water_amt = water * 3 // 100
    meter = rng.choice([10, 15, 20])
    total = elec + water_amt + meter
    due = month + timedelta(days=rng.choice([20, 21, 25]))
    late = rng.choice([2, 3, 5])
    sections = [
        ("Account", f"{co} bill for account {acct}, billing period {_MONTHS[month.month - 1]} {month.year}."),
        ("Consumption",
         f"Electricity consumed: {kwh:,} kWh at {rate} fils per kWh, AED {money(elec)}. Water consumed: "
         f"{water:,} imperial gallons, AED {money(water_amt)}. Meter charge: AED {meter}."),
        ("Amount due",
         f"Total due: AED {money(total)}, payable by {en_date(due)}. A late payment charge of {late} "
         "percent applies to balances unpaid after the due date."),
    ]
    facts = [
        Fact([f"How much is due on the {ref}?", f"What is the total of the {ref}?"],
             money_expect(total), "money"),
        Fact([f"When is the {ref} due?", f"What is the payment deadline on the {ref}?"],
             [en_date(due)], "dates"),
        Fact([f"How many kWh of electricity were used on the {ref}?"], [f"{kwh:,}"], "usage"),
        Fact([f"How much water was consumed on the {ref}?"], [f"{water:,}"], "usage"),
        Fact([f"What is the electricity rate per kWh on the {ref}?"], [f"{rate} fils"], "rates"),
        Fact([f"What is the late payment charge on the {ref}?"], [f"{late} percent"], "billing"),
    ]
    absent = [
        (f"How much is the sewerage fee on the {ref}?", "The bill lists no sewerage fee."),
        (f"What is the {co} bill amount for account {acct} in {_MONTHS[(month.month - 2) % 12]} {month.year - (month.month == 1)}?", "Only one billing period is in the library."),
        (f"Does {co} offer a solar panel discount?", "No discount terms on the bill."),
    ]
    d = Doc(f"tr-bill-{n:03d}", f"{co} — Bill, account {acct}", "en", f"tr-bill-{n:03d}",
            sections, facts, absent, key=ref)
    d.traps = [
        (f"What is the reconnection fee on the {ref}?",
         "Only a late payment charge is stated; no reconnection fee.",
         f"What is the late payment charge on the {ref}?", [f"{late} percent"]),
        # Not "water rate per gallon": amount / gallons derives it, so a model
        # that computes it is right and the label would be wrong (cf. E20 u045).
        (f"What is the fuel surcharge on the {ref}?",
         "The bill lists no fuel surcharge.",
         f"How much is the water charge on the {ref}?", money_expect(water_amt)),
    ]
    return d


def utility_bill_ar(rng: random.Random, n: int) -> Doc:
    co = rng.choice(UTILITIES_AR)
    acct = f"{rng.randint(10, 99)}-{rng.randint(100000, 999999)}"
    month = _start_date(rng)
    ref = f"فاتورة {co} لشهر {_MONTHS_AR[month.month - 1]} {month.year}"
    kwh = rng.randint(400, 4800)
    total = rng.randrange(250, 2400, 5)
    due = month + timedelta(days=21)
    sections = [
        ("الحساب", f"فاتورة {co} للحساب {acct} عن شهر {_MONTHS_AR[month.month - 1]} {month.year}."),
        ("الاستهلاك والمبلغ",
         f"استهلاك الكهرباء {kwh} كيلوواط ساعة. المبلغ الإجمالي المستحق {money(total)} درهم، "
         f"ويجب السداد قبل {ar_date(due)}."),
    ]
    facts = [
        Fact([f"كم المبلغ المستحق في {ref}؟", f"ما إجمالي {ref}؟"],
             money_expect(total, "ar"), "money"),
        Fact([f"متى آخر موعد لسداد {ref}؟"], ar_date_expect(due), "dates"),
        Fact([f"كم كان استهلاك الكهرباء في {ref}؟"], [str(kwh), str(kwh).translate(_EASTERN)], "usage"),
    ]
    absent = [(f"كم رسوم الصرف الصحي في {ref}؟", "الفاتورة لا تذكر رسوم الصرف الصحي.")]
    d = Doc(f"tr-bill-ar-{n:03d}", f"فاتورة {co} — الحساب {acct}", "ar", f"tr-bill-ar-{n:03d}",
            sections, facts, absent, key=ref)
    d.traps = [(f"كم رسوم التأخير في {ref}؟", "The bill states no late fee.",
                f"متى آخر موعد لسداد {ref}؟", ar_date_expect(due))]
    return d


def car_registration(rng: random.Random, n: int) -> Doc:
    make, model = rng.choice(CARS)
    year = rng.randint(2016, 2026)
    plate = f"{rng.choice('ABCDEFGHKLMN')} {rng.randint(10000, 99999)}"
    ref = f"the {make} {model} with plate {plate}"
    owner = rng.choice(PEOPLE)
    insurer = rng.choice(INSURERS)
    expiry = _start_date(rng) + timedelta(days=rng.randint(0, 27))
    fee = rng.choice([350, 400, 450])
    inspect = year < 2023
    sections = [
        ("Vehicle", f"{year} {make} {model}, plate {plate}, registered to {owner}."),
        ("Registration",
         f"Registration expires on {en_date(expiry)}. The renewal fee is AED {fee}. "
         + ("A technical inspection is required before renewal because the vehicle is more than three years old."
            if inspect else "No technical inspection is required at the next renewal.")),
        ("Insurance", f"Insured by {insurer}. Valid insurance is required to renew the registration."),
    ]
    facts = [
        Fact([f"When does the registration for plate {plate} expire?", f"When does the registration of {ref} expire?"],
             [en_date(expiry)], "dates"),
        Fact([f"How much is the registration renewal fee for {ref}?"], [f"AED {fee}"], "money"),
        Fact([f"Who insures {ref}?"], [insurer], "insurance"),
        Fact([f"Does {ref} need an inspection before renewal?"],
             ["inspection is required"] if inspect else ["no technical inspection"], "rules"),
        Fact([f"What model year is {ref}?"], [str(year)], "vehicle"),
    ]
    absent = [
        (f"What is the insurance premium for {ref}?", "The registration card gives no premium."),
        (f"How many traffic fines are on plate {plate}?", "No fines record in the library."),
        (f"What is the mileage of {ref}?", "Mileage is not recorded."),
    ]
    d = Doc(f"tr-car-{n:03d}", f"Vehicle Registration — {make} {model}, plate {plate}", "en",
            f"tr-car-{n:03d}", sections, facts, absent, key=plate)
    d.premises = [(f"Why is the renewal fee for {ref} AED {fee + 250}?",
                   f"False premise: the renewal fee is AED {fee}.")]
    d.traps = [
        (f"When does the insurance policy for {ref} expire?",
         "Only the registration expiry is given; the insurance expiry is not.",
         f"When does the registration of {ref} expire?", [en_date(expiry)]),
        (f"How much does the technical inspection for {ref} cost?",
         "Inspection is mentioned but its cost is not.",
         f"How much is the registration renewal fee for {ref}?", [f"AED {fee}"]),
    ]
    return d


def school_fees(rng: random.Random, n: int, year: int | None = None, base: dict | None = None) -> Doc:
    school = base["school"] if base else rng.choice(SCHOOLS)
    grade = base["grade"] if base else rng.randint(1, 12)
    year = year or rng.choice([2026, 2027])
    tuition = rng.randrange(28_000, 95_000, 500)
    sibling = rng.choice([5, 10, 15])
    bus = rng.randrange(4_000, 9_000, 250)
    reg = rng.choice([500, 1000, 1500])
    refund_weeks = rng.choice([2, 4, 6])
    label = f"{year}/{str(year + 1)[-2:]}"
    sections = [
        ("Tuition",
         f"Annual tuition for Grade {grade} at {school} in {label} is AED {money(tuition)}, payable in three "
         "termly instalments."),
        ("Discounts", f"A sibling discount of {sibling} percent applies to the second and later children."),
        ("Other fees",
         f"School transport costs AED {money(bus)} per year. A non-refundable registration fee of AED {money(reg)} "
         "is due on enrolment."),
        ("Withdrawal", f"Tuition is refunded in full if written notice of withdrawal is given {refund_weeks} weeks "
                       "before the start of term."),
    ]
    facts = [
        Fact([f"What is the Grade {grade} tuition at {school}?", f"How much are annual fees for Grade {grade} at {school}?"],
             money_expect(tuition), "money"),
        Fact([f"What is the sibling discount for Grade {grade} at {school}?"], [f"{sibling} percent"], "discounts"),
        Fact([f"How much is the school bus for Grade {grade} at {school}?"], money_expect(bus), "money"),
        Fact([f"What is the registration fee for Grade {grade} at {school}?"], money_expect(reg), "money"),
        Fact([f"How much notice is needed for a full Grade {grade} tuition refund at {school}?"], [f"{refund_weeks} weeks"], "refunds"),
    ]
    absent = [
        (f"What is the uniform cost for Grade {grade} at {school}?", "The fee schedule lists no uniform cost."),
        (f"What is the Grade {grade} tuition at {school} for {year + 3}/{str(year + 4)[-2:]}?",
         "Only the listed academic year is in the library."),
        (f"Does {school} charge Grade {grade} for after-school activities?", "No activity fees in the schedule."),
    ]
    sid = base["doc_id"] + "-old" if base else f"tr-fees-{n:03d}"
    d = Doc(sid, f"{school} — Fee Schedule {label}, Grade {grade}", "en",
            base["about"] if base else sid, sections, facts, absent, key=f"{school}|{grade}")
    other = grade + 1 if grade < 12 else grade - 1
    d.traps = [
        (f"What is the Grade {other} tuition at {school}?",
         f"The schedule covers Grade {grade} only.",
         f"What is the Grade {grade} tuition at {school}?", money_expect(tuition)),
        (f"How much is a one-way school bus for Grade {grade} at {school}?",
         "Only the annual transport fee is given.",
         f"How much is the school bus for Grade {grade} at {school}?", money_expect(bus)),
    ]
    return d


def school_fees_ar(rng: random.Random, n: int) -> Doc:
    school = rng.choice(SCHOOLS_AR)
    grade = rng.randint(1, 12)
    tuition = rng.randrange(28_000, 95_000, 500)
    sibling = rng.choice([5, 10, 15])
    sections = [
        ("الرسوم الدراسية", f"الرسوم السنوية للصف {grade} في {school} هي {money(tuition)} درهم، تُدفع على ثلاثة أقساط."),
        ("الخصومات", f"يُمنح خصم للإخوة بنسبة {sibling} بالمئة للطفل الثاني وما بعده."),
    ]
    facts = [
        Fact([f"كم الرسوم السنوية للصف {grade} في {school}؟"], money_expect(tuition, "ar"), "money"),
        Fact([f"كم نسبة خصم الإخوة للصف {grade} في {school}؟"], [f"{sibling} بالمئة", f"{sibling}%"], "discounts"),
    ]
    absent = [(f"كم رسوم الحافلة المدرسية للصف {grade} في {school}؟", "الجدول لا يذكر رسوم الحافلة.")]
    d = Doc(f"tr-fees-ar-{n:03d}", f"جدول رسوم {school} — الصف {grade}", "ar", f"tr-fees-ar-{n:03d}",
            sections, facts, absent, key=f"{school}|{grade}")
    other = grade + 1 if grade < 12 else grade - 1
    d.traps = [(f"كم الرسوم السنوية للصف {other} في {school}؟", f"The schedule covers Grade {grade} only.",
                f"كم الرسوم السنوية للصف {grade} في {school}؟", money_expect(tuition, "ar"))]
    return d


def gym(rng: random.Random, n: int) -> Doc:
    g = rng.choice(GYMS)
    member = rng.choice(PEOPLE)
    ref = f"{member}'s membership at {g}"
    monthly = rng.choice([199, 249, 299, 349, 450])
    months = rng.choice([6, 12, 24])
    freeze = rng.choice([14, 30, 60])
    cancel = rng.choice([30, 60])
    guests = rng.choice([0, 2, 4])
    sections = [
        ("Membership", f"{member} holds a {months}-month membership at {g} for AED {monthly} per month."),
        ("Freezing and cancellation",
         f"The membership may be frozen for up to {freeze} days per year. Cancellation requires {cancel} days "
         "written notice; fees already paid are not refunded."),
        ("Guests", f"The member receives {guests} free guest passes per month." if guests
         else "Guest passes are not included in this membership."),
    ]
    facts = [
        Fact([f"How much is the monthly fee for {ref}?", f"What does {member} pay per month at {g}?"], [f"AED {monthly}"], "money"),
        Fact([f"How long can {ref} be frozen?"], days_expect(freeze), "rules"),
        Fact([f"How much notice is needed to cancel {ref}?"], days_expect(cancel), "notice"),
        Fact([f"How long is the term of {ref}?"], [f"{months}-month", f"{months} months"], "term"),
        Fact([f"How many guest passes come with {ref}?"],
             [f"{guests} free guest"] if guests else ["not included"], "rules"),
    ]
    absent = [
        (f"What are the opening hours of {g}?", "The membership terms give no opening hours."),
        (f"Does {ref} include swimming pool access?", "Facilities are not described."),
    ]
    d = Doc(f"tr-gym-{n:03d}", f"{g} — Membership Agreement", "en", f"tr-gym-{n:03d}", sections, facts, absent, key=ref)
    d.premises = [(f"Why does {ref} need {cancel + 60} days notice to cancel?",
                   f"False premise: cancellation needs {cancel} days notice.")]
    d.traps = [(f"How much is {ref} if paid annually up front?",
                "Only the monthly fee is stated; no annual price.",
                f"How much is the monthly fee for {ref}?", [f"AED {monthly}"])]
    return d


def telecom(rng: random.Random, n: int) -> Doc:
    t = rng.choice(TELCOS)
    plan = f"Home {rng.choice([250, 500, 1000])}"
    speed = int(plan.split()[1])
    monthly = rng.choice([299, 349, 389, 449, 529])
    term = rng.choice([12, 24])
    etf = rng.randrange(500, 2500, 100)
    install = rng.choice([0, 199, 299])
    sections = [
        ("Plan", f"{t} {plan} home internet: {speed} Mbps download, AED {monthly} per month, {term}-month commitment."),
        ("Installation", "Installation is free." if not install else f"A one-off installation fee of AED {install} applies."),
        ("Early termination", f"Ending the contract before the commitment period costs AED {money(etf)}."),
    ]
    facts = [
        Fact([f"How much is the {t} {plan} plan per month?"], [f"AED {monthly}"], "money"),
        Fact([f"What download speed does the {t} {plan} plan give?"], [f"{speed} Mbps"], "plan"),
        Fact([f"What is the early termination fee for {t} {plan}?"], money_expect(etf), "money"),
        Fact([f"How long is the {t} {plan} commitment?"], [f"{term}-month", f"{term} months"], "term"),
        Fact([f"Is there an installation fee for {t} {plan}?"],
             ["free"] if not install else [f"AED {install}"], "money"),
    ]
    absent = [
        (f"What is the upload speed on {t} {plan}?", "Only download speed is stated."),
        (f"Does {t} {plan} include a TV package?", "No TV terms in the plan."),
    ]
    d = Doc(f"tr-telecom-{n:03d}", f"{t} — {plan} Plan Terms", "en", f"tr-telecom-{n:03d}", sections, facts, absent,
            key=f"{t} {plan}")
    d.traps = [(f"What is the monthly price of {t} {plan} after the commitment period ends?",
                "Only the price during the commitment is stated.",
                f"How much is the {t} {plan} plan per month?", [f"AED {monthly}"])]
    return d


def warranty(rng: random.Random, n: int) -> Doc:
    brand, code = rng.choice(BRANDS)
    model = f"{code}-{rng.randint(1000, 9899)}"
    kind = APPLIANCES[code]
    months = rng.choice([12, 24, 36])
    part_years = rng.choice([5, 7, 10])
    part = {"WM": "inverter motor", "AC": "compressor", "DW": "circulation pump", "OV": "heating element",
            "TV": "display panel"}[code]
    hours = rng.choice(["8 am to 8 pm, Saturday to Thursday", "9 am to 6 pm, Monday to Saturday"])
    sections = [
        ("Coverage", f"The {brand} {model} {kind} is covered for {months} months from purchase against "
                     f"manufacturing defects. The {part} is covered for {part_years} years."),
        ("Exclusions", "The warranty does not cover damage from misuse, power surges or unauthorised repair."),
        ("Service", f"The service centre is open {hours}. Keep the purchase invoice; it is required for any claim."),
    ]
    facts = [
        Fact([f"How long is the warranty on the {brand} {model}?", f"What is the warranty period for the {model} {kind}?"],
             [f"{months} months"], "warranty"),
        Fact([f"How long is the {part} on the {model} covered?"], [f"{part_years} years"], "warranty"),
        Fact([f"What does the {brand} {model} warranty exclude?"], ["misuse", "power surges", "unauthorised repair"], "warranty"),
        Fact([f"When is the service centre for the {brand} {model} open?"], [hours.split(",")[0]], "service"),
        Fact([f"What do I need to make a warranty claim on the {model}?"], ["purchase invoice"], "claims"),
    ]
    other = f"{code}-{int(model.split('-')[1]) + rng.choice([1, 10, 100])}"
    absent = [
        (f"How long is the warranty on the {brand} {other}?", f"Only {model} is in the library; {other} is a near-miss.",
         other),
        (f"What is the energy rating of the {brand} {model}?", "The warranty does not state an energy rating."),
        (f"Can I extend the {brand} {model} warranty?", "No extension terms are given."),
    ]
    d = Doc(f"tr-warranty-{n:03d}", f"{brand} {model} {kind.title()} — Warranty", "en",
            f"tr-warranty-{n:03d}", sections, facts, absent, key=model)
    d.premises = [(f"Why is the {brand} {model} warranty only 6 months?",
                   f"False premise: the warranty is {months} months.")]
    d.traps = [
        (f"How long is the warranty on the accessories that came with the {brand} {model}?",
         "Only the appliance and one part are covered; accessories are not mentioned.",
         f"How long is the warranty on the {brand} {model}?", [f"{months} months"]),
        (f"Is a refurbished {brand} {model} covered by the same warranty?",
         "Refurbished units are not addressed.",
         f"How long is the {part} on the {model} covered?", [f"{part_years} years"]),
    ]
    return d


def ac_service(rng: random.Random, n: int) -> Doc:
    s = rng.choice(SERVICERS)
    visits = rng.choice([2, 3, 4])
    fee = rng.randrange(600, 2400, 50)
    response = rng.choice([4, 6, 12, 24])
    parts = rng.choice([250, 500, 1000])
    b = rng.choice(BUILDINGS)
    sections = [
        ("Scope", f"{s} services the air conditioning at {b} {visits} times a year for AED {money(fee)} annually."),
        ("Breakdowns", f"Emergency call-outs are attended within {response} hours. Spare parts are included up to "
                       f"AED {money(parts)} per year; above that they are charged at cost."),
    ]
    facts = [
        Fact([f"How many AC service visits per year does {s} make at {b}?"], [f"{visits} times"], "scope"),
        Fact([f"What is the annual {s} maintenance fee at {b}?"], money_expect(fee), "money"),
        Fact([f"How fast does {s} respond to a breakdown at {b}?"], [f"{response} hours"], "service"),
        Fact([f"Up to what value are spare parts included in the {s} contract at {b}?"], money_expect(parts), "money"),
    ]
    absent = [
        (f"Does the {s} contract at {b} cover the water heater?", "Only air conditioning is in scope."),
        (f"When does the {s} contract at {b} end?", "The contract gives no end date."),
    ]
    d = Doc(f"tr-acservice-{n:03d}", f"{s} — AC Maintenance Contract, {b}", "en",
            f"tr-acservice-{n:03d}", sections, facts, absent, key=f"{s}|{b}")
    d.traps = [(f"How quickly does {s} respond to a routine, non-emergency request at {b}?",
                "Only the emergency call-out time is stated.",
                f"How fast does {s} respond to a breakdown at {b}?", [f"{response} hours"])]
    return d


# Counts are bounded by how many distinct keys each family's name pool allows.
FAMILIES = [
    (tenancy_en, 60), (tenancy_ar, 30), (utility_bill_en, 50), (utility_bill_ar, 25),
    (car_registration, 40), (school_fees, 45), (school_fees_ar, 30), (gym, 30),
    (telecom, 10), (warranty, 45), (ac_service, 30),
]
SUPERSEDED_FEES = 6  # school fee schedules that get an older, superseded year


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


def build(seed: int = 7) -> tuple[list[Doc], list[dict]]:
    rng = random.Random(seed)
    docs: list[Doc] = []
    # Arabic documents live in Arabic households, numbered after the English
    # ones, so an English and an Arabic tenancy never share an index.
    ar_offset = max(c for f, c in FAMILIES if not f.__name__.endswith("_ar"))
    for family, count in FAMILIES:
        offset = ar_offset if family.__name__.endswith("_ar") else 0
        seen: set[str] = set()
        n = 0
        for _ in range(count * 20):
            if n == count:
                break
            d = family(rng, n + 1)
            if d.key in seen:
                continue  # two documents a question could not tell apart
            seen.add(d.key)
            d.household = offset + n
            n += 1
            docs.append(d)

    # Version skew: a superseded schedule for the same school and grade, with
    # different numbers. The live one must win; the old one is a distractor.
    skewed = [d for d in docs if d.doc_id.startswith("tr-fees-") and "-ar-" not in d.doc_id][:SUPERSEDED_FEES]
    for live in skewed:
        school, grade = live.title.split(" — ")[0], int(live.title.rsplit("Grade ", 1)[1])
        year = int(live.title.split("Schedule ")[1][:4])
        old = school_fees(rng, 0, year - 1, {"school": school, "grade": grade, "doc_id": live.doc_id,
                                                "about": live.about})
        old.status, old.tier, old.facts, old.absent = "superseded", "secondary", [], []
        old.household = live.household
        docs.append(old)

    for i, d in enumerate(docs):
        d.split = "valid" if i % VALID_EVERY == VALID_EVERY - 1 else "train"
    by_id = {d.doc_id: d for d in docs}
    for d in docs:  # an old version sits in the same split as its live one
        if d.doc_id.endswith("-old"):
            d.split = by_id[d.doc_id.removesuffix("-old")].split

    items: list[dict] = []
    # A near-miss is only unanswerable if nothing in that household names it.
    texts: dict[int, list[str]] = {}
    for d in docs:
        texts.setdefault(d.household, []).append(d.markdown())

    def add(kind: str, question: str, d: Doc, **kw) -> None:
        items.append({"id": f"t{len(items) + 1:05d}", "kind": kind, "question": question, "lang": d.lang,
                      "split": d.split, "household": d.household, **kw})

    for d in docs:
        for f in d.facts:
            for q in f.questions:
                add("answerable", q, d, expect_any=f.expect, expect_doc=d.doc_id, tags=[f.tag])
        for q, why, *probe in d.absent:
            if probe and any(probe[0] in t for t in texts[d.household]):
                continue  # the near-miss identifier exists after all
            add("unanswerable", q, d, note=why, tags=["near_miss" if probe else "absent"])
    return docs, items + round_two(docs, seed) + round_three(docs)


# ---------------------------------------------------------------------------
# round 2 (E23): refusals the first student never saw
# ---------------------------------------------------------------------------
#
# The first SFT student cited passages for general knowledge ("The Berlin Wall
# fell in 1989 [S1][S5]") because every training refusal was a near-miss about
# a household document. These add the shapes it had not seen: world facts, a
# document kind the household does not have, and a false premise. None reuse an
# eval question or its fact (tests/test_train.py checks the questions).

GENERAL_EN = [
    "What is the capital of Canada?", "Who painted the Mona Lisa?", "How many continents are there?",
    "What is the tallest mountain in the world?", "Who was the first person to walk on the Moon?",
    "What is the freezing point of water in Fahrenheit?", "How many days are in a leap year?",
    "What is the chemical formula for table salt?", "Which planet is closest to the Sun?",
    "Who wrote Romeo and Juliet?", "What is the longest river in South America?",
    "In what year did the Titanic sink?", "How many players does a football team have on the pitch?",
    "What is the square root of 144?", "What language is spoken in Brazil?", "What is the largest ocean?",
    "Who discovered penicillin?", "What is the capital of Australia?", "How many minutes are in a day?",
    "What gas do plants absorb from the air?", "In what year was the UAE founded?",
    "What is the national bird of the UAE?", "How tall is the Burj Khalifa?",
    "What time does the Dubai Metro open on Fridays?", "What is the population of Abu Dhabi?",
    "Who is the current FIFA president?",
]
GENERAL_AR = [
    "ما عاصمة كندا؟", "من رسم الموناليزا؟", "كم عدد القارات؟", "ما أطول نهر في العالم؟",
    "من كتب روميو وجولييت؟", "ما أكبر محيط في العالم؟", "كم يوماً في السنة الكبيسة؟",
    "ما الطائر الوطني لدولة الإمارات؟", "كم يبلغ ارتفاع برج خليفة؟", "في أي عام تأسست دولة الإمارات؟",
    "ما عاصمة أستراليا؟", "من اكتشف البنسلين؟",
]
# A household without this kind of document is asked about one anyway.
MISSING_KIND = {
    "tr-tenancy": ("When does my tenancy contract end?", "متى ينتهي عقد الإيجار الخاص بي؟"),
    "tr-bill": ("How much is my latest electricity bill?", "كم مبلغ فاتورة الكهرباء الأخيرة؟"),
    "tr-car": ("When does my car registration expire?", "متى ينتهي تسجيل سيارتي؟"),
    "tr-fees": ("How much are my child's school fees this year?", "كم الرسوم المدرسية لطفلي هذا العام؟"),
    "tr-gym": ("How much do I pay for the gym each month?", "كم أدفع للنادي الرياضي شهرياً؟"),
    "tr-telecom": ("What speed is my home internet plan?", "ما سرعة باقة الإنترنت المنزلي؟"),
    "tr-warranty": ("How long is the warranty on my washing machine?", "كم مدة ضمان الغسالة؟"),
    "tr-acservice": ("How many times a year is the air conditioning serviced?", "كم مرة في السنة تتم صيانة المكيف؟"),
}


def _kind(doc_id: str) -> str:
    return doc_id.removesuffix("-old").rsplit("-", 1)[0].removesuffix("-ar")


def round_two(docs: list[Doc], seed: int) -> list[dict]:
    rng = random.Random(seed + 1)  # its own stream: round-1 documents stay byte-identical
    homes: dict[int, list[Doc]] = {}
    for d in docs:
        homes.setdefault(d.household, []).append(d)
    split = {h: ds[0].split for h, ds in homes.items()}
    lang = {h: ds[0].lang for h, ds in homes.items()}
    out: list[dict] = []

    def add(question: str, h: int, note: str, tag: str) -> None:
        out.append({"id": f"t2-{len(out) + 1:05d}", "kind": "unanswerable", "question": question,
                    "lang": lang[h], "split": split[h], "household": h, "note": note, "tags": [tag]})

    for language, pool in (("en", GENERAL_EN), ("ar", GENERAL_AR)):
        hs = sorted(h for h in homes if lang[h] == language)
        for q in pool:
            for h in rng.sample(hs, 2):
                add(q, h, "General knowledge; no document in the library states it.", "general")
    for h, ds in sorted(homes.items()):
        have = {_kind(d.doc_id) for d in ds}
        missing = sorted(k for k in MISSING_KIND if k not in have)
        for k in rng.sample(missing, min(2, len(missing))):
            en, ar = MISSING_KIND[k]
            add(ar if lang[h] == "ar" else en, h, f"This household has no {k[3:]} document.", "missing_kind")
    for d in docs:
        for q, note in d.premises:
            add(q, d.household, note, "false_premise")
    return out



# ---------------------------------------------------------------------------
# round 3 (E24): adjacent-fact traps
# ---------------------------------------------------------------------------
#
# After run 2 the student failed 8 of 4,264 training items, too few to learn
# from, while its benchmark failures shared one shape: a question about
# something next to a stated fact, answered with that fact. These questions
# are that shape on the training documents. Each comes with an answerable
# sibling, so preference pairs can teach the line between them rather than a
# general lean towards refusing.


def round_three(docs: list[Doc]) -> list[dict]:
    out: list[dict] = []

    def add(kind: str, question: str, d: Doc, tag: str, **kw) -> None:
        out.append({"id": f"t3-{len(out) + 1:05d}", "kind": kind, "question": question, "lang": d.lang,
                    "split": d.split, "household": d.household, "tags": [tag], **kw})

    for d in docs:
        for trap, why, sibling, expect in d.traps:
            add("unanswerable", trap, d, "adjacent", note=why)
            add("answerable", sibling, d, "adjacent_sibling", expect_any=expect, expect_doc=d.doc_id)
    return out


def household_dir(n: int) -> str:
    return f"h{n:03d}"


def write(out_dir: Path, seed: int = 7) -> tuple[int, int]:
    docs, items = build(seed)
    corpus = out_dir / "corpus"
    for old in [*corpus.glob("*.md"), *corpus.glob("h*/*.md")]:
        old.unlink()
    for d in docs:
        home = corpus / household_dir(d.household)
        home.mkdir(parents=True, exist_ok=True)
        (home / f"{d.doc_id}.md").write_text(d.markdown(), encoding="utf-8")
    (out_dir / "items.jsonl").write_text(
        "\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8"
    )
    return len(docs), len(items)
