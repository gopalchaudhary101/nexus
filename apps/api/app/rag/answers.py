"""Answer generation with two honest modes.

Mock mode (default, no API key)
    Extractive and source-grounded: the answer is a real sentence taken from
    the retrieved chunks, with a citation. When no supporting sentence
    exists, NEXUS refuses instead of inventing. Confidence is derived from
    retrieval score + lexical overlap, and never exceeds 0.92.

LLM mode (provider configured)
    The provider sees the injection-safe context (rag/context.py) and must
    return {answer, confidence, sources}. Citations are validated against
    the actually-retrieved refs — hallucinated sources are dropped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ml.extraction.amounts import extract_amounts
from ml.extraction.dates import extract_dates

from ..llm.base import LLMClient
from .context import SYSTEM_PROMPT, build_ask_payload, build_context
from .retriever import RetrievedChunk

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "is", "are", "was",
    "my", "i", "me", "what", "when", "which", "who", "how", "do", "does", "did",
    "this", "that", "with", "for", "at", "by", "it", "be", "there", "your", "any",
    "about", "am", "will", "would", "can",
}

DATE_HINTS = ("when", "expire", "expiry", "renew", "due", "deadline", "valid",
              "ends", "until", "date", "renews", "lapse")
AMOUNT_HINTS = ("how much", "cost", "amount", "fee", "premium", "price", "total",
                "rent", "pay", "charge", "spend")

REFUSAL = ("I couldn't find information about this in your documents yet. "
           "Upload the relevant document (or rephrase the question) and I'll "
           "answer from the source.")


@dataclass
class GroundedAnswer:
    answer: str
    confidence: float
    grounded: bool
    sources: list[dict] = field(default_factory=list)
    provider: str = ""


def _stem(t: str) -> str:
    return t[:-1] if t.endswith("s") and len(t) > 3 else t


def _q_tokens(q: str) -> set[str]:
    return {_stem(t) for t in re.findall(r"[a-z0-9]+", q.lower()) if t not in _STOP and len(t) > 1}


def _tokens(text: str) -> set[str]:
    return {_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower())}


def _sentence_score(sentence: str, qtok: set[str]) -> int:
    return len(qtok & _tokens(sentence))


# topic synonym groups: (question hint words) -> (chunk evidence phrases)
_TOPICS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("end", "ends", "finish", "lapse"), ("valid until", "expires", "expiry", "expir", "ends", "until", "term")),
    (("expire", "expiry", "expires"), ("expires", "expiry", "expiration", "lapse", "valid until")),
    (("due", "deadline", "pay"), ("due", "payable", "pay by", "deadline", "payment is due")),
    (("flight", "trip", "travel", "depart"), ("flight", "departs", "boarding", "itinerary", "pnr")),
    (("renew", "renewal"), ("renew", "renews", "auto-renew", "renewal")),
    (("cancel", "cancellation"), ("cancel", "cancellation", "terminate", "notice")),
    (("warranty", "guarantee"), ("warranty", "guarantee", "valid until", "coverage period")),
    (("how much", "cost", "price", "amount", "fee", "premium", "rent", "charge",
      "total", "spend"), ("amount", "fee", "premium", "total", "cost", "rent",
                          "price", "charge", "inr", "₹")),
]


def _topic_match(question: str, chunk_text: str) -> int:
    ql = question.lower()
    cl = chunk_text.lower()
    n = 0
    for hints, evidence in _TOPICS:
        if any(h in ql for h in hints) and any(e in cl for e in evidence):
            n += 1
    return n


def _mock_answer(question: str, chunks: list[RetrievedChunk]) -> GroundedAnswer:
    if not chunks:
        return GroundedAnswer(REFUSAL, 0.0, False, [])
    # Refusals carry NO sources: NEXUS never invents a citation for an answer
    # it did not ground.
    q = question.lower()
    qtok = _q_tokens(question)
    want_date = any(h in q for h in DATE_HINTS)
    want_amount = any(h in q for h in AMOUNT_HINTS)

    best: tuple[float, str, str, RetrievedChunk] | None = None
    for c in chunks[:4]:
        chunk_overlap = len(qtok & _tokens(c.text))
        topics = _topic_match(question, c.text)
        for sent in _SENT_SPLIT.split(c.text):
            sent = sent.strip()
            if len(sent) < 20 or len(sent) > 400:
                continue
            overlap = _sentence_score(sent, qtok)
            dates = extract_dates(sent)
            amounts = extract_amounts(sent)
            # accept if the sentence is on-topic: strong direct overlap, or
            # weaker overlap backed by chunk-level topical agreement
            topical = (
                overlap >= 2
                or (overlap >= 1 and (chunk_overlap >= 2 or topics >= 1))
                or (overlap == 0 and topics >= 1 and chunk_overlap >= 2)
            )
            good = False
            if want_date and dates and topical or want_amount and amounts and topical or not (want_date or want_amount) and overlap >= 2 and chunk_overlap >= 3:
                good = True
            if not good:
                continue
            score = (overlap * 0.2 + c.score * 0.35 + (0.15 if dates else 0)
                     + (0.05 if amounts else 0) + chunk_overlap * 0.05 + topics * 0.1)
            if best is None or score > best[0]:
                best = (score, sent, f"{c.document_name} — Page {c.page}", c)

    if best is None:
        return GroundedAnswer(REFUSAL, 0.0, False, [])
    score, sent, ref, c = best
    confidence = round(min(0.92, 0.4 + score * 0.8), 2)
    return GroundedAnswer(
        f"According to {ref}: “{sent}”",
        confidence,
        True,
        _sources([c]),
    )


def _sources(chunks: list[RetrievedChunk], weak: bool = False) -> list[dict]:
    out = []
    for c in chunks:
        out.append({
            "document_id": c.document_id,
            "document_name": c.document_name,
            "page": c.page,
            "chunk_index": c.chunk_index,
            "similarity": round(c.score * (0.5 if weak else 1.0), 3),
            "ref": f"{c.document_name} — Page {c.page}",
        })
    return out


def _llm_answer(llm: LLMClient, question: str, chunks: list[RetrievedChunk]) -> GroundedAnswer:
    from ..llm.providers import chat_json

    context = build_context(chunks)
    payload = build_ask_payload(question, context)
    data = chat_json(llm, SYSTEM_PROMPT, payload)
    answer = str(data.get("answer", "")).strip()
    try:
        conf = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = round(max(0.0, min(1.0, conf)), 2)
    valid_refs = {f"{c.document_name} — Page {c.page}" for c in chunks}
    by_ref = {f"{c.document_name} — Page {c.page}": c for c in chunks}
    sources: list[dict] = []
    for s in data.get("sources", []) or []:
        key = s if isinstance(s, str) else str(s)
        if key in by_ref:
            c = by_ref[key]
            sources.append({
                "document_id": c.document_id, "document_name": c.document_name,
                "page": c.page, "chunk_index": c.chunk_index,
                "similarity": round(c.score, 3), "ref": key,
            })
    if not answer:
        return GroundedAnswer(REFUSAL, 0.0, False, [], llm.name)
    grounded = bool(sources) or bool(valid_refs & set(str(x) for x in data.get("sources", [])))
    return GroundedAnswer(answer, conf, grounded, sources or _sources(chunks[:1], weak=True),
                          llm.name)


def answer_question(question: str, chunks: list[RetrievedChunk],
                    llm: LLMClient | None = None) -> GroundedAnswer:
    if llm is not None and not llm.is_mock:
        try:
            return _llm_answer(llm, question, chunks)
        except Exception:
            # Provider failure must not masquerade as a successful answer:
            # fall back to the grounded extractive path.
            pass
    return _mock_answer(question, chunks)
