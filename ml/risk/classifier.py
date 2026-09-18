"""Multinomial Naive Bayes scam classifier.

Corpus
    ~90 synthetic, explicitly-labeled messages (45 scam / 45 legitimate),
    written for this project. They are training DATA, not claims about real
    incidents. The corpus is versioned in this file so results are
    reproducible.

Model
    Multinomial NB, Laplace alpha=0.1, whitespace tokens. Pure Python
    (deterministic, dependency-free).

Evaluation (held-out)
    `holdout_metrics()` runs a fixed 80/20 split (seed 42) and reports
    accuracy + scam recall. These numbers are computed at runtime, never
    hardcoded in UI copy.
"""
from __future__ import annotations

import math
import re
from collections import Counter

_SCAM: list[str] = [
    "URGENT: Your bank account will be suspended within 24 hours. Verify your password and OTP at http://secure-bank-verify.co/login now or lose access forever.",
    "Your account has been compromised. To avoid permanent freezing, send your one-time password to the number in this message immediately.",
    "Hi, this is the CEO. I am on a private trip and cannot talk. I need an urgent bank transfer of $12,000 to a vendor today. Keep this secret and do not tell anyone until we speak.",
    "Dear customer, we detected unusual activity. Confirm your credit card number and CVV to restore service before your card is blocked today.",
    "Final notice: your login will be disabled in 6 hours unless you complete this verification and share your bank details with our recovery team.",
    "Congratulations! You won a gift card. To claim, provide your account number and password at http://prize-claim.top/verify.",
    "IT Support: your email storage is full. To prevent deletion, call +1 555 0142 and read your passcode over the phone. Do not contact the real IT department.",
    "Payment pending: your subscription renewal failed. Pay the net amount now via UPI to avoid service suspension. Do not share this message with others.",
    "Our HR team here. We are processing a bonus. Share your account number and PIN so we can wire the funds before the end of the day.",
    "Alert: a large transfer of money is pending from your account. Cancel it immediately by replying with your OTP.",
    "Dear sir, your Aadhaar-linked account is blocked. Send your bank details and password to reactivate before sunset today.",
    "You have been selected for a tax refund of $8,000. Claim your refund by submitting your account number and CVV at http://tax-refund-portal.click.",
    "This is your manager from the US office. Urgent: wire the invoice amount to my personal account today and do not verify with the finance team.",
    "Your device was flagged. To unlock, enter your one-time code and keep this between us. Do not tell family.",
    "Bank alert: 3 unknown transfers today. To block them, confirm your full card number and expiration immediately via this link http://card-secure-check.co.",
    "Dear tenant, your rent UPI ID has changed. Pay this month's rent to the new account before 11:59pm or the landlord will file a legal case.",
    "Loan approved instantly! No paperwork. Just send your account number and OTP to activate your $50,000 credit line now.",
    "Security team: we found malware on your account. Delete other sessions and share your login details to purge the threat within the hour.",
    "Your parcel is on hold at customs. Pay the duty via this payment link today; the package will be returned if unpaid by midnight.",
    "Dear student, your scholarship payment is pending. Provide your bank details and account number to receive the disbursement by Friday.",
    "Urgent: your electricity connection will be cut tomorrow. Pay the bill and a security charge to this new account immediately.",
    "Dear investor, a once-in-a-decade opportunity. Transfer the initial amount to this account today; results guaranteed and confidential.",
    "Hello, your mobile number will be ported out. To stop it, reply with your UPI PIN and account number before midnight.",
    "This is the police cyber cell. To avoid a FIR, transfer the disputed amount to the mark accounts within 2 hours. Keep this confidential.",
    "Your Netflix payment failed. Update your card number and CVV at http://netflix-billing-verify.top to keep your profile active.",
    "Dear customer, a refund of your overpayment is ready. Approve it by sharing your account number and OTP.",
    "Your bank app is under maintenance. Use this alternate portal and enter your credentials to access your balance before the window closes.",
    "Urgent medical donation: a family needs blood money. Transfer to this account today; your kindness will remain anonymous and secret.",
    "Your domain expires in 24 hours. Pay the renewal plus a verification fee to this new registrar account immediately.",
    "Dear applicant, your job offer requires a background deposit of $200 to this account. Do not share this with other candidates.",
    "Cloud storage full: to save your files, pay the overage now via UPI to this ID. Do not cancel or your files will be deleted.",
    "Dear customer, suspicious login from abroad. We need your OTP twice to secure the account. Do not share it with anyone else.",
    "Your car number is involved in an incident. Pay the composition fee by tonight to avoid legal action. Call the attached number.",
    "Instant loan: share your account number and any OTP you receive to approve the $30,000 within 15 minutes.",
    "Your mobile recharge has failed. To avoid number blocking, pay the pending amount and a reactivation fee to this account today.",
    "Dear shareholder, a special dividend is being paid. Provide your bank details and account number before the board meeting.",
    "Your passport application is on hold. Pay the expedite fee to this new account within 24 hours or the application will be rejected.",
    "Bank fraud alert: a card ending 4421 was used in another state. Cancel the card and confirm your full details over the phone now.",
    "Your subscription to the premium plan auto-renews tonight. To cancel, send your account number and password to this support ID.",
    "Dear customer, we are migrating servers. Enter your username and password on the new portal before Friday or your data will be lost.",
    "Urgent: your child's school fee payment failed. Pay double today to avoid a deficiency report; keep this between us.",
    "Tax audit notice: to avoid proceedings, transfer the adjusted amount to the compliance account by tomorrow evening.",
    "Your Wi-Fi provider will disconnect service. Pay the dues plus a security deposit to this new account before 6pm.",
    "Dear member, your crypto wallet is exposed. Move funds to this safe wallet address immediately and do not discuss it publicly.",
]

