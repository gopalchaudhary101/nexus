"""Personal Knowledge Graph (relational storage).

Entities: USER, DOCUMENT, MERCHANT, TRANSACTION (sampled), SUBSCRIPTION,
DEADLINE, RISK.
Relationships: OWNS, MENTIONS, GENERATES, RENEWS_ON, EXPIRES_ON,
PAID_FOR, RELATED_TO.

Stored in knowledge_entities/knowledge_relationships (Postgres/SQLite).
A dedicated graph DB is an optional extension — at portfolio scale the
relational form keeps the local stack simple (per architecture spec).
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.models import KnowledgeEntity, KnowledgeRelationship


def _find_entity(db: Session, user_id: str, kind: str, name: str) -> KnowledgeEntity | None:
    return db.execute(
        select(KnowledgeEntity).where(
            KnowledgeEntity.user_id == user_id,
            KnowledgeEntity.kind == kind,
            KnowledgeEntity.name == name,
        )
    ).scalars().first()


def upsert_entity(db: Session, user_id: str, kind: str, name: str,
                  attrs: dict | None = None, ref_id: str | None = None) -> str:
    name = name[:255]
    row = _find_entity(db, user_id, kind, name)
    if row is None:
        # The ingestion worker pool runs multiple documents for the same
        # user concurrently, so two jobs can both miss the SELECT above and
        # race to insert the same (user_id, kind, name) node (e.g. the
        # singleton USER node). The unique constraint on KnowledgeEntity
        # turns the loser's insert into an IntegrityError instead of a
        # silent duplicate row; a savepoint scopes that failure to just
        # this insert so the caller's outer transaction survives, and we
        # re-select to pick up the winner's row.
        try:
            # add() must happen *inside* the SAVEPOINT: only then does a
            # rollback-on-exception also expunge the pending object from
            # the session, leaving it usable for the caller's subsequent
            # commit. add()-then-begin_nested() looks equivalent but isn't
            # — the object stays pending against the outer transaction and
            # the whole session (not just this insert) ends up needing an
            # explicit rollback, which crashed the ingestion job's own
            # later commit with PendingRollbackError.
            with db.begin_nested():
                row = KnowledgeEntity(user_id=user_id, kind=kind, name=name,
                                      attrs_json=json.dumps(attrs or {}, default=str),
                                      ref_id=ref_id)
                db.add(row)
                db.flush()
        except IntegrityError:
            row = _find_entity(db, user_id, kind, name)
            assert row is not None, "insert failed on unique conflict but no row found"
    else:
        if attrs:
            row.attrs_json = json.dumps(attrs, default=str)
        if ref_id:
            row.ref_id = ref_id
    return row.id


def add_rel(db: Session, user_id: str, src_id: str, rel: str, dst_id: str) -> None:
    exists = db.execute(
        select(KnowledgeRelationship).where(
            KnowledgeRelationship.user_id == user_id,
            KnowledgeRelationship.src_id == src_id,
            KnowledgeRelationship.rel == rel,
            KnowledgeRelationship.dst_id == dst_id,
        )
    ).first()
    if exists is None:
        db.add(KnowledgeRelationship(user_id=user_id, src_id=src_id, rel=rel, dst_id=dst_id))


def rebuild_document_graph(db: Session, doc, entities: list, deadlines: list[dict]) -> None:
    from ..db.models import Document  # noqa: F401
    uid = doc.user_id
    user_node = upsert_entity(db, uid, "USER", doc.filename and _user_name(db, uid) or "User")
    doc_node = upsert_entity(db, uid, "DOCUMENT", doc.filename,
                             {"type": doc.doc_type, "status": doc.status}, ref_id=doc.id)
    add_rel(db, uid, user_node, "OWNS", doc_node)
    for e in entities:
        if e.kind in {"MERCHANT", "PERSON", "EMAIL", "URL", "ACCOUNT_REF"}:
            node = upsert_entity(db, uid, e.kind, e.value[:255],
                                 {"confidence": e.confidence, "evidence": e.evidence[:120]})
            add_rel(db, uid, doc_node, "MENTIONS", node)
    for d in deadlines:
        node = upsert_entity(db, uid, "DEADLINE", d["title"][:255],
                             {"due": d["due_date"].isoformat(), "kind": d["kind"]},
                             ref_id=None)
        add_rel(db, uid, doc_node, "GENERATES", node)


def _user_name(db: Session, user_id: str) -> str:
    from ..db.models import User
    u = db.get(User, user_id)
    return u.name if u else "User"


def delete_document_graph(db: Session, user_id: str, ref_id: str) -> None:
    node = db.execute(
        select(KnowledgeEntity).where(
            KnowledgeEntity.user_id == user_id,
            KnowledgeEntity.kind == "DOCUMENT",
            KnowledgeEntity.ref_id == ref_id,
        )
    ).scalar_one_or_none()
    if node is None:
        return
    rels = db.execute(select(KnowledgeRelationship).where(
        KnowledgeRelationship.user_id == user_id,
        (KnowledgeRelationship.src_id == node.id) | (KnowledgeRelationship.dst_id == node.id),
    )).scalars().all()
    for r in rels:
        db.delete(r)
    db.delete(node)
    db.commit()


def get_graph(db: Session, user_id: str) -> dict:
    nodes = db.execute(select(KnowledgeEntity).where(
        KnowledgeEntity.user_id == user_id)).scalars().all()
    by_id = {n.id: n for n in nodes}
    edges = db.execute(select(KnowledgeRelationship).where(
        KnowledgeRelationship.user_id == user_id)).scalars().all()
    out_nodes = [{
        "id": n.id, "kind": n.kind, "name": n.name,
        "attrs": json.loads(n.attrs_json or "{}"),
    } for n in nodes]
    out_edges = []
    for e in edges:
        if e.src_id in by_id and e.dst_id in by_id:
            out_edges.append({"src": e.src_id, "rel": e.rel, "dst": e.dst_id})
    return {"nodes": out_nodes, "edges": out_edges}
