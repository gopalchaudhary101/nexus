from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..llm.factory import get_embedder, get_llm
from ..rag.answers import answer_question
from ..rag.retriever import HybridRetriever
from ..schemas import AskIn, AskOut, HitOut, SearchIn, SearchOut, SourceOut
from .deps import get_current_user

router = APIRouter(tags=["search"])


def _retriever() -> HybridRetriever:
    return HybridRetriever(get_embedder())


@router.post("/search", response_model=SearchOut)
def search(body: SearchIn, db: Session = Depends(get_db),
           user=Depends(get_current_user)):
    hits = _retriever().search(db, user.id, body.query, top_k=body.top_k,
                               doc_type=body.doc_type)
    return SearchOut(
        query=body.query,
        hits=[HitOut(chunk_id=h.chunk_id, document_id=h.document_id,
                     document_name=h.document_name, doc_type=h.doc_type,
                     page=h.page, chunk_index=h.chunk_index, text=h.text,
                     vector_score=h.vector_score, bm25_score=h.bm25_score,
                     score=h.score) for h in hits],
    )


@router.post("/ask", response_model=AskOut)
def ask(body: AskIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    hits = _retriever().search(db, user.id, body.question, top_k=body.top_k,
                               doc_type=body.doc_type)
    ga = answer_question(body.question, hits, llm=get_llm())
    return AskOut(
        question=body.question,
        answer=ga.answer,
        confidence=ga.confidence,
        grounded=ga.grounded,
        sources=[SourceOut(**s) for s in ga.sources],
        provider=ga.provider or get_llm().name,
    )
