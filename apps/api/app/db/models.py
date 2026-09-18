"""SQLAlchemy models. UUID string PKs (portable across SQLite/Postgres),
explicit FKs, indexes, timestamps. No unstructured-everything JSON blobs:
JSON columns are used only for genuinely semi-structured payloads
(signals, args, attrs) alongside proper scalar columns.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, utcnow


def new_uuid() -> str:
    return uuid.uuid4().hex


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))

    documents: Mapped[list[Document]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_user_status", "user_id", "status"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(512))
    file_type: Mapped[str] = mapped_column(String(16))            # pdf|docx|txt|csv|md|image
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    mime: Mapped[str] = mapped_column(String(120), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="UPLOADED", index=True)
    # UPLOADED -> PROCESSING -> INDEXING -> READY | FAILED
    status_detail: Mapped[str] = mapped_column(Text, default="")
    doc_type: Mapped[str] = mapped_column(String(24), default="OTHER")
    doc_type_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    user: Mapped[User] = relationship(back_populates="documents")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (Index("ix_chunks_user_doc", "user_id", "document_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    embedding_json: Mapped[str] = mapped_column(Text, default="")
    embedding_provider: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentEntity(Base):
    __tablename__ = "document_entities"
    __table_args__ = (Index("ix_ent_user_kind", "user_id", "kind"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))                 # MERCHANT, DATE, AMOUNT, EMAIL, ...
    value: Mapped[str] = mapped_column(String(512))
    field: Mapped[str] = mapped_column(String(64), default="")    # structured field if mapped
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[str] = mapped_column(String(512), default="")
    page: Mapped[int] = mapped_column(Integer, default=0)


class Merchant(Base):
    __tablename__ = "merchants"
    # Unique, not just indexed: import_transactions() get-or-creates by
    # (user_id, normalized) from concurrent ingestion jobs — the constraint
    # turns a would-be duplicate insert into a clean IntegrityError the
    # caller retries as a lookup, instead of a silently duplicated merchant.
    __table_args__ = (UniqueConstraint("user_id", "normalized", name="uq_merchants_user_norm"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    normalized: Mapped[str] = mapped_column(String(255))


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_tx_user_date", "user_id", "date"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    merchant_id: Mapped[str | None] = mapped_column(ForeignKey("merchants.id", ondelete="SET NULL"))
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    description: Mapped[str] = mapped_column(String(512))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    category: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(24), default="csv")
    source_doc_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (Index("ix_subs_user_status", "user_id", "status"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    merchant: Mapped[str] = mapped_column(String(255))
    raw_merchant: Mapped[str] = mapped_column(String(512), default="")
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    frequency: Mapped[str] = mapped_column(String(16))
    occurrences: Mapped[int] = mapped_column(Integer, default=0)
    first_date: Mapped[date] = mapped_column(Date)
    last_date: Mapped[date] = mapped_column(Date)
    next_due: Mapped[date] = mapped_column(Date)
    median_interval_days: Mapped[float] = mapped_column(Float, default=0.0)
    monthly_equivalent: Mapped[float] = mapped_column(Float)
    annualized_cost: Mapped[float] = mapped_column(Float)
    amount_cv: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")  # ACTIVE | LAPSED
    price_increase_json: Mapped[str] = mapped_column(Text, default="null")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    source: Mapped[str] = mapped_column(String(24), default="transactions")
    source_doc_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Deadline(Base):
    __tablename__ = "deadlines"
    # Unique on (user_id, title, due_date): _upsert_deadline() get-or-creates
    # on this triple from concurrent ingestion jobs — see Merchant above.
    __table_args__ = (
        Index("ix_deadlines_user_due", "user_id", "due_date"),
        UniqueConstraint("user_id", "title", "due_date", name="uq_deadlines_user_title_due"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32), default="OTHER")
    due_date: Mapped[date] = mapped_column(Date, index=True)
    source_doc_id: Mapped[str | None] = mapped_column(String(32))
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    importance: Mapped[int] = mapped_column(Integer, default=2)       # 1..5
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Risk(Base):
    __tablename__ = "risks"
    __table_args__ = (Index("ix_risks_user_level", "user_id", "level"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))                     # SCAM, ANOMALY, DEADLINE, SUBSCRIPTION
    subject: Mapped[str] = mapped_column(String(512))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    level: Mapped[str] = mapped_column(String(16))                    # LOW|MEDIUM|HIGH|CRITICAL
    signals_json: Mapped[str] = mapped_column(Text, default="[]")
    components_json: Mapped[str] = mapped_column(Text, default="{}")
    disclaimer: Mapped[str] = mapped_column(Text, default="")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Task(Base, TimestampMixin):
    """User-visible action items (reminders, drafts, reports)."""
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(32), default="REMINDER")
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")   # OPEN|DONE|CANCELLED
    source: Mapped[str] = mapped_column(String(64), default="agent")


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_runs_user_status", "user_id", "status"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(48), default="")
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    # PENDING | RUNNING | WAITING_APPROVAL | COMPLETED | FAILED
    response_text: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (Index("ix_steps_run_seq", "run_id", "seq"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(24))                     # PLANNER|TOOL|DATA|MODEL|LLM|REPORT|GATE
    name: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str] = mapped_column(Text, default="")
    args_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(24), default="OK")     # OK|PENDING_APPROVAL|FAILED|SKIPPED
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_user_status", "user_id", "status"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32))
    tool: Mapped[str] = mapped_column(String(64))
    risk_class: Mapped[str] = mapped_column(String(24))               # SENSITIVE|CONSEQUENTIAL
    args_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="null")
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    # PENDING | APPROVED | REJECTED | EXECUTED | FAILED | EXPIRED
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_user_created", "user_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str | None] = mapped_column(String(32), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    action: Mapped[str] = mapped_column(String(120))
    target: Mapped[str] = mapped_column(String(255), default="")
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelPrediction(Base):
    __tablename__ = "model_predictions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(64))
    task: Mapped[str] = mapped_column(String(64))                     # anomaly|forecast|recurring|risk
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeEntity(Base):
    __tablename__ = "knowledge_entities"
    # Unique on (user_id, kind, name): upsert_entity() get-or-creates on this
    # triple, called concurrently by the ingestion worker pool (>=2 threads)
    # processing different documents for the same user — see Merchant above.
    __table_args__ = (
        Index("ix_ke_user_kind", "user_id", "kind"),
        UniqueConstraint("user_id", "kind", "name", name="uq_ke_user_kind_name"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))                     # USER|DOCUMENT|MERCHANT|DEADLINE|...
    name: Mapped[str] = mapped_column(String(255))
    attrs_json: Mapped[str] = mapped_column(Text, default="{}")
    ref_id: Mapped[str | None] = mapped_column(String(32))            # FK-ish pointer (no constraint: polymorphic)


class KnowledgeRelationship(Base):
    __tablename__ = "knowledge_relationships"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    src_id: Mapped[str] = mapped_column(String(32), index=True)
    rel: Mapped[str] = mapped_column(String(32))
    dst_id: Mapped[str] = mapped_column(String(32), index=True)


class RagEvalResult(Base):
    __tablename__ = "rag_eval_results"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str | None] = mapped_column(String(32), index=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    question: Mapped[str] = mapped_column(Text)
    expected_doc: Mapped[str] = mapped_column(String(255))
    retrieved_docs_json: Mapped[str] = mapped_column(Text, default="[]")
    top1_doc: Mapped[str] = mapped_column(String(255), default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    answer_sources_json: Mapped[str] = mapped_column(Text, default="[]")
    precision_at_1: Mapped[float] = mapped_column(Float, default=0.0)
    recall_at_5: Mapped[float] = mapped_column(Float, default=0.0)
    citation_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    answer_correctness: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notif_user_read", "user_id", "read"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))                     # DEADLINE|RISK|PROCESSING|APPROVAL|AGENT
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="INFO")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryEntry(Base, TimestampMixin):
    __tablename__ = "memory_entries"
    __table_args__ = (Index("ix_mem_user_scope_key", "user_id", "scope", "key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(24))                    # conversation|preference|state
    key: Mapped[str] = mapped_column(String(120))
    value_json: Mapped[str] = mapped_column(Text, default="{}")
