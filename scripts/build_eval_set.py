"""Regenerate data/eval/eval_set.jsonl from a compact declaration.

The eval set is the project's measuring instrument, so it is kept as source
rather than hand-edited JSONL: that way the proportions, the uniqueness of ids
and the existence of every `expect_doc` are checked by running this file, and
the diff of a change is readable.

Run:  python scripts/build_eval_set.py
"""

from __future__ import annotations

import json
import re
import subprocess
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
    ("How much is each rent cheque for the flat?", ["AED 19,500", "19,500"], "tenancy-agreement", "money"),
    ("What happens if neither party serves notice before the tenancy expires?", ["renews automatically", "further 12 months"], "tenancy-agreement", "notice"),
    ("Who is responsible for the central air conditioning under the tenancy?", ["landlord"], "tenancy-agreement", "maintenance"),
    ("Up to what amount is the tenant responsible for minor maintenance?", ["AED 500", "500 per incident"], "tenancy-agreement", "maintenance"),
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



# E8 - the headline metric lives on this slice, so it is the one that has to be
# big. Every item names why it cannot be answered; see tests/test_eval.py.
UNANSWERABLE += [
    # near-miss entities: the distinctive terms are all present, one token differs
    ("What is the excess on an ArcticLine FR-441?", "FR-441 is not the documented model; the manual covers the FR-440.", "near-miss"),
    ("How much is the Freedom 150 Plus plan?", "No 'Plus' variant exists in the plan terms.", "near-miss"),
    ("What is the Vertex V14 Pro battery coverage?", "Only the plain V14 is documented.", "near-miss"),
    ("What is the pass mark for PHY-103?", "Only PHY-104 appears in the handbooks.", "near-miss"),
    ("What does the ALF-90 filter cost?", "The documented part is ALF-9; ALF-90 does not appear.", "near-miss"),
    ("What is the deposit for Unit 1024 at Al Noor Tower?", "The contract is for Unit 1204, not 1024.", "near-miss"),
    ("What is the tariff for the first 2,500 kWh?", "The slab boundaries are 2,000 and 4,000 kWh; 2,500 is not a boundary.", "near-miss"),
    ("What is the library loan period for a 7-day item?", "Loans are 14-day standard or 3-day short-loan; no 7-day category.", "near-miss"),
    ("How much is the UFP application fee for international students?", "Only one application fee is documented, with no student-type split.", "near-miss"),
    ("What is the HomeGuard buildings insurance sum insured?", "The schedule covers contents, not buildings.", "near-miss"),
    # false premises: the question asserts something the corpus contradicts
    ("Why is the fridge warranty only 12 months?", "False premise: the fridge warranty is 24 months.", "false-premise"),
    ("Why does the tenancy require 30 days notice?", "False premise: the contract requires 90 days.", "false-premise"),
    ("Why is the PHY-104 exam three hours long?", "False premise: the 2026/27 handbook says 2 hours.", "false-premise"),
    ("Which three slabs above 5,000 kWh does the tariff define?", "False premise: the top slab is above 4,000 kWh and there is only one.", "false-premise"),
    ("How do I claim the library's lost-item insurance?", "False premise: no such scheme is described.", "false-premise"),
    ("What is the fourth UFP tuition instalment?", "False premise: tuition is paid in two instalments.", "false-premise"),
    ("How much data does the roaming pass give after the first 48 hours?", "False premise: the pass is valid for 24 hours.", "false-premise"),
    ("What is the second excess tier for escape of water claims?", "False premise: a single escape-of-water excess is specified.", "false-premise"),
    ("When was the tenancy contract amended?", "False premise: no amendment is recorded.", "false-premise"),
    ("Which Vertex models are excluded from the 36-month extension?", "False premise: no model exclusions are listed.", "false-premise"),
    # silent: a reasonable question the corpus simply does not cover
    ("Can I pay the electricity bill by direct debit?", "Payment methods are not described.", "silent"),
    ("Is there a discount for paying UFP tuition in full up front?", "No early-payment discount is documented.", "silent"),
    ("Can I transfer my phone plan to another person?", "Transfers are not covered by the plan terms.", "silent"),
    ("Does the library have printing facilities?", "Not covered by the regulations.", "silent"),
    ("Can I freeze my phone contract while travelling?", "Suspension is not addressed.", "silent"),
    ("What happens to the electricity deposit if I move to another apartment?", "Transfers between premises are not covered.", "silent"),
    ("Does the contents policy cover accidental damage to a laptop at home?", "Accidental damage is not listed among covered perils.", "silent"),
    ("How do I appeal a PHY-104 grade?", "No appeals process appears in the handbook.", "silent"),
    ("Can a Vertex laptop be repaired at a third-party centre under warranty?", "Third-party repair is not addressed.", "silent"),
    ("What identification do I need to open an electricity account?", "Account-opening documents are not listed.", "silent"),
    ("Is the fridge suitable for installation in a garage?", "Installation environment is not covered.", "silent"),
    ("How many guests can a tenant have overnight?", "The contract says nothing about guests.", "silent"),
    ("Does the tenancy include a service charge?", "No service charge appears in the contract.", "silent"),
    ("Can I renew a short-loan library item in person?", "Short-loan items cannot be renewed; in-person renewal is not described.", "silent"),
    ("What is the UFP minimum attendance for lectures?", "Only laboratory attendance is specified.", "silent"),
    ("Does the phone plan include visual voicemail?", "Features beyond data, voice and SMS are not listed.", "silent"),
    ("Who pays for repainting at the end of the tenancy?", "Redecoration is not addressed.", "silent"),
    ("What is the warranty on the fridge water filter itself?", "Only the appliance warranty is documented.", "silent"),
    ("Can insurance claims be submitted online?", "The claims channel is not described.", "silent"),
    ("How long does a PHY-104 resit take to be marked?", "Marking timelines are not given.", "silent"),
    ("Is there a penalty for exceeding the library borrowing limit?", "Only overdue fines are specified.", "silent"),
    ("Does the electricity tariff change in summer?", "No seasonal variation is described.", "silent"),
    ("What happens if the landlord sells the property mid-tenancy?", "Not covered by the contract excerpt.", "silent"),
    ("How do I cancel the Vertex extended warranty?", "Cancellation is not addressed.", "silent"),
    ("Can two students share one group study room booking slot?", "Shared bookings are not described.", "silent"),
    ("What is the grace period for a late UFP registration?", "No grace period is documented.", "silent"),
    ("Does the insurance cover items in a car parked at home?", "Vehicle contents are not addressed.", "silent"),
    ("What voltage does the FR-440 require?", "Electrical specifications are not in the excerpt.", "silent"),
    ("Is the agency commission refundable if the tenancy falls through?", "The summary sheet says it is non-refundable on signature but not what happens if the let fails.", "silent"),
    # prior leaks: true facts the model knows and the corpus does not contain
    ("What is the speed of light in metres per second?", "Model knows it; the corpus does not contain it.", "prior-leak"),
    ("Who wrote the Principia Mathematica?", "True fact, no source in the corpus.", "prior-leak"),
    ("What is the chemical symbol for tungsten?", "True fact, no source in the corpus.", "prior-leak"),
    ("How many millimetres are in an inch?", "A unit conversion the model knows and no document states.", "prior-leak"),
    ("What is the largest country in Africa by area?", "True fact, no source in the corpus.", "prior-leak"),
    ("In what year did the Berlin Wall fall?", "True fact, no source in the corpus.", "prior-leak"),
    ("What is the acceleration due to gravity at sea level?", "Physics the model knows; not in any document here.", "prior-leak"),
    ("What is the currency of Japan?", "True fact, no source in the corpus.", "prior-leak"),
    # Arabic
    ("كم رسوم الطباعة في المكتبة؟", "Arabic. Printing is not covered anywhere in the corpus.", "silent"),
    ("ما هي مدة ضمان الكمبيوتر المحمول في المستند العربي؟", "Arabic. The Arabic summaries cover the fridge, tenancy and fees, not the laptop.", "silent"),
    ("ما هو الرقم السري لحساب الكهرباء؟", "Arabic. No account credentials exist in the corpus.", "silent"),
    ("كم عدد سكان الإمارات؟", "Arabic prior-leak probe: a true fact with no source here.", "prior-leak"),
]