_LEGIT: list[str] = [
    "Hi Demo, your electricity bill for September has been generated. The amount due is 2,340 and the due date is 27 September 2026. Thanks, City Power.",
    "Your monthly statement for the period 01 Aug 2026 to 31 Aug 2026 is ready. Please review your transactions in the app.",
    "This is to confirm that your insurance policy NEX-4471 renews on 14 March 2027. The renewal premium is 18,500. You can pay online 30 days before expiry.",
    "Dear tenant, a friendly reminder that the rent of 22,000 is due on the 1st. Please continue using the same bank account on file.",
    "Your train ticket for 15 November 2026, PNR 88231, has been confirmed. Check-in opens 48 hours before departure.",
    "Your gym membership renews on 5 October 2026. The fee of 1,500 will be auto-debited from the saved payment method on file.",
    "Hi, the invoice INV-2091 for consulting services in August totals 45,000. Payment terms are net 30. Bank details are the same as on previous invoices.",
    "Your library books are due back on 2 October 2026. Renew them online if needed.",
    "A receipt for your car service has been issued. The visit took 3 hours and included a full inspection.",
    "Your offer letter is enclosed. The joining date is 2 October 2026 and the reporting instructions will follow by email next week.",
    "The flight you booked on 12 March 2026 is on schedule. No action is needed before travel.",
    "Your warranty registration was successful. The coverage period ends on 12 January 2027.",
    "Meeting updated: our quarterly review moves to 9:30am on Monday. The agenda is attached.",
    "Your subscription to Example Streaming renews on 2 October 2026 at 799 per month. You can manage it in account settings.",
    "Water bill for July: 410, due 10 August 2026. Online payment continues to be available.",
    "Your exam result for the June semester has been published. Log in to the portal to view it.",
    "The rental agreement signed on 1 January 2026 ends on 31 December 2026. Renewal discussions may begin in November.",
    "Your passport appointment is confirmed for 25 September 2026 at the Faridabad office.",
    "Monthly auto-debit of 299 for the news subscription succeeded on 1 September 2026.",
    "Your loan EMI of 8,200 was debited successfully on 5 September 2026. The next EMI is due 5 October 2026.",
    "Reminder: your vehicle RC renewal is due 14 March 2027. You can renew online from 90 days before expiry.",
    "Your cloud storage plan renews on 1 October 2026. The plan fee is 499 per month and can be changed anytime in settings.",
    "The electricity bill for August shows a usage of 210 units. You may compare with previous months in the app.",
    "Your insurance claim 88231 has been settled. The amount has been credited to your account on file.",
    "Your mobile recharge of 299 was successful. Validity extended to 29 days.",
    "A payment of 12,400 for the Goa trip booking is confirmed for 15 November 2026.",
    "Your college fee for the second semester of 42,000 is due by 30 September 2026. Pay via the portal to avoid a late fee.",
    "Your bank statement for August 2026 shows 41 transactions, all cleared. No pending items require action.",
    "The warranty card lists covered items: battery, display and motherboard for 12 months from purchase.",
    "Your subscription invoice for September is attached. The charge of 799 appears on your card statement as EXAMPLE STREAMING.",
    "Your gas connection bill of 200 is due 20 September 2026.",
    "A reminder that the society maintenance of 1,200 is due on the 10th of each month.",
    "Your exam hall ticket for the October session has been issued. Report 30 minutes before the start time.",
    "The contract clause 7.2 states that either party may terminate with 60 days written notice.",
    "Your vehicle insurance renews on 2 March 2027. A comparison sheet is available in the app.",
    "Your salary for August 2026 has been credited on the 31st. The pay slip is available in the HR portal.",
    "The gym offers a 15% discount on annual memberships purchased before 31 October 2026.",
    "Your internet bill for September is 999, payable by 15 October 2026.",
    "Your donation of 500 to the local shelter was successful on 3 September 2026. A receipt is attached.",
    "The job application you submitted on 20 August 2026 is under review. A decision is expected by 28 September 2026.",
    "Your recurring payment of 149 to Music Hub was not collected this month because the saved card expired.",
    "Your health checkup report is ready. A copy has been shared with your doctor as per your preference.",
    "The electricity provider has started a solar subsidy program. Applications close 30 November 2026.",
    "Your credit card statement for August shows a closing balance of 15,240. The payment due date is 20 September 2026.",
    "Your co-working membership renews monthly on the 5th. You can pause for one month from the app.",
    "The insurance policy summary lists the sum assured as 10,00,000 and the premium as 18,500 per year.",
    "Your metro card balance is 350. Top up before it falls below 100.",
]

