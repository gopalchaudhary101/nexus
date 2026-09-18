"""Hybrid retrieval: vector similarity + BM25, with metadata filtering.

Backends
    - Local (default, fully verified): loads the user's chunks (capped at
      LOCAL_SCAN_CAP) and scores with numpy cosine + a BM25 pass.
    - pgvector (Postgres deployments): cosine via `<=>` in SQL when
      NEXUS_USE_PGVECTOR=1 and the embedding column is populated.

Retrieval is per-user only: the query is always filtered by user_id, which
is the tenant-isolation guarantee for search.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select

from ..core.config import get_settings
from ..db.models import Document, DocumentChunk
from ..llm.base import Embedder

LOCAL_SCAN_CAP = 4000
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "is", "are", "was",
    "my", "i", "me", "what", "when", "which", "who", "how", "do", "does", "did",
    "this", "that", "with", "for", "at", "by", "it", "be", "there", "your",
}


@dataclass
class RetrievedChunk:
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


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class HybridRetriever:
    def __init__(self, embedder: Embedder, vector_weight: float = 0.6) -> None:
        self.embedder = embedder
        self.vector_weight = vector_weight
        self.bm25_weight = 1.0 - vector_weight
        self.k1 = 1.5
        self.b = 0.75

    # ── public ─────────────────────────────────────────────────────────
    def search(self, db, user_id: str, query: str, top_k: int = 5,
               doc_type: str | None = None) -> list[RetrievedChunk]:
        settings = get_settings()
        if settings.using_postgres and settings.use_pgvector:
            hits = self._search_pgvector(db, user_id, query, top_k, doc_type)
            if hits is not None:
                return hits
        return self._search_local(db, user_id, query, top_k, doc_type)

    # ── local (numpy) backend ──────────────────────────────────────────
    def _search_local(self, db, user_id: str, query: str, top_k: int,
                      doc_type: str | None) -> list[RetrievedChunk]:
        stmt = (
            select(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(DocumentChunk.user_id == user_id)
            .where(Document.status == "READY")
            .limit(LOCAL_SCAN_CAP)
        )
        if doc_type:
            stmt = stmt.where(Document.doc_type == doc_type.upper())
        rows = db.execute(stmt).all()
        if not rows:
            return []
        chunks = [r[0] for r in rows]
        docs = {d.id: d for _, d in rows}

        qvec = self.embedder.embed(query)
        mat = np.zeros((len(chunks), self.embedder.dim), dtype=np.float32)
        for i, c in enumerate(chunks):
            try:
                mat[i] = np.asarray(json.loads(c.embedding_json), dtype=np.float32)
            except (ValueError, TypeError):
                continue
        vec_scores = np.clip(mat @ qvec, 0.0, 1.0)

        texts = [c.text for c in chunks]
        bm = self._bm25_scores(query, texts)
        bm_max = float(bm.max()) if bm.size else 0.0
        bm_norm = bm / bm_max if bm_max > 0 else bm

        combined = self.vector_weight * vec_scores + self.bm25_weight * bm_norm
        order = np.argsort(-combined)
        out: list[RetrievedChunk] = []
        for idx in order[:top_k]:
            c = chunks[idx]
            d = docs[c.document_id]
            out.append(RetrievedChunk(
                chunk_id=c.id, document_id=c.document_id, document_name=d.filename,
                doc_type=d.doc_type, page=c.page, chunk_index=c.chunk_index,
                text=c.text,
                vector_score=round(float(vec_scores[idx]), 4),
                bm25_score=round(float(bm_norm[idx]), 4),
                score=round(float(combined[idx]), 4),
            ))
        return out

    # ── pgvector backend ───────────────────────────────────────────────
    def _search_pgvector(self, db, user_id: str, query: str, top_k: int,
                         doc_type: str | None) -> list[RetrievedChunk] | None:
        try:
            import sqlalchemy as sa
            qvec = self.embedder.embed(query)
            vec_literal = "[" + ",".join(f"{v:.6f}" for v in qvec.tolist()) + "]"
            params: dict = {"u": user_id, "vec": vec_literal, "k": top_k}
            where = ("c.user_id = :u AND d.status = 'READY'")
            if doc_type:
                where += " AND d.doc_type = :dt"
                params["dt"] = doc_type.upper()
            sql = sa.text(
                f"""
                SELECT c.id, c.document_id, c.chunk_index, c.page, c.text,
                       1 - (c.embedding <=> :vec::vector) AS vec_score
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE {where}
                ORDER BY c.embedding <=> :vec::vector
                LIMIT :k
                """
            )
            rows = db.execute(sql, params).all()
        except Exception:
            # pgvector not available on this cluster — fall back to local.
            return None
        # Re-blend with BM25 over the top-k window for ranking quality.
        bm = self._bm25_scores(query, [r[4] for r in rows])
        bm_max = float(bm.max()) if bm.size else 0.0
        bm_norm = bm / bm_max if bm_max > 0 else bm
        out: list[RetrievedChunk] = []
        for r, b in zip(rows, bm_norm, strict=True):
            vec = float(r[5])
            out.append(RetrievedChunk(
                chunk_id=r[0], document_id=r[1], document_name=r[1],
                doc_type="", page=int(r[3]), chunk_index=int(r[2]), text=r[4],
                vector_score=round(vec, 4), bm25_score=round(float(b), 4),
                score=round(self.vector_weight * vec + self.bm25_weight * float(b), 4),
            ))
        return out

    # ── BM25 ───────────────────────────────────────────────────────────
    def _bm25_scores(self, query: str, texts: list[str]) -> np.ndarray:
        q_tokens = tokenize(query)
        if not q_tokens or not texts:
            return np.zeros(len(texts), dtype=np.float32)
        doc_tokens = [tokenize(t) for t in texts]
        n = len(doc_tokens)
        df: dict[str, int] = {}
        for dt in doc_tokens:
            for t in set(dt):
                df[t] = df.get(t, 0) + 1
        avgdl = (sum(len(dt) for dt in doc_tokens) / n) or 1.0
        scores = np.zeros(n, dtype=np.float32)
        for i, dt in enumerate(doc_tokens):
            if not dt:
                continue
            tf: dict[str, int] = {}
            for t in dt:
                tf[t] = tf.get(t, 0) + 1
            s = 0.0
            for q in q_tokens:
                if q not in tf:
                    continue
                idf = math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
                f = tf[q]
                s += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * len(dt) / avgdl))
            scores[i] = s
        return scores
