"""Deterministic rule planner.

The planner maps a user request to an intent and a fixed sequence of tool
calls. This is a real (if simple) planner: every step is a declared tool
call with arguments, visible in the agent trace. An LLM planner can be
swapped in behind the same (intent, steps) interface without changing the
executor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class PlanStep:
    tool: str
    args: dict = field(default_factory=dict)
    description: str = ""


def classify_intent(request: str, has_message: bool = False) -> str:
    r = (request or "").lower()
    if has_message or any(w in r for w in ("suspicious", "scam", "fraud", "phishing",
                                           "analyze this message", "is this message")):
        return "risk_check"
    if any(w in r for w in ("subscription", "recurring", "auto-renew", "autorenew", "membership")):
        return "subscription_review"
    if any(w in r for w in ("expir", "renew", "deadline", "due", "warranty", "notice")):
        return "expiring_soon"
    if any(w in r for w in ("forecast", "predict", "expected spending", "trend of my spending")):
        return "forecast"
    if any(w in r for w in ("anomal", "unusual transaction", "weird transaction")):
        return "anomaly_review"
    if any(w in r for w in ("attention", "this week", "today", "priority",
                            "what should i", "take care", "action plan")):
        return "weekly_attention"
    if "changed" in r or "change" in r:
        return "spending_change"
    return "rag_question"


def build_plan(intent: str, request: str,
               message: str | None = None) -> tuple[str, list[PlanStep]]:
    if intent == "weekly_attention":
        return intent, [
            PlanStep("list_deadlines", {"days": 14}, "Searching deadlines in the next 14 days"),
            PlanStep("search_documents", {"query": "urgent renewal expiry deadline cancellation"},
                     "Searching documents for urgent items"),
            PlanStep("list_subscriptions", {}, "Loading subscriptions and recurring costs"),
            PlanStep("detect_anomalies", {}, "Scanning recent transactions for anomalies"),
            PlanStep("build_insight_report", {"focus": "attention"},
                     "Assembling prioritized action plan"),
            PlanStep("create_reminder",
                     {"title": "Review NEXUS weekly action plan",
                      "due_date": (date.today() + timedelta(days=1)).isoformat()},
                     "Create a reminder so the plan is not forgotten (needs your approval)"),
        ]
    if intent == "expiring_soon":
        m = re.search(r"(\d{1,3})\s*(?:days?|d\b)", request.lower())
        days = int(m.group(1)) if m else 30
        return intent, [
            PlanStep("list_deadlines", {"days": days}, f"Listing deadlines in the next {days} days"),
            PlanStep("search_documents", {"query": "expiry renewal warranty cancellation deadline"},
                     "Searching documents for expiring items"),
            PlanStep("build_insight_report", {"focus": "expiring"}, "Ranking by urgency"),
        ]
    if intent == "subscription_review":
        return intent, [
            PlanStep("list_subscriptions", {}, "Loading detected subscriptions"),
            PlanStep("search_transactions", {"days": 180}, "Reviewing 6 months of recurring payments"),
            PlanStep("build_insight_report", {"focus": "subscriptions"},
                     "Ranking review candidates by annual cost"),
        ]
    if intent == "risk_check":
        text = message or request
        return intent, [
            PlanStep("analyze_risk", {"text": text}, "Running multi-signal risk engine"),
        ]
    if intent == "anomaly_review":
        return intent, [
            PlanStep("detect_anomalies", {}, "Fitting and running anomaly detector"),
            PlanStep("build_insight_report", {"focus": "anomalies"}, "Summarizing flagged items"),
        ]
    if intent == "forecast":
        return intent, [
            PlanStep("search_transactions", {"days": 365}, "Loading spending history"),
            PlanStep("get_forecast", {}, "Running forecast (or reporting insufficient data)"),
        ]
    if intent == "spending_change":
        return intent, [
            PlanStep("search_transactions", {"days": 180}, "Loading 6 months of transactions"),
            PlanStep("get_forecast", {}, "Comparing trend and forecast"),
            PlanStep("build_insight_report", {"focus": "spending"}, "Summarizing changes"),
        ]
    # default: grounded RAG question
    return intent, [
        PlanStep("search_documents", {"query": request}, "Retrieving relevant document evidence"),
    ]
