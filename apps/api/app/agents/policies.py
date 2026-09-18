"""Action policy: every tool is classified SAFE / SENSITIVE / CONSEQUENTIAL.

SAFE           -> may execute automatically
SENSITIVE      -> requires user confirmation (approval)
CONSEQUENTIAL  -> always requires explicit approval; default when unknown
                   is ASK (fail-closed).
"""
from __future__ import annotations

SAFE = "SAFE"
SENSITIVE = "SENSITIVE"
CONSEQUENTIAL = "CONSEQUENTIAL"

TOOL_POLICY: dict[str, str] = {
    # read-only / computation
    "search_documents": SAFE,
    "get_document": SAFE,
    "search_transactions": SAFE,
    "list_subscriptions": SAFE,
    "detect_anomalies": SAFE,
    "list_deadlines": SAFE,
    "get_forecast": SAFE,
    "analyze_risk": SAFE,
    "build_insight_report": SAFE,
    # changes user-visible state
    "create_reminder": SENSITIVE,
    "prepare_email": SENSITIVE,
    # external-world or destructive
    "send_email": CONSEQUENTIAL,
    "cancel_subscription": CONSEQUENTIAL,
    "delete_document": CONSEQUENTIAL,
}


def policy_for(tool: str) -> str:
    return TOOL_POLICY.get(tool, SENSITIVE)  # unknown tools fail closed