# Conflict items. Deliberately few: with n well under 30 this is a capability
# check - does the path work at all - not a rate. Reported as passed/total.
# (question, expect_docs, expect_outcome, note)
CONFLICT: list[tuple[str, list[str], str, str]] = [
    ("What is the annual rent on the Al Noor Tower unit?",
     ["tenancy-agreement", "tenancy-summary-sheet"], "conflict",
     "Contract says AED 78,000; the agency summary says AED 82,000. Both live."),
    ("How much notice must I give before the tenancy expires if I don't want to renew?",
     ["tenancy-agreement", "tenancy-summary-sheet"], "conflict",
     "Contract says 90 days; the agency summary says 60 days. Both live."),
    ("What is the security deposit on the flat?",
     ["tenancy-agreement", "tenancy-summary-sheet"], "conflict",
     "Contract says AED 3,900; the agency summary says AED 4,100. Both live."),
    ("What is the coursework weighting for PHY-104?",
     ["ufp-handbook-2026", "ufp-handbook-2025"], "version_skew",
     "2026/27 says 30 percent, superseded 2025/26 says 40. Answer from current, surface the old."),
    ("How long does the PHY-104 final examination last?",
     ["ufp-handbook-2026", "ufp-handbook-2025"], "version_skew",
     "2026/27 says 2 hours, superseded 2025/26 says 90 minutes."),
    ("What is the examination weighting for PHY-104?",
     ["ufp-handbook-2026", "ufp-handbook-2025"], "version_skew",
     "2026/27 says 70 percent, superseded 2025/26 says 60 percent."),
]