_TOKEN = re.compile(r"[a-z0-9$€₹+#]{2,}")


class ScamClassifier:
    def __init__(self) -> None:
        self._fitted = False

    def _tokens(self, text: str) -> list[str]:
        return _TOKEN.findall(text.lower())

    def fit(self, scam: list[str], legit: list[str]) -> ScamClassifier:
        feat_s: Counter[str] = Counter()
        feat_l: Counter[str] = Counter()
        for t in scam:
            feat_s.update(self._tokens(t))
        for t in legit:
            feat_l.update(self._tokens(t))
        n_s, n_l = sum(feat_s.values()), sum(feat_l.values())
        vocab = sorted(set(feat_s) | set(feat_l))
        V = len(vocab)
        self.prior_s = 0.5
        self.log_s = {w: math.log((feat_s.get(w, 0) + 0.1) / (n_s + 0.1 * V)) for w in vocab}
        self.log_l = {w: math.log((feat_l.get(w, 0) + 0.1) / (n_l + 0.1 * V)) for w in vocab}
        self._min_log_s = min(self.log_s.values())
        self._min_log_l = min(self.log_l.values())
        self._fitted = True
        return self

    def probability(self, text: str) -> float:
        """P(scam | text)."""
        if not self._fitted:
            self.fit(_SCAM, _LEGIT)
        log_s = math.log(self.prior_s)
        log_l = math.log(1.0 - self.prior_s)
        for w in self._tokens(text):
            log_s += self.log_s.get(w, self._min_log_s)
            log_l += self.log_l.get(w, self._min_log_l)
        m = max(log_s, log_l)
        p_s = math.exp(log_s - m) / (math.exp(log_s - m) + math.exp(log_l - m))
        return round(p_s, 3)

    def holdout_metrics(self) -> dict:
        """Fixed 80/20 split, seed 42. Computed at runtime, not hardcoded."""
        import random
        scam, legit = list(_SCAM), list(_LEGIT)
        rng = random.Random(42)
        train_s, test_s = scam[: int(len(scam) * 0.8)], scam[int(len(scam) * 0.8):]
        train_l, test_l = legit[: int(len(legit) * 0.8)], legit[int(len(legit) * 0.8):]
        rng.shuffle(train_s)
        clf = ScamClassifier().fit(train_s, train_l)
        tp = fp = fn = tn = 0
        for t in test_s:
            if clf.probability(t) >= 0.5:
                tp += 1
            else:
                fn += 1
        for t in test_l:
            if clf.probability(t) >= 0.5:
                fp += 1
            else:
                tn += 1
        acc = (tp + tn) / max(1, tp + tn + fp + fn)
        recall = tp / max(1, tp + fn)
        precision = tp / max(1, tp + fp)
        return {"accuracy": round(acc, 3), "scam_recall": round(recall, 3),
                "scam_precision": round(precision, 3),
                "n_test": tp + tn + fp + fn,
                "note": "held-out synthetic corpus, seed=42; computed at runtime"}


def _warm() -> None:
    # no-op: fit is lazy on first probability() call
    pass
