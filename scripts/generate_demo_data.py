"""Generate the NEXUS synthetic demo dataset (NO real personal data).

Outputs (committed, deterministic):
  data/demo/transactions.csv      18 months, recurring + one-off + seeded anomalies
  data/demo/subscriptions.csv     ground-truth recurring schedule
  data/demo/documents/*.pdf|txt   realistic personal documents
  data/demo/messages/*.txt        one suspicious, one normal message
  data/demo/eval_set.json         RAG evaluation ground truth

Dates are anchored to the project timeframe (today ≈ 2026-09-17) so the
demo deadlines/renewals line up with the dashboard.
"""
from __future__ import annotations

import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "demo"
DOCS = DEMO / "documents"
MSGS = DEMO / "messages"

TODAY = date(2026, 9, 17)
RNG = random.Random(42)

# ── PDF helper ───────────────────────────────────────────────────────────


def make_pdf(path: Path, title: str, lines: list[str]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Heading1"], fontSize=15)
    body = ParagraphStyle("b", parent=styles["BodyText"], fontSize=10.5, leading=15)
    story = [Paragraph(title, h), Spacer(1, 0.4 * cm)]
    for ln in lines:
        story.append(Paragraph(ln, body))
        story.append(Spacer(1, 0.25 * cm))
    doc.build(story)
    print(f"  pdf  {path.name}")


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    MSGS.mkdir(parents=True, exist_ok=True)

    # ── documents ────────────────────────────────────────────────────────
    print("Generating documents...")
    make_pdf(DOCS / "insurance_policy.pdf", "Sentinel Insurance — Policy Summary", [
        "Policy Number: NEX-4471",
        "Policyholder: Demo User",
        "Provider: Sentinel Insurance Ltd.",
        "Plan: Comprehensive Health, Sum Assured INR 10,00,000.",
        "Coverage start date: 14 March 2026.",
        "The policy expires on 14 March 2027, unless renewed.",
        "The annual premium is INR 18,500, payable yearly.",
        "The renewal premium payment is due on 25 September 2026.",
        "Renewal window: policyholders may renew up to 30 days before expiry.",
        "Claims are settled directly to the bank account on file.",
    ])
    make_pdf(DOCS / "electricity_bill.pdf", "City Power — Electricity Bill", [
        "Consumer Number: 4471-8890",
        "Provider: City Power Distribution Co.",
        "Billing period: 1 August 2026 to 31 August 2026.",
        "Units consumed: 210 units.",
        "Amount due: INR 2,340.",
        "Due date: 27 September 2026.",
        "Late fee of INR 50 per day applies after the due date.",
        "Please pay by the due date to avoid disconnection notice.",
    ])
    make_pdf(DOCS / "rental_agreement.pdf", "Residential Rental Agreement", [
        "This rental agreement is made between the Landlord and the Tenant, Demo User.",
        "The lease term starts on 1 January 2026 and ends on 31 December 2026.",
        "The monthly rent is INR 22,000, payable by the 1st of each month.",
        "A refundable security deposit of INR 66,000 was paid on 1 January 2026.",
        "Either party may terminate the lease with 60 days written notice.",
        "The renewal notice must be given by 1 November 2026.",
        "If the tenant cancels within the notice window, a cancellation fee of one month rent applies.",
        "Maintenance of common areas is included in the rent.",
    ])
    make_pdf(DOCS / "travel_booking.pdf", "SkyWings Air — Booking Confirmation", [
        "Booking Reference: SK-99231",
        "Passenger: Demo User",
        "Route: Delhi (DEL) to Goa (GOI).",
        "The flight departs on 15 November 2026 at 09:40.",
        "The total fare paid is INR 12,400.",
        "Check-in opens 48 hours before departure.",
        "Cabin baggage allowance is 7 kg.",
    ])
    make_pdf(DOCS / "suspicious_invoice.pdf", "INVOICE #7781 — 'Consulting Services'", [
        "From: CEO Office (on behalf of Mr. S. Kapoor, CTO).",
        "Subject: Urgent vendor settlement.",
        "An urgent invoice for INR 4,50,000 is attached. The net amount is due TODAY.",
        "Please transfer the amount to the new account ending 0042 immediately.",
        "Do not share this with anyone; the matter is confidential.",
        "Call +1 555 0142 to confirm account details over the phone.",
    ])
    (DOCS / "gym_receipt.txt").write_text(
        "FITZONE GYM\nReceipt No: R-2214\nDate: 5 September 2026\n"
        "Membership fee: 1,500 INR (monthly)\n"
        "Paid by UPI. The membership renews on 5 October 2026.\n"
        "Auto-debit from the saved payment method.\n", encoding="utf-8")
    (DOCS / "warranty.txt").write_text(
        "NOVA LAPTOPS — Limited Warranty Card\n\n"
        "Serial Number: NV-2291-XR\n\n"
        "The warranty is valid until 12 January 2027, covering battery, display "
        "and motherboard against manufacturing defects.\n"
        "Register repairs at any authorised service centre with this card.\n",
        encoding="utf-8")
    (DOCS / "job_offer.txt").write_text(
        "Orbit Analytics Pvt Ltd — Offer Letter\n\n"
        "Dear Demo User,\n\n"
        "We are pleased to offer you the position of Data Scientist.\n"
        "The joining date is 2 October 2026.\n"
        "Please accept or decline by the response deadline of 28 September 2026.\n"
        "The package is as discussed, with a 3-month probation period.\n\n"
        "Regards,\nHiring Team, Orbit Analytics\n", encoding="utf-8")
    print("  txt  gym_receipt.txt, warranty.txt, job_offer.txt")

    # ── messages ─────────────────────────────────────────────────────────
    (MSGS / "suspicious_message.txt").write_text(
        "URGENT: Your bank account will be suspended within 24 hours. "
        "Verify your password and OTP at http://secure-bank-verify.co/login "
        "now or lose access forever. Do not share this with anyone.\n",
        encoding="utf-8")
    (MSGS / "normal_message.txt").write_text(
        "Hi Demo, your utility bill for September has been generated. "
        "You can review your usage details and pay online from your account "
        "portal at any time before the due date shown in your account. "
        "Thanks, City Power.\n", encoding="utf-8")
    (MSGS / "suspicious_urgent_payment.txt").write_text(
        "This is your manager from the US office. I am travelling and cannot "
        "speak. I need an urgent bank transfer of $12,000 to a vendor today. "
        "Keep this secret and do not tell anyone until we speak. "
        "Call +1 555 0142 for account details.\n", encoding="utf-8")

    # ── transactions ─────────────────────────────────────────────────────
    print("Generating transactions...")
    rows: list[dict] = []

    def add(d: date, desc: str, amount: float, cat: str, hour: int = 12) -> None:
        rows.append({"date": datetime(d.year, d.month, d.day, hour, RNG.randint(0, 59)),
                     "description": desc, "amount": amount, "currency": "INR",
                     "category": cat})

    start = date(2025, 3, 1)
    # recurring schedules
    rec = [
        ("EXAMPLE STREAMING SUBSCRIPTION", 799, date(2025, 3, 2), 30, None, "Subscriptions"),
        ("FITZONE GYM MEMBERSHIP", 1500, date(2025, 3, 5), 30, None, "Health"),
        ("CLOUDVAULT STORAGE PLAN", 499, date(2025, 3, 8), 30, date(2026, 7, 1), "Software"),
        ("NATIONAL DAILY NEWS SUB", 299, date(2025, 3, 10), 91, None, "Subscriptions"),
        ("MUSIC HUB PREMIUM", 149, date(2025, 3, 12), 30, date(2026, 4, 12), "Subscriptions"),
    ]
    for name, amount, first, interval, price_change, cat in rec:
        cur = first
        while cur <= TODAY:
            amt = amount
            if price_change is not None and cur >= price_change:
                amt = 599 if name == "CLOUDVAULT STORAGE PLAN" else amount
            add(cur, name, amt, cat, hour=RNG.choice([8, 9, 10]))
            cur += timedelta(days=interval)

    # one-off spending (realistic, ~3 per month)
    one_off = [
        ("KIRANA STORE NEAR HOME", (600, 2400), "Groceries"),
        ("HP PETROL PUMP", (1100, 1900), "Fuel"),
        ("BIG BAZAAR HYPERMARKET", (1500, 6500), "Groceries"),
        ("AMAZON PAYMENT ON DELIVERY", (500, 4200), "Shopping"),
        ("CAFE LOUNGE DINNER", (350, 1600), "Dining"),
        ("LOCAL CLOTHING STORE", (800, 3500), "Shopping"),
    ]
    d = start
    while d <= TODAY:
        for _ in range(RNG.randint(2, 4)):
            desc, (lo, hi), cat = RNG.choice(one_off)
            dd = d + timedelta(days=RNG.randint(0, 25))
            if dd <= TODAY:
                add(dd, desc, float(RNG.randint(lo, hi)), cat,
                    hour=RNG.choice([10, 12, 18, 20, 21]))
        d += timedelta(days=30)

    add(date(2026, 8, 5), "GOA TRIP FLIGHT SKYWINGS", 12400, "Travel", hour=11)
    add(date(2026, 6, 20), "LAPTOP REPAIR NOVA SERVICE", 3800, "Repairs", hour=15)

    # seeded anomalies (new merchant, unusual amount/time)
    add(date(2026, 8, 28), "PAYTO XFER UNKNOWN RECIPIENT", 48200, "Transfer", hour=23)
    add(date(2026, 9, 2), "QUICK CASH ADVANCE", 21750, "Transfer", hour=22)
    add(date(2026, 8, 15), "CRYPTO GATEWAY CHARGE", 9999, "Other", hour=1)

    rows.sort(key=lambda r: r["date"])
    with open(DEMO / "transactions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "description", "amount", "currency", "category"])
        for r in rows:
            w.writerow([r["date"].strftime("%Y-%m-%d %H:%M"), r["description"],
                        f"{r['amount']:.2f}", r["currency"], r["category"]])
    print(f"  csv  transactions.csv ({len(rows)} rows)")

    with open(DEMO / "subscriptions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["merchant", "frequency", "amount", "currency", "started"])
        for name, amount, first, interval, _, _ in rec:
            freq = {7: "WEEKLY", 30: "MONTHLY", 91: "QUARTERLY", 365: "YEARLY"}[interval]
            w.writerow([name, freq, amount if not (price_change and name == "CLOUDVAULT STORAGE PLAN") else 599,
                        "INR", first.isoformat()])
    print("  csv  subscriptions.csv")

    # ── eval set ─────────────────────────────────────────────────────────
    eval_set = {"cases": [
        {"id": "q01", "question": "When does my insurance policy expire?",
         "expected_doc": "insurance_policy", "expected_keywords": ["14 March 2027"], "category": "dates"},
        {"id": "q02", "question": "What is my insurance renewal premium and when is it due?",
         "expected_doc": "insurance_policy", "expected_keywords": ["18,500", "25 September 2026"], "category": "amounts+dates"},
        {"id": "q03", "question": "When is the electricity bill due?",
         "expected_doc": "electricity_bill", "expected_keywords": ["27 September 2026"], "category": "dates"},
        {"id": "q04", "question": "How much is the electricity bill?",
         "expected_doc": "electricity_bill", "expected_keywords": ["2,340"], "category": "amounts"},
        {"id": "q05", "question": "When does my rental agreement end?",
         "expected_doc": "rental_agreement", "expected_keywords": ["31 December 2026"], "category": "dates"},
        {"id": "q06", "question": "What is the monthly rent for the apartment?",
         "expected_doc": "rental_agreement", "expected_keywords": ["22,000"], "category": "amounts"},
        {"id": "q07", "question": "What is the cancellation notice period for the lease?",
         "expected_doc": "rental_agreement", "expected_keywords": ["60 days"], "category": "policy"},
        {"id": "q08", "question": "What is the next billing date for Example Streaming?",
         "expected_doc": "streaming_invoice", "expected_keywords": ["2 October 2026"], "category": "dates"},
        {"id": "q09", "question": "How much is the streaming subscription per month?",
         "expected_doc": "streaming_invoice", "expected_keywords": ["799"], "category": "amounts"},
        {"id": "q10", "question": "When does the device warranty end?",
         "expected_doc": "warranty", "expected_keywords": ["12 January 2027"], "category": "dates"},
        {"id": "q11", "question": "What is the response deadline for the job offer?",
         "expected_doc": "job_offer", "expected_keywords": ["28 September 2026"], "category": "dates"},
        {"id": "q12", "question": "When is the Goa trip flight?",
         "expected_doc": "travel_booking", "expected_keywords": ["15 November 2026"], "category": "dates"},
    ]}
    # streaming_invoice is generated as a txt below (pdf optional)
    (DOCS / "streaming_invoice.txt").write_text(
        "EXAMPLE STREAMING — Subscription Invoice\n\n"
        "Invoice No: SI-8812\n"
        "Merchant: Example Streaming\n"
        "Plan: Premium Monthly\n"
        "Amount: 799 INR per month\n"
        "The next billing date is 2 October 2026.\n"
        "Auto-renew is ON. To cancel, request by the 25th of the previous month.\n"
        "Cancellation before the deadline avoids the next cycle charge.\n",
        encoding="utf-8")
    (DEMO / "eval_set.json").write_text(json.dumps(eval_set, indent=2), encoding="utf-8")
    print("  json eval_set.json (12 cases)")
    print(f"\nDemo dataset ready under {DEMO}")


if __name__ == "__main__":
    main()