# E25 - fresh held-out slice, written to its own file so the main benchmark is
# unchanged. Written without looking at any model's output on the main set. The
# DPO run (E24) trained on adjacent-fact traps, so this slice asks the same kind
# of question about facts the training never saw, each paired with an answerable
# sibling on the fact it sits next to: a system that refuses everything cannot
# score on both halves. Pair n is ju{n} (unanswerable) and js{n} (sibling).
# (unanswerable question, why it cannot be answered, sibling question, sibling expect_any, doc)
SLICE_J_ADJACENT: list[tuple[str, str, str, list[str], str]] = [
    # -- fridge-manual -------------------------------------------------------
    ("What temperature should the FR-440's chiller drawer be set to?",
     "Settings are given for the fresh food compartment and freezer only; no chiller drawer is mentioned.",
     "What setting does ArcticLine recommend for the FR-440 fresh food compartment?", ["4 degrees", "4°C", "4 °C"], "fridge-manual"),
    ("Which FR-440 error code signals a freezer thermistor fault?",
     "E1 is the fresh food compartment thermistor; no freezer thermistor code is listed.",
     "Which FR-440 error code points to a fault in the fresh food compartment thermistor?", ["E1"], "fridge-manual"),
    ("How long should the FR-440 be unplugged before calling service about an E4 error?",
     "The 5-minute unplug instruction is given for E7 only.",
     "How long should the FR-440 stay unplugged when it shows E7?", ["5 minutes"], "fridge-manual"),
    ("How much does a replacement ALF-9 filter cartridge cost?",
     "The manual gives the part number and replacement interval, not a price.",
     "After how many litres dispensed should the ALF-9 cartridge be replaced?", ["1500 litres", "1500"], "fridge-manual"),
    ("Where is the model number label on the FR-440?",
     "Only the serial number's location is given.",
     "Where on the FR-440 is the serial number needed for warranty service?", ["inner left wall"], "fridge-manual"),
    ("How long does the FR-440 take to get back to its set point after a power cut?",
     "The 24-hour figure is for first installation; recovery after a power cut is not stated.",
     "How long after installation must the FR-440 run before food goes in?", ["24 hours"], "fridge-manual"),
    ("At what percentage of cartridge life does the FR-440 filter light turn red?",
     "Only the amber threshold is stated; there is no red state.",
     "At what percentage of cartridge life does the FR-440 filter light turn amber?", ["90 percent"], "fridge-manual"),
    # -- tenancy-agreement ---------------------------------------------------
    ("Who is responsible for repairing the water heater at Al Noor Tower?",
     "Major maintenance names structure and central air conditioning; minor names light fittings, handles and washers. Water heaters are in neither list.",
     "Under the Al Noor Tower contract, who pays for replacing tap washers?", ["tenant"], "tenancy-agreement"),
    ("How many days does the landlord have to complete a major repair at Al Noor Tower?",
     "The contract assigns major maintenance to the landlord but sets no deadline.",
     "What does the Al Noor Tower contract count as major maintenance?", ["structural repair", "central air conditioning"], "tenancy-agreement"),
    ("On what date is the second Al Noor Tower rent cheque due?",
     "The contract gives the number and size of cheques, not their dates.",
     "Into how many cheques is the Al Noor Tower rent divided?", ["four"], "tenancy-agreement"),
    ("What per-incident spending limit applies to the landlord's major maintenance?",
     "The AED 500 per-incident figure caps the tenant's minor maintenance; no landlord limit is set.",
     "What per-incident ceiling applies to the tenant's minor repairs at Al Noor Tower?", ["AED 500", "500"], "tenancy-agreement"),
    ("What agency commission is charged when the Al Noor Tower tenancy renews?",
     "The summary sheet gives the commission payable on signature; renewal commission is not mentioned.",
     "What letting agency commission applies to Unit 1204?", ["5 percent"], "tenancy-summary-sheet"),
    # -- insurance-policy ----------------------------------------------------
    ("Within how many days must a theft be reported to the police for a HomeGuard claim?",
     "The 30-day limit is for notifying the insurer; no deadline for the police report is set.",
     "Within how many days must a HomeGuard claim be notified?", ["30 days"], "insurance-policy"),
    ("How long does HomeGuard take to settle a claim?",
     "The schedule covers notification and documents, not settlement times.",
     "What reference does a HomeGuard theft claim require?", ["police report"], "insurance-policy"),
    ("What is the HomeGuard per-item limit for jewellery?",
     "AED 5,000 is the threshold for listing an item separately, not a jewellery limit; jewellery is not mentioned.",
     "What value triggers separate listing of an item on the HomeGuard schedule?", ["AED 5,000", "5,000"], "insurance-policy"),
    ("What is the annual premium on the HomeGuard contents policy?",
     "The schedule states cover limits and excesses, not the premium.",
     "What is the HomeGuard contents sum insured?", ["AED 150,000", "150,000"], "insurance-policy"),
    ("What is the single-item limit for portable electronics taken outside the home?",
     "Only an aggregate AED 10,000 limit is stated, not a per-item one.",
     "What aggregate limit applies to portable electronics taken out of the home?", ["AED 10,000", "10,000"], "insurance-policy"),
    # -- electricity-tariff --------------------------------------------------
    ("What is the Metro Utilities electricity deposit for a townhouse?",
     "Deposits are given for apartments and villas only.",
     "What electricity security deposit applies to a villa?", ["AED 2,000", "2,000"], "electricity-tariff"),
    ("What fee does Metro Utilities charge to disconnect an overdue account?",
     "Only the reconnection fee is stated.",
     "What does Metro Utilities charge to reconnect a disconnected supply?", ["AED 300", "300"], "electricity-tariff"),
    ("What does Metro Utilities charge to upgrade the capacity of an existing connection?",
     "Only the fee for a new residential connection is stated.",
     "What one-off fee applies to a new residential electricity connection?", ["AED 2,000", "2,000"], "electricity-tariff"),
    ("On what day of the month does Metro Utilities issue water bills?",
     "The schedule is for electricity only.",
     "On which day of the month are Metro Utilities electricity bills issued?", ["5th"], "electricity-tariff"),
    ("How long does Metro Utilities take to close an electricity account?",
     "The 45-day figure is for refunding the deposit after closure, not for closing the account.",
     "How soon after account closure is the electricity deposit refunded?", ["45 days"], "electricity-tariff"),
    # -- phone-plan ----------------------------------------------------------
    ("How much does a weekly roaming pass cost on Freedom 150?",
     "Only a daily roaming pass is offered.",
     "What does a Nova Mobile daily roaming pass cost?", ["AED 35"], "phone-plan"),
    ("What do outgoing calls cost on the Nova Mobile daily roaming pass?",
     "The pass includes incoming minutes; outgoing call charges are not stated.",
     "How many incoming call minutes come with the daily roaming pass?", ["60 minutes", "60 incoming"], "phone-plan"),
    ("What is the monthly cap on out-of-bundle voice charges for Freedom 150?",
     "The AED 200 cap applies to data; no cap is stated for voice.",
     "What is the monthly cap on out-of-bundle data charges for Freedom 150?", ["AED 200", "200"], "phone-plan"),
    ("How much does Nova Mobile charge to replace an eSIM?",
     "Only a SIM replacement fee is stated; eSIMs are not mentioned.",
     "What is the Freedom 150 SIM replacement fee?", ["AED 25"], "phone-plan"),
    ("What is roaming data charged at once the daily pass's 1 GB is used up?",
     "The AED 2 per MB rate applies to roaming without a pass; usage beyond the pass allowance is not addressed.",
     "How much data does the Nova Mobile daily roaming pass include?", ["1 GB"], "phone-plan"),
    # -- laptop-warranty -----------------------------------------------------
    ("How long is the Vertex V14 power adapter covered for?",
     "Only the laptop hardware and battery coverage periods are given; the adapter is not.",
     "For how many months does Vertex cover V14 hardware from purchase?", ["12-month", "12 month", "12 months"], "laptop-warranty"),
    ("How long is the V14 battery covered under the Vertex extended warranty?",
     "The extension takes total coverage to 36 months, but battery cover under it is not stated.",
     "How many charge cycles does the standard V14 battery warranty cover?", ["500 charge cycles", "500"], "laptop-warranty"),
    ("What is the turnaround for Vertex express warranty service?",
     "Only a standard turnaround is stated; no express tier exists in the statement.",
     "How many working days does standard Vertex warranty repair take?", ["7 working days"], "laptop-warranty"),
    ("What does Vertex charge for an out-of-warranty screen replacement?",
     "Only the diagnostic fee is stated; repair prices are not.",
     "How much is an out-of-warranty diagnostic assessment on a Vertex laptop?", ["AED 120", "120"], "laptop-warranty"),
    # -- library-rules -------------------------------------------------------
    ("How many items can library staff borrow at once?",
     "Limits are given for foundation, undergraduate and postgraduate students only.",
     "What is the borrowing limit for undergraduate students?", ["8 items", "eight", "up to 8"], "library-rules"),
    ("What is the penalty for not collecting a reserved library item?",
     "The hold period is stated; no penalty for non-collection is.",
     "For how many working days is a reserved library item kept after notification?", ["3 working days"], "library-rules"),
    ("What is the fine for leaving a group study room booking unclaimed?",
     "Unclaimed bookings are released after 15 minutes; no fine is stated.",
     "After how many minutes is an unclaimed group study room booking released?", ["15 minutes"], "library-rules"),
    ("How many group study room bookings can a reader hold at the same time?",
     "The 5-item limit is for reservations of library items; study rooms are limited by hours per day only.",
     "What is the maximum number of active item reservations a reader may hold?", ["5 active reservations", "5 reservations", "five", "maximum of 5"], "library-rules"),
    # -- fee-schedule --------------------------------------------------------
    ("When is the UFP registration fee due?",
     "The amount is stated; the due date is given only for tuition instalments.",
     "How much is the UFP registration fee per academic year?", ["AED 1,500", "1,500"], "fee-schedule"),
    ("How much of the registration fee is refunded if I withdraw before teaching starts?",
     "The 90 percent refund applies to tuition paid; registration fee refunds are not addressed.",
     "What share of tuition paid is refunded on withdrawal before teaching starts?", ["90 percent"], "fee-schedule"),
    ("How much does it cost to resubmit a failed PHY-104 laboratory report?",
     "The AED 400 fee is an examination resit fee per module; resubmitting coursework is not addressed in either document.",
     "What is the UFP examination resit fee per module?", ["AED 400", "400"], "fee-schedule"),
    # -- ufp-handbook-2026 ---------------------------------------------------
    ("What mark must I get on PHY-104 coursework alone to pass the module?",
     "The 40 percent pass mark is for the module; no component pass mark is set.",
     "What overall mark is needed to pass PHY-104?", ["40 percent"], "ufp-handbook-2026"),
    ("How long is the PHY-104 resit examination?",
     "The 2-hour duration is for the final examination; the resit's length is not stated.",
     "How many times may a student who fails PHY-104 resit the written exam?", ["once"], "ufp-handbook-2026"),
]

