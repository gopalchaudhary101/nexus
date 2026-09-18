"""Pydantic v2 API schemas."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── auth ───────────────────────────────────────────────────────────────
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(min_length=1, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: str
    email: EmailStr
    name: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DeleteMeIn(BaseModel):
    password: str


# ── documents ──────────────────────────────────────────────────────────
class EntityOut(BaseModel):
    kind: str
    value: str
    field: str = ""
    confidence: float
    evidence: str = ""
    page: int = 0


class DocumentOut(ORMModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    status: str
    status_detail: str
    doc_type: str
    doc_type_confidence: float
    page_count: int
    created_at: datetime


class ChunkOut(BaseModel):
    id: str
    chunk_index: int
    page: int
    text: str
    score: float | None = None


class DocumentDetailOut(DocumentOut):
    text_preview: str = ""
    entities: list[EntityOut] = []
    chunks: list[ChunkOut] = []
    chunk_count: int = 0


# ── search / ask ───────────────────────────────────────────────────────
class SearchIn(BaseModel):
    query: str = Field(min_length=2)
    top_k: int = Field(default=5, ge=1, le=20)
    doc_type: str | None = None


class HitOut(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    doc_type: str
    page: int
    chunk_index: int
    text: str
    vector_score: float
    bm25_score: float
    score: float


class SearchOut(BaseModel):
    query: str
    hits: list[HitOut]


class AskIn(BaseModel):
    question: str = Field(min_length=2)
    doc_type: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class SourceOut(BaseModel):
    document_id: str
    document_name: str
    page: int
    chunk_index: int
    similarity: float
    ref: str


class AskOut(BaseModel):
    question: str
    answer: str
    confidence: float
    grounded: bool
    sources: list[SourceOut]
    provider: str


# ── insights ───────────────────────────────────────────────────────────
class OverviewOut(BaseModel):
    needs_attention: int
    upcoming: int
    risk_signals: int
    recurring_monthly: float
    recurring_currency: str
    documents: int
    ready_documents: int
    pending_documents: int
    knowledge_coverage: float
    pending_approvals: int
    recent: list[dict] = []


class SubscriptionOut(BaseModel):
    id: str
    merchant: str
    raw_merchant: str
    amount: float
    currency: str
    frequency: str
    occurrences: int
    last_date: date
    next_due: date
    monthly_equivalent: float
    annualized_cost: float
    status: str
    confidence: float
    price_increase: dict | None = None
    notes: list[str] = []


class AnomalyOut(BaseModel):
    transaction_id: str
    date: datetime
    description: str
    amount: float
    currency: str
    label: str
    score: float
    model: str
    explanations: list[dict] = []
    note: str = "Anomaly != fraud. Unusual transaction — review recommended."


class DeadlineOut(BaseModel):
    id: str
    title: str
    kind: str
    due_date: date
    days_remaining: int
    risk_level: str
    source: str
    source_ref: str = ""
    amount: float | None = None
    currency: str = "INR"
    importance: int
    notes: str = ""


class ForecastOut(BaseModel):
    ok: bool
    message: str
    model: str
    history: list[dict] = []
    points: list[dict] = []
    trend_pct_mom: float | None = None


# ── risk ───────────────────────────────────────────────────────────────
class RiskAnalyzeIn(BaseModel):
    text: str | None = Field(default=None, max_length=20000)
    document_id: str | None = None
    sender: str | None = None
    claimed_brand: str | None = None


class RiskOut(BaseModel):
    id: str
    risk_level: str
    score: float
    signals: list[dict]
    components: dict
    disclaimer: str
    subject: str


# ── agents ─────────────────────────────────────────────────────────────
class AgentRunIn(BaseModel):
    request: str = Field(min_length=2, max_length=4000)
    message: str | None = Field(default=None, max_length=20000)


class AgentStepOut(BaseModel):
    seq: int
    type: str
    name: str
    detail: str
    status: str
    duration_ms: float
    args: dict = {}
    result: dict = {}
    created_at: datetime


class AgentTaskOut(BaseModel):
    id: str
    request: str
    intent: str
    status: str
    response_text: str
    result: dict = {}
    created_at: datetime
    finished_at: datetime | None = None
    steps: list[AgentStepOut] = []


class AgentTaskListOut(BaseModel):
    items: list[AgentTaskOut]
    total: int


# ── approvals ──────────────────────────────────────────────────────────
class ApprovalOut(BaseModel):
    id: str
    run_id: str | None
    tool: str
    risk_class: str
    args: dict = {}
    status: str
    result: dict | None = None
    created_at: datetime
    decided_at: datetime | None = None


# ── analytics ──────────────────────────────────────────────────────────
class OverviewAnalyticsOut(BaseModel):
    documents: int
    chunks: int
    transactions: int
    subscriptions: int
    deadlines: int
    risks: int
    agent_runs: int
    audit_events: int
    storage_bytes: int


class SpendingOut(BaseModel):
    currency: str
    months: list[dict]          # {month, total, recurring, other}


class RagQualityOut(BaseModel):
    evaluated: bool
    message: str | None = None
    generated_at: str | None = None
    n_cases: int | None = None
    metrics: dict | None = None
    rows: list[dict] = []


class RiskAnalyticsOut(BaseModel):
    total: int
    by_level: dict
    top_signals: list[dict]     # {label, count}
    recent: list[dict] = []


# ── notifications ──────────────────────────────────────────────────────
class NotificationOut(ORMModel):
    id: str
    kind: str
    title: str
    body: str
    severity: str
    read: bool
    created_at: datetime
