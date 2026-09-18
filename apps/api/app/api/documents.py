from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit.service import log as audit_log
from ..core.errors import Forbidden, NotFound
from ..core.security import safe_filename
from ..db.models import Document, DocumentChunk, DocumentEntity
from ..db.session import get_db
from ..schemas import ChunkOut, DocumentDetailOut, DocumentOut, EntityOut
from ..services.graph import delete_document_graph
from ..services.ingest import run_ingestion
from ..services.storage import store_upload, validate_upload
from ..tasks.runner import get_runner
from .deps import get_current_user

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", status_code=202, response_model=DocumentOut)
def upload(file: UploadFile = File(...), db: Session = Depends(get_db),
           user=Depends(get_current_user)):
    data = file.file.read()
    filename = file.filename or "file"
    ftype = validate_upload(filename, data)
    doc = Document(
        user_id=user.id, filename=safe_filename(filename), stored_path="",
        file_type=ftype, size_bytes=len(data), mime=file.content_type or "",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    stored = store_upload(user.id, doc.id, filename, data)
    doc.stored_path = stored
    db.commit()
    job_id = get_runner().submit(run_ingestion, doc.id)
    audit_log(db, user.id, "document.uploaded", actor="user", target=doc.filename,
              detail={"job_id": job_id, "type": ftype, "bytes": len(data)})
    return DocumentOut.model_validate(doc)


@router.get("", response_model=list[DocumentOut])
def list_documents(limit: int = Query(default=100, ge=1, le=200),
                   offset: int = Query(default=0, ge=0),
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(select(Document).where(Document.user_id == user.id)
                      .order_by(Document.created_at.desc())
                      .limit(limit).offset(offset)).scalars().all()
    return [DocumentOut.model_validate(r) for r in rows]


@router.get("/{doc_id}", response_model=DocumentDetailOut)
def get_document(doc_id: str, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user.id:
        raise NotFound("Document not found")
    entities = db.execute(select(DocumentEntity).where(
        DocumentEntity.document_id == doc_id)).scalars().all()
    chunks = db.execute(select(DocumentChunk).where(
        DocumentChunk.document_id == doc_id).order_by(DocumentChunk.chunk_index)
        .limit(200)).scalars().all()
    return DocumentDetailOut(
        **DocumentOut.model_validate(doc).model_dump(),
        text_preview=doc.text[:4000],
        entities=[EntityOut(kind=e.kind, value=e.value, field=e.field,
                            confidence=e.confidence, evidence=e.evidence, page=e.page)
                  for e in entities],
        chunks=[ChunkOut(id=c.id, chunk_index=c.chunk_index, page=c.page, text=c.text)
                for c in chunks],
        chunk_count=len(chunks),
    )


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user.id:
        raise Forbidden("Document not found")
    db.execute(sa_delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
    db.execute(sa_delete(DocumentEntity).where(DocumentEntity.document_id == doc_id))
    delete_document_graph(db, user.id, doc_id)
    p = Path(doc.stored_path)
    if p.exists():
        p.unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
    audit_log(db, user.id, "document.deleted", actor="user", target=doc.filename)
    return None