# (question, expect_any, expect_doc) - answerable, phrased fresh, several on
# facts the main set never asks about.
SLICE_J_ANSWERABLE: list[tuple[str, list[str], str]] = [
    ("When is the second UFP tuition instalment due?", ["10 January 2027"], "fee-schedule"),
    ("Is the UFP application fee refundable?", ["non-refundable", "not refundable"], "fee-schedule"),
    ("What must a student submit to start a UFP tuition refund?", ["written withdrawal request", "in writing", "written request"], "fee-schedule"),
    ("How many local SMS does the Freedom 150 plan include?", ["unlimited"], "phone-plan"),
    ("How long is a Nova Mobile daily roaming pass valid for?", ["24 hours"], "phone-plan"),
    ("Can short-loan library items be renewed?", ["cannot be renewed", "can't be renewed", "not be renewed", "not renewable", "cannot renew"], "library-rules"),
    ("Is there a cap on overdue fines for short-loan library items?", ["no cap", "not capped", "uncapped"], "library-rules"),
    ("Under what condition may a standard library loan be renewed?", ["reserved"], "library-rules"),
    ("Which components make up the FR-440's sealed cooling system?", ["compressor", "condenser", "evaporator"], "fridge-manual"),
    ("Does using a third-party water filter affect the FR-440 warranty?", ["non-arcticline", "not cover", "void"], "fridge-manual"),
    ("Is damage from a non-Vertex charger covered by the V14 warranty?", ["exclude", "not cover"], "laptop-warranty"),
    ("What do I need to obtain before Vertex warranty service can begin?", ["support reference number"], "laptop-warranty"),
    ("Is the Vertex diagnostic fee refunded if I go ahead with the repair?", ["credited"], "laptop-warranty"),
    ("Does the Vertex warranty cover lost data?", ["not covered", "not cover", "exclude"], "laptop-warranty"),
    ("How many consumption slabs does the Metro Utilities residential tariff have?", ["three", "3 slabs"], "electricity-tariff"),
    ("Does the HomeGuard policy cover property used for business?", ["exclude", "not cover"], "insurance-policy"),
    ("Which minor repairs does the Al Noor Tower contract list as the tenant's job?", ["light fittings", "door handles", "tap washers"], "tenancy-agreement"),
    ("How long is the Al Noor Tower tenancy term?", ["12 months", "twelve-month", "twelve months", "12-month"], "tenancy-agreement"),
    ("How are the three PHY-104 laboratory reports weighted against each other?", ["equal weight", "equally"], "ufp-handbook-2026"),
    ("Does a documented absence count against the PHY-104 laboratory attendance requirement?", ["excluded", "does not count", "doesn't count", "not counted"], "ufp-handbook-2026"),
]
SLICE_J_OUT = REPO / "data" / "eval" / "eval_slice_j.jsonl"


def build_slice_j() -> list[dict]:
    items: list[dict] = []
    for i, (q, note, _, _, _) in enumerate(SLICE_J_ADJACENT, start=1):
        items.append({"id": f"ju{i:03d}", "kind": "unanswerable", "question": q, "note": note,
                      "lang": "en", "tags": ["adjacent-fact"]})
    for i, (_, _, q, expect, doc) in enumerate(SLICE_J_ADJACENT, start=1):
        items.append({"id": f"js{i:03d}", "kind": "answerable", "question": q, "expect_any": expect,
                      "expect_doc": doc, "lang": "en", "tags": ["adjacent-sibling"]})
    for i, (q, expect, doc) in enumerate(SLICE_J_ANSWERABLE, start=1):
        items.append({"id": f"ja{i:03d}", "kind": "answerable", "question": q, "expect_any": expect,
                      "expect_doc": doc, "lang": "en", "tags": ["fresh"]})
    return items


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


