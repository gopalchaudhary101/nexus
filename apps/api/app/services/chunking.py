"""Semantic-ish chunking: paragraph-aware, page-aware, fixed overlap.

Chunk size targets ~target_chars with `overlap_chars` of carry-over so
sentences near boundaries remain retrievable from both neighbours.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    page: int
    index: int = 0


def _flush(buf: list[str], page: int, overlap: int, out: list[Chunk]) -> list[str]:
    if not buf:
        return []
    text = " ".join(buf).strip()
    if len(text) < 40 and not out:
        return [text]
    if len(text) < 40:
        buf2 = buf[:]
        return buf2
    out.append(Chunk(text=text, page=page, index=len(out)))
    # carry-over for overlap
    tail = text[-overlap:] if overlap > 0 else ""
    return [tail] if tail else []


def chunk_text(text: str, pages: list[str] | None = None,
               target: int = 700, overlap: int = 120) -> list[Chunk]:
    out: list[Chunk] = []
    if pages:
        for pno, page in enumerate(pages, start=1):
            buf: list[str] = []
            for para in page.split("\n"):
                para = para.strip()
                if not para:
                    continue
                buf.append(para)
                if sum(len(b) for b in buf) >= target:
                    carry = _flush(buf, pno, overlap, out)
                    buf = carry
            if buf:
                _flush(buf, pno, 0, out)
    else:
        buf = []
        for para in text.split("\n"):
            para = para.strip()
            if not para:
                continue
            buf.append(para)
            if sum(len(b) for b in buf) >= target:
                carry = _flush(buf, 1, overlap, out)
                buf = carry
        if buf:
            _flush(buf, 1, 0, out)
    for i, c in enumerate(out):
        c.index = i
    return [c for c in out if len(c.text) >= 30]
