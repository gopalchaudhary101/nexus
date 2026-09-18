"""Ingestion pipeline orchestration (runs as a background job).

raw file -> validation -> storage -> text extraction -> cleaning ->
chunking -> entity extraction -> classification -> embeddings -> vector
index -> structured records (deadlines/subscriptions) -> knowledge graph
-> status READY (or FAILED with reason) -> notification
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ml.extraction.classify import classify_document
from ml.extraction.entities import extract_entities

from ..db.models import Deadline, Document, DocumentChunk, DocumentEntity, Subscription
from ..db.session import get_session_factory
from ..llm.factory import get_embedder
from . import records as rec
from .chunking import chunk_text
from .extract import extract_text
from .graph import rebuild_document_graph
from .notify import notify
from .transactions import import_transactions, parse_transactions_csv


def _find_deadline(db, user_id: str, title: str, due):
    return db.execute(select(Deadline).where(
        Deadline.user_id == user_id,
        Deadline.title == title,
        Deadline.due_date == due,
    )).scalars().first()


def _upsert_deadline(db, doc: Document, d: dict) -> None:
    due = d["due_date"]
    today = date.today()
    if due < today - timedelta(days=30) or due > today + timedelta(days=3650):
        return  # implausible/stale — don't pollute the deadline list
    title = d["title"][:255]
    existing = _find_deadline(db, doc.user_id, title, due)
    if existing is not None:
        return
    # Two ingestion worker threads can derive the same (title, due_date)
    # deadline from two different documents at once; the unique constraint
    # on Deadline turns the loser's insert into an IntegrityError inside a
    # savepoint rather than a duplicate row or a crash (see graph.upsert_entity).
    db.add(Deadline(
        user_id=doc.user_id, title=title, kind=d["kind"],
        due_date=due, source_doc_id=doc.id, source_ref=d["source_ref"][:255],
        amount=d.get("amount"), currency=d.get("currency", "INR"),
        importance=d.get("importance", 2), notes=d.get("notes", ""),
    ))
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        pass  # another job just inserted the same deadline — nothing to do


def _upsert_subscription(db, doc: Document, s: dict) -> None:
    from .transactions import find_matching_subscription

    existing = find_matching_subscription(db, doc.user_id, s["merchant"][:255], s["frequency"])
    if existing is not None:
        existing.amount = s["amount"]
        existing.next_due = s["next_due"]
        existing.monthly_equivalent = s["monthly_equivalent"]
        existing.annualized_cost = s["annualized_cost"]
        existing.source_doc_id = doc.id
        existing.confidence = max(existing.confidence, s["confidence"])
        return
    db.add(Subscription(
        user_id=doc.user_id, merchant=s["merchant"][:255],
        raw_merchant=s.get("raw_merchant", s["merchant"])[:512],
        amount=s["amount"], currency=s.get("currency", "INR"),
        frequency=s["frequency"], occurrences=1,
        first_date=s["next_due"], last_date=s["next_due"], next_due=s["next_due"],
        median_interval_days={"WEEKLY": 7, "MONTHLY": 30, "QUARTERLY": 90, "YEARLY": 365}[s["frequency"]],
        monthly_equivalent=s["monthly_equivalent"], annualized_cost=s["annualized_cost"],
        amount_cv=0.0, status="ACTIVE",
        notes_json=json.dumps([f"From document: {s.get('source_ref', '')}"]),
        confidence=s["confidence"], source="document", source_doc_id=doc.id,
    ))


def run_ingestion(doc_id: str) -> None:
    SessionLocal = get_session_factory()
    db = SessionLocal()
    doc = db.get(Document, doc_id)
    if doc is None:
        db.close()
        return
    try:
        doc.status = "PROCESSING"
        doc.status_detail = "Extracting text"
        db.commit()

        path = Path(doc.stored_path)

        if doc.file_type == "csv":
            text = path.read_text(encoding="utf-8", errors="replace")
            rows = parse_transactions_csv(text)
            n = import_transactions(db, doc.user_id, rows, source="csv", source_doc_id=doc.id)
            doc.text = text[:20000]
            doc.page_count = 1
            doc.doc_type = "BANK_STATEMENT" if "statement" in doc.filename.lower() else "OTHER"
            doc.doc_type_confidence = 0.9
            from .graph import _user_name, add_rel, upsert_entity
            user_node = upsert_entity(db, doc.user_id, "USER", _user_name(db, doc.user_id))
            doc_node = upsert_entity(db, doc.user_id, "DOCUMENT", doc.filename,
                                     {"type": doc.doc_type, "rows": n}, ref_id=doc.id)
            add_rel(db, doc.user_id, user_node, "OWNS", doc_node)
            for m in {r["merchant_key"] for r in rows}:
                node = upsert_entity(db, doc.user_id, "MERCHANT", m.title()[:255])
                add_rel(db, doc.user_id, doc_node, "MENTIONS", node)
            # subscription intelligence is part of transaction ingestion
            from .transactions import refresh_subscriptions_for_user
            refresh_subscriptions_for_user(db, doc.user_id)
            db.commit()
            doc.status = "READY"
            doc.status_detail = f"Imported {n} transactions."
            db.commit()
            notify(db, doc.user_id, "PROCESSING", f"{doc.filename} imported",
                   f"{n} transactions available for analysis.", "INFO")
            return

        text, pages = extract_text(path, doc.file_type)
        doc.text = text[:100000]
        doc.page_count = len(pages) if pages else 1

        doc_type, conf, _scores = classify_document(text)
        doc.doc_type = doc_type
        doc.doc_type_confidence = conf

        doc.status = "INDEXING"
        doc.status_detail = "Chunking, embedding, extracting entities"
        db.commit()

        chunks = chunk_text(text, pages or None)
        embedder = get_embedder()
        embs = embedder.embed_batch([c.text for c in chunks])
        for c, e in zip(chunks, embs, strict=True):
            db.add(DocumentChunk(
                document_id=doc.id, user_id=doc.user_id, chunk_index=c.index,
                page=c.page, text=c.text, embedding_json=json.dumps(e.tolist()),
                embedding_provider=embedder.name,
            ))

        ents = extract_entities(text)
        for e in ents:
            db.add(DocumentEntity(
                document_id=doc.id, user_id=doc.user_id, kind=e.kind,
                value=e.value[:512], confidence=e.confidence,
                evidence=e.evidence[:512],
            ))

        base_ref = doc.filename
        deadlines = rec.derive_deadlines(doc_type, text, pages or [text], base_ref)
        for d in deadlines:
            _upsert_deadline(db, doc, d)
        sub = rec.derive_subscription(doc_type, text, base_ref)
        if sub:
            _upsert_subscription(db, doc, sub)
        db.commit()

        rebuild_document_graph(db, doc, ents, deadlines)
        doc.status = "READY"
        doc.status_detail = (f"{len(chunks)} chunks, {len(ents)} entities, "
                             f"{len(deadlines)} deadlines, type={doc_type} ({conf:.0%})")
        db.commit()
        notify(db, doc.user_id, "PROCESSING", f"{doc.filename} is ready",
               doc.status_detail, "INFO")
    except Exception as e:  # noqa: BLE001 - surface as FAILED status, never crash worker
        doc.status = "FAILED"
        doc.status_detail = f"{type(e).__name__}: {e}"
        db.commit()
        try:
            notify(db, doc.user_id, "PROCESSING", f"Processing failed: {doc.filename}",
                   doc.status_detail, "WARN")
        except Exception:
            db.rollback()
    finally:
        db.close()