# ADR-013: the true answers to the prior-leak probes. Strict systems are still
# scored on refusing them; a system with a labelled general-knowledge fallback
# is scored on getting them right. Personal-detail unanswerables get no entry:
# for those the only right general answer is "I don't know".
GENERAL_FACTS: dict[str, list[str]] = {
    "What is the capital of Burkina Faso?": ["Ouagadougou"],
    "Who won the 2024 UEFA European Championship?": ["Spain"],
    "What is the boiling point of water in kelvin?": ["373"],
    "What is the speed of light in metres per second?": ["299792458", "299,792,458", "3 x 10", "3 × 10", "300,000,000", "300000000"],
    "Who wrote the Principia Mathematica?": ["Newton", "Whitehead"],
    "What is the chemical symbol for tungsten?": ["symbol for tungsten is W", "is W.", "is W ", "(W)", "**W**", "\"W\"", "'W'"],
    "How many millimetres are in an inch?": ["25.4"],
    "What is the largest country in Africa by area?": ["Algeria"],
    "In what year did the Berlin Wall fall?": ["1989"],
    "What is the acceleration due to gravity at sea level?": ["9.8"],
    "What is the currency of Japan?": ["yen"],
    "كم عدد سكان الإمارات؟": ["مليون", "million"],
}


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
                **({"expect_general": GENERAL_FACTS[q]} if q in GENERAL_FACTS else {}),
            }
        )
    for i, (q, docs, outcome, note) in enumerate(CONFLICT, start=1):
        items.append(
            {
                "id": f"c{i:03d}",
                "kind": "conflict",
                "question": q,
                "expect_docs": docs,
                "expect_outcome": outcome,
                "note": note,
                "lang": "ar" if is_arabic(q) else "en",
                "tags": [outcome],
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
        if item["kind"] == "conflict":
            if len(item.get("expect_docs", [])) < 2:
                problems.append(f"{item['id']} must name at least two disagreeing documents")
            if item.get("expect_outcome") not in {"conflict", "version_skew"}:
                problems.append(f"{item['id']} needs expect_outcome conflict|version_skew")
            for doc in item.get("expect_docs", []):
                if doc not in present:
                    problems.append(f"{item['id']} names missing doc {doc}")
    return problems


def validate_slice(slice_items: list[dict]) -> list[str]:
    """The slice is checked together with the main set, so no id or question is
    shared, plus one check the main set leaves to tests: every answerable item's
    fact is actually in its document."""
    problems = []
    texts = {p.stem: _normalise(p.read_text(encoding="utf-8")) for p in CORPUS.glob("*.md")}
    for item in slice_items:
        if not item["id"].startswith("j"):
            problems.append(f"{item['id']} is in the fresh slice but not prefixed 'j'")
        if item["kind"] == "answerable":
            doc = texts.get(item["expect_doc"], "")
            if not any(_normalise(e) in doc for e in item["expect_any"]):
                problems.append(f"{item['id']} expects a fact not found in {item['expect_doc']}")
    return problems


def _normalise(s: str) -> str:
    return " ".join(s.lower().replace(",", "").split())


def _write(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8")


def main() -> int:
    items = build()
    slice_j = build_slice_j()
    if problems := validate(items + slice_j) + validate_slice(slice_j):
        for p in problems:
            print(f"INVALID: {p}", file=sys.stderr)
        return 1

    _write(OUT, items)
    _write(SLICE_J_OUT, slice_j)
    print(f"wrote {len(slice_j)} items -> {SLICE_J_OUT.relative_to(REPO)} (fresh held-out slice, E25)")

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

    for kind in ("answerable", "unanswerable", "out_of_scope", "conflict"):
        n = kinds[kind]
        if not n:
            continue
        hw = wilson(n // 2, n).half_width
        print(f"  {kind:14s} n={n:3d} -> worst-case 95% CI half-width ±{hw:.1%}")
    print(f"  (±10pp needs {required_n(0.10)} items per slice, ±5pp needs {required_n(0.05)})")
    return write_slice_k(items)


# ---------------------------------------------------------------------------
# Slice k - the amin-2 checkpoint-selection slice (docs/TRAINING.md, Round 2)
# ---------------------------------------------------------------------------
# Used for one thing only: choosing which amin-2 checkpoint to keep, in hybrid
# mode. Never trained on, never reported as a benchmark; slice j stays the
# final one-time test. Written blind, without looking at any model's output.
# It must share no question with the training items, the main set or slice j,
# by exact match or by any 6-gram; validate_slice_k() and tests/test_eval.py
# enforce that. Pair n is ku{n} (trap) and ks{n} (its answerable sibling).
# (trap question, why it cannot be answered, sibling question, sibling expect_any, doc)
SLICE_K_ADJACENT: list[tuple[str, str, str, list[str], str]] = [
    # -- fridge-manual -------------------------------------------------------
    ("What fresh food temperature should the FR-440 hold in holiday mode?",
     "Only the normal fresh food setting is given; no holiday mode is mentioned.",
     "What is the standard FR-440 fresh food compartment setting in degrees Celsius?", ["4 degrees", "4°C", "4 °C"], "fridge-manual"),
    ("Which error code does the FR-440 show if the defrost heater is shorted?",
     "E4 is an open defrost heater circuit; a short is not listed.",
     "Which FR-440 code means the defrost heater circuit is open?", ["E4"], "fridge-manual"),
    ("How cold does the FR-440 freezer go in fast-freeze mode?",
     "Only the recommended freezer setting is given; fast-freeze is not mentioned.",
     "What FR-440 freezer setting does ArcticLine recommend?", ["minus 18", "-18"], "fridge-manual"),
    ("How many litres per minute does the FR-440 water dispenser deliver?",
     "The manual gives the filter's litre lifetime, not a flow rate.",
     "Every how many months does ArcticLine want the ALF-9 cartridge changed?", ["6 months", "six months"], "fridge-manual"),
    ("Which code does the FR-440 display when a door is left open?",
     "Codes E1, E4 and E7 are listed; none is a door alarm.",
     "What fault does code E7 point to on the FR-440?", ["communication failure"], "fridge-manual"),
    # -- tenancy-agreement ---------------------------------------------------
    ("What interest is paid on the Unit 1204 security deposit?",
     "The contract sets the deposit and its refund window, not any interest.",
     "Within how many days of handover is the Al Noor Tower deposit returned?", ["30 days"], "tenancy-agreement"),
    ("At what time on 1 March 2026 are the Unit 1204 keys handed over?",
     "Only the start date is given.",
     "On what date does the Unit 1204 tenancy commence?", ["1 March 2026"], "tenancy-agreement"),
    ("To whom should the Unit 1204 rent cheques be made payable?",
     "The contract gives the number and value of the cheques, not the payee.",
     "What is each of the four Unit 1204 rent cheques worth?", ["19,500"], "tenancy-agreement"),
    ("How should the tenant report a central air conditioning fault at Unit 1204?",
     "The contract assigns the system to the landlord but sets no reporting procedure.",
     "Whose responsibility is the central air conditioning at Unit 1204?", ["landlord"], "tenancy-agreement"),
    ("What penalty does the Unit 1204 tenant pay for leaving before 28 February 2027?",
     "Early termination is not addressed; only notice of non-renewal is.",
     "On what date does the Unit 1204 contract expire?", ["28 February 2027"], "tenancy-agreement"),
    # -- insurance-policy ----------------------------------------------------
    ("What no-claims discount does HomeGuard give after a claim-free year?",
     "The schedule states limits and excesses; no discount is mentioned.",
     "How much is the standard HomeGuard excess per claim?", ["AED 750", "750"], "insurance-policy"),
    ("What phone number do I call to notify HomeGuard of a claim?",
     "Only the notification deadline is given, not a contact number.",
     "How many days after an incident does HomeGuard allow for notifying a claim?", ["30 days"], "insurance-policy"),
    ("How much of the escape of water excess is waived if a leak detector is fitted?",
     "A single escape of water excess is stated, with no waiver.",
     "What excess does HomeGuard charge on an escape of water claim?", ["AED 1,500", "1,500"], "insurance-policy"),
    # -- electricity-tariff --------------------------------------------------
    ("What does Metro Utilities charge for a meter reading on request?",
     "Only the monthly meter charge is stated.",
     "What monthly meter charge applies to every Metro Utilities residential account?", ["AED 10"], "electricity-tariff"),
    ("How many hours after arrears are paid is a disconnected supply restored?",
     "The disconnection threshold and reconnection fee are given; no restoration time is.",
     "After how many days overdue can Metro Utilities cut off a home?", ["60 days"], "electricity-tariff"),
    ("What is the Metro Utilities peak-hour electricity rate?",
     "The tariff is three consumption slabs; there is no time-of-use rate.",
     "What does the top residential consumption slab cost per kWh?", ["38 fils"], "electricity-tariff"),
    ("What rate per kWh applies to charging an electric car at home?",
     "No electric vehicle rate exists; only the three residential slabs.",
     "What does Metro Utilities charge per kWh in the middle residential slab?", ["28 fils"], "electricity-tariff"),
    ("What interest does Metro Utilities pay on an electricity security deposit?",
     "The deposit amounts and refund window are given, not interest.",
     "How large is the Metro Utilities security deposit for an apartment?", ["AED 1,000", "1,000"], "electricity-tariff"),
    # -- phone-plan ----------------------------------------------------------
    ("What does Nova Mobile charge to upgrade from Freedom 150 to a bigger plan mid-contract?",
     "Only early termination is priced; upgrades are not mentioned.",
     "How is the Freedom 150 early exit fee worked out?", ["50 percent"], "phone-plan"),
    ("What data speed applies on Freedom 150 once the out-of-bundle cap is hit?",
     "The cap limits charges; throttling speeds are not stated.",
     "What does Freedom 150 charge per MB for local data over the allowance?", ["0.50"], "phone-plan"),
    ("How many devices may share Freedom 150 data through a hotspot?",
     "Only the data allowance is given; tethering is not addressed.",
     "How much local data comes with Freedom 150 each month?", ["20 GB"], "phone-plan"),
    ("What does Nova Mobile charge for sending an SMS while roaming?",
     "Roaming covers data and incoming calls only; SMS abroad is not priced.",
     "What does roaming data cost per MB without a pass?", ["AED 2", "2 per MB"], "phone-plan"),
    ("What will Freedom 150 cost per month after the 12-month minimum term ends?",
     "The term and the current price are given; no post-term price is.",
     "How long is the Freedom 150 minimum term?", ["12 months"], "phone-plan"),
    # -- laptop-warranty -----------------------------------------------------
    ("What does Vertex charge to replace a cracked V14 screen?",
     "Cracked displays are excluded; no repair price is given.",
     "Name two kinds of damage the V14 limited warranty excludes.", ["liquid damage", "cracked display", "power adapter"], "laptop-warranty"),
    ("What is the rated battery capacity of the Vertex V14 in watt-hours?",
     "Only the 80 percent defect threshold is given, not the rating.",
     "Below what share of rated capacity is a V14 battery treated as defective?", ["80 percent"], "laptop-warranty"),
    ("For how many days is a Vertex support reference number valid?",
     "The statement says where the number comes from, not how long it lasts.",
     "Where does a Vertex customer obtain a support reference number?", ["online"], "laptop-warranty"),
    ("How long is a completed Vertex warranty repair itself guaranteed?",
     "Turnaround is stated; no guarantee on repairs is.",
     "How many working days does a Vertex repair take once the unit reaches the service centre?", ["7 working days"], "laptop-warranty"),
    # -- library-rules -------------------------------------------------------
    ("How many days before a standard loan is due does the library send a reminder?",
     "The loan period is given; reminders are not mentioned.",
     "How many days is a standard Central Campus Library loan?", ["14 days"], "library-rules"),
    ("Up to how many people can use one group study room at once?",
     "A minimum of 3 occupants is set; no maximum is.",
     "How many people must be present to use a group study room?", ["3 occupants", "three", "minimum of 3", "3 people"], "library-rules"),
    ("How far in advance can a group study room be booked?",
     "Daily hours per reader are limited; advance booking windows are not stated.",
     "How many hours a day may one reader book group study rooms?", ["3 hours"], "library-rules"),
    ("How many short-loan items may a foundation student hold at the same time?",
     "There is an overall borrowing limit but no separate short-loan limit.",
     "For how many days is a short-loan item issued?", ["3 days"], "library-rules"),
    # -- fee-schedule --------------------------------------------------------
    ("How much is the UFP graduation fee?",
     "Application, registration, resit and ID card fees are listed; no graduation fee.",
     "What does a replacement UFP student identity card cost?", ["AED 75", "75"], "fee-schedule"),
    ("By what date must the UFP application fee be paid?",
     "The fee amount is given; only tuition instalments have due dates.",
     "What does it cost to apply to the University Foundation Programme?", ["AED 500", "500"], "fee-schedule"),
    ("What is the UFP annual tuition for 2027/28?",
     "The schedule covers 2026/27 only.",
     "What is the annual UFP tuition for 2026/27?", ["52,000"], "fee-schedule"),
    ("What tuition discount do siblings get on the UFP?",
     "No discounts are mentioned.",
     "In how many instalments is UFP tuition paid?", ["two", "2 instalments"], "fee-schedule"),
    ("What does the UFP charge for an official transcript?",
     "Transcripts are not among the listed charges.",
     "By what date must the first UFP tuition instalment be paid?", ["15 August 2026"], "fee-schedule"),
    # -- ufp-handbook-2026 ---------------------------------------------------
    ("Which calculator models are approved for the PHY-104 exam?",
     "Only the type of calculator is given, not a model list.",
     "What type of calculator may be used in the PHY-104 exam?", ["non-programmable"], "ufp-handbook-2026"),
    ("What is the deadline for handing in PHY-104 laboratory reports?",
     "The number and weighting of the reports are given, not deadlines.",
     "How many laboratory reports does PHY-104 coursework comprise?", ["three", "3 laboratory reports", "3 lab"], "ufp-handbook-2026"),
    ("In which month does the PHY-104 resit sitting take place?",
     "The resit cap and number of attempts are given; no timing is.",
     "To what mark is a PHY-104 resit capped?", ["40 percent"], "ufp-handbook-2026"),
    ("What documentation is accepted to excuse a PHY-104 laboratory absence?",
     "Documented absence is excluded from the calculation, but acceptable documents are not listed.",
     "What share of PHY-104 laboratory sessions must a student attend to sit the final exam?", ["80 percent"], "ufp-handbook-2026"),
]

# (question, expect_any, expect_doc) - answerable, phrased fresh. Facts the two
# tenancy documents or the two handbooks disagree on are left out: those are
# conflict items, not plain answerables.
SLICE_K_ANSWERABLE: list[tuple[str, list[str], str]] = [
    ("For how many months is the FR-440 compressor covered?", ["60 months", "60-month"], "fridge-manual"),
    ("What do I need to show ArcticLine to get FR-440 warranty service?", ["proof of purchase"], "fridge-manual"),
    ("Will ArcticLine honour the FR-440 warranty if I damaged the fridge moving it myself?", ["transport"], "fridge-manual"),
    ("What is the first thing to do when the FR-440 display shows E7?", ["unplug"], "fridge-manual"),
    ("What does clause 7.2 of the Al Noor Tower contract provide?", ["renews automatically", "renew automatically"], "tenancy-agreement"),
    ("Is a broken door handle at Unit 1204 for the landlord or the tenant to fix?", ["tenant"], "tenancy-agreement"),
    ("What may be deducted from the Al Noor Tower deposit at handover?", ["fair wear and tear"], "tenancy-agreement"),
    ("Which clause of the Al Noor Tower contract deals with the security deposit?", ["11.1", "clause 11"], "tenancy-agreement"),
    ("When is the letting agency commission on Unit 1204 due?", ["on signature", "at signature", "upon signature"], "tenancy-summary-sheet"),
    ("Does HomeGuard pay out when a washing machine simply breaks down?", ["mechanical breakdown"], "insurance-policy"),
    ("Up to what amount is cash protected under HomeGuard?", ["AED 2,000", "2,000"], "insurance-policy"),
    ("If my laptop is stolen at a café, up to how much does HomeGuard cover portable electronics?", ["AED 10,000", "10,000"], "insurance-policy"),
    ("What excess would I pay on a HomeGuard claim for a burst pipe?", ["AED 1,500", "1,500"], "insurance-policy"),
    ("If my apartment uses 3,000 kWh in a month, what rate applies to the units above 2,000?", ["28 fils"], "electricity-tariff"),
    ("How long after issue is a Metro Utilities bill due?", ["21 days"], "electricity-tariff"),
    ("What percentage penalty is added when a Metro Utilities bill is paid late?", ["2 percent"], "electricity-tariff"),
    ("Does the AED 10 meter charge still apply in a month with zero consumption?", ["regardless of consumption", "every residential account", "yes"], "electricity-tariff"),
    ("What does Metro Utilities charge per kWh on a home's first 2,000 kWh in a month?", ["23 fils"], "electricity-tariff"),
    ("Does Freedom 150 come with unlimited local texts?", ["unlimited"], "phone-plan"),
    ("Beyond 500 minutes, what is the per-minute local call charge on Freedom 150?", ["30 fils"], "phone-plan"),
    ("If I cancel Freedom 150 early, how is the termination fee calculated?", ["50 percent"], "phone-plan"),
    ("Will leftover Freedom 150 data be added to next month's allowance?", ["does not roll over", "not roll over", "doesn't roll over", "won't roll over", "not carry over", "does not carry"], "phone-plan"),
    ("Is a V14 with a tampered serial number still under warranty?", ["removed or altered", "not covered", "excluded", "excludes"], "laptop-warranty"),
    ("Does the Vertex warranty cover software problems?", ["not covered", "does not cover", "excluded", "excludes"], "laptop-warranty"),
    ("With Vertex's extended warranty, how many months of total coverage do I get?", ["36 months", "36-month"], "laptop-warranty"),
    ("How many days after buying a V14 do I have to add extended cover?", ["30 days"], "laptop-warranty"),
    ("How long can a postgraduate keep a standard loan before it is due?", ["14 days"], "library-rules"),
    ("What is the most I can be fined for one overdue standard library item?", ["AED 50", "50"], "library-rules"),
    ("How much is charged for each day a short-loan item is late?", ["AED 10", "10 per item"], "library-rules"),
    ("Which readers may borrow up to 15 items from the Central Campus Library?", ["postgraduate"], "library-rules"),
    ("How much does the January UFP tuition instalment come to?", ["26,000"], "fee-schedule"),
    ("What percentage of tuition is refunded for withdrawing in week two of teaching?", ["50 percent"], "fee-schedule"),
    ("How much does a late UFP tuition payment cost me?", ["AED 250", "250"], "fee-schedule"),
    ("How soon after a written withdrawal request are UFP refunds paid?", ["30 working days"], "fee-schedule"),
    ("Who supplies the data and formula booklet in the PHY-104 exam?", ["provided in the examination hall", "provided"], "ufp-handbook-2026"),
    ("What minimum module mark passes PHY-104 in 2026/27?", ["40 percent"], "ufp-handbook-2026"),
    ("كم شهراً يغطي الضمان نظام التبريد المغلق في الثلاجة؟", ["60"], "ar-fridge-summary"),
    ("ماذا يعني الرمز E4 في الثلاجة؟", ["سخان", "defrost"], "ar-fridge-summary"),
    ("كم قيمة كل قسط من الرسوم الدراسية للبرنامج التأسيسي؟", ["26000"], "ar-fee-summary"),
    ("خلال كم يوماً يُرد مبلغ التأمين بعد تسليم الوحدة؟", ["30"], "ar-tenancy-summary"),
]

# (question, expect_general) - no household document answers these; in hybrid
# mode the right answer is the labelled general fact.
SLICE_K_GENERAL: list[tuple[str, list[str]]] = [
    ("What is the capital of Mongolia?", ["Ulaanbaatar", "Ulan Bator"]),
    ("How many bones are in the adult human body?", ["206"]),
    ("Which element has atomic number 26?", ["iron"]),
    ("Who painted the ceiling of the Sistine Chapel?", ["Michelangelo"]),
    ("Roughly how many kilometres are in a mile?", ["1.6"]),
    ("Who developed the theory of general relativity?", ["Einstein"]),
    ("What is the official currency of Saudi Arabia?", ["riyal"]),
    ("How many grams are in a kilogram?", ["1000"]),
    ("How many sides does an octagon have?", ["eight", "8"]),
    ("Which metal is liquid at room temperature?", ["mercury"]),
    ("Who wrote the novel Pride and Prejudice?", ["Austen"]),
    ("What is the hardest natural substance?", ["diamond"]),
    ("How many hours are in a week?", ["168"]),
    ("What is the capital of Kenya?", ["Nairobi"]),
    ("Which organ pumps blood around the human body?", ["heart"]),
    ("What is the largest planet in the solar system?", ["Jupiter"]),
    ("Who composed the Moonlight Sonata?", ["Beethoven"]),
    ("What is the capital of Oman?", ["Muscat"]),
    ("ما هي عاصمة اليابان؟", ["طوكيو", "Tokyo"]),
    ("ما هي أكبر صحراء حارة في العالم؟", ["الكبرى", "Sahara"]),
]

# Personal details no document records. A general answer must decline, not guess.
SLICE_K_PERSONAL: list[str] = [
    "What is my Nova Mobile phone number?",
    "How much was my last electricity bill?",
    "What is my Metro Utilities account number?",
    "On what date did I buy my Vertex V14?",
    "What is the serial number of my FR-440?",
    "What grade did I get on my last PHY-104 lab report?",
    "What is my student ID number?",
    "Which library books do I currently have on loan?",
    "How much data have I used this month on my phone plan?",
    "What is the name of my letting agent at Al Noor Tower?",
    "Have I paid my second tuition instalment yet?",
    "What is the Wi-Fi password for our flat?",
    "When does my HomeGuard policy renew?",
    "What is my landlord's phone number?",
    "How many of our rent cheques have cleared so far?",
    "On which day did I last replace the fridge water filter?",
    "What time is my doctor's appointment next week?",
    "How much did my insurance claim for the stolen bike pay out?",
    "Who is my PHY-104 lab partner?",
    "كم رصيدي في حساب الكهرباء؟",
]
SLICE_K_OUT = REPO / "data" / "eval" / "eval_slice_k.jsonl"
SLICE_J_OUT = REPO / "data" / "eval" / "eval_slice_j.jsonl"
SLICE_J_BRANCH = "claude/peaceful-liskov-6728c3"


def build_slice_k() -> list[dict]:
    items: list[dict] = []

    def lang(q: str) -> str:
        return "ar" if is_arabic(q) else "en"

    for i, (q, note, _, _, _) in enumerate(SLICE_K_ADJACENT, start=1):
        items.append({"id": f"ku{i:03d}", "kind": "unanswerable", "question": q, "note": note,
                      "lang": lang(q), "tags": ["adjacent-fact"]})
    for i, (_, _, q, expect, doc) in enumerate(SLICE_K_ADJACENT, start=1):
        items.append({"id": f"ks{i:03d}", "kind": "answerable", "question": q, "expect_any": expect,
                      "expect_doc": doc, "lang": lang(q), "tags": ["adjacent-sibling"]})
    for i, (q, expect, doc) in enumerate(SLICE_K_ANSWERABLE, start=1):
        items.append({"id": f"ka{i:03d}", "kind": "answerable", "question": q, "expect_any": expect,
                      "expect_doc": doc, "lang": lang(q), "tags": ["fresh"]})
    for i, (q, facts) in enumerate(SLICE_K_GENERAL, start=1):
        items.append({"id": f"kg{i:03d}", "kind": "unanswerable", "question": q,
                      "note": "General knowledge; no household document covers it.",
                      "expect_general": facts, "lang": lang(q), "tags": ["general"]})
    for i, q in enumerate(SLICE_K_PERSONAL, start=1):
        items.append({"id": f"kp{i:03d}", "kind": "unanswerable", "question": q,
                      "note": "A personal detail no document records; a general answer must decline.",
                      "lang": lang(q), "tags": ["personal"]})
    return items


def question_words(q: str) -> list[str]:
    return re.findall(r"\w+", q.lower())


def question_ngrams(q: str, n: int = 6) -> set[tuple[str, ...]]:
    w = question_words(q)
    return {tuple(w[i : i + n]) for i in range(len(w) - n + 1)}


def slice_j_questions() -> list[str] | None:
    """Slice j's questions: from its file once merged, else from its branch.
    None when neither is available."""
    if SLICE_J_OUT.exists():
        text = SLICE_J_OUT.read_text(encoding="utf-8")
    else:
        try:
            text = subprocess.run(
                ["git", "show", f"{SLICE_J_BRANCH}:data/eval/eval_slice_j.jsonl"],
                cwd=REPO, capture_output=True, text=True, check=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            return None
    return [json.loads(line)["question"] for line in text.splitlines() if line.strip()]


def training_questions() -> list[str]:
    """The training items, regenerated (they are gitignored), plus the file on
    disk when present in case it was built with another seed."""
    sys.path.insert(0, str(REPO))
    from amin.config import settings
    from amin.train import corpus

    qs = [i["question"] for i in corpus.build(seed=7)[1]]
    on_disk = settings.train_path / "items.jsonl"
    if on_disk.exists():
        qs += [json.loads(line)["question"] for line in on_disk.read_text(encoding="utf-8").splitlines() if line.strip()]
    return qs


def overlaps(slice_items: list[dict], others: dict[str, list[str]]) -> list[str]:
    """Every slice question that matches another set exactly or shares a 6-gram with it."""
    problems = []
    for name, questions in others.items():
        exact = {" ".join(question_words(q)) for q in questions}
        grams = set().union(*(question_ngrams(q) for q in questions)) if questions else set()
        for item in slice_items:
            q = item["question"]
            if " ".join(question_words(q)) in exact:
                problems.append(f"{item['id']} repeats a question in {name}")
            elif shared := question_ngrams(q) & grams:
                problems.append(f"{item['id']} shares {' '.join(sorted(shared)[0])!r} with {name}")
    return problems


def validate_slice_k(slice_items: list[dict], main_items: list[dict]) -> list[str]:
    problems = validate(main_items + slice_items)
    texts = {p.stem: " ".join(p.read_text(encoding="utf-8").lower().replace(",", "").split())
             for p in CORPUS.glob("*.md")}
    for item in slice_items:
        if not item["id"].startswith("k"):
            problems.append(f"{item['id']} is in slice k but not prefixed 'k'")
        if item["kind"] == "answerable":
            doc = texts.get(item["expect_doc"], "")
            if not any(" ".join(e.lower().replace(",", "").split()) in doc for e in item["expect_any"]):
                problems.append(f"{item['id']} expects a fact not found in {item['expect_doc']}")
    others = {"the main set": [i["question"] for i in main_items], "training items": training_questions()}
    if (j := slice_j_questions()) is not None:
        others["slice j"] = j
    return problems + overlaps(slice_items, others)


def write_slice_k(main_items: list[dict]) -> int:
    slice_k = build_slice_k()
    if problems := validate_slice_k(slice_k, main_items):
        for p in problems:
            print(f"INVALID (slice k): {p}", file=sys.stderr)
        return 1
    SLICE_K_OUT.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in slice_k) + "\n", encoding="utf-8")
    print(f"wrote {len(slice_k)} items -> {SLICE_K_OUT.relative_to(REPO)} (checkpoint selection only, amin-2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
