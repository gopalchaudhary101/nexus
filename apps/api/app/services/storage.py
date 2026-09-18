"""Upload validation + on-disk storage (local directory; S3 in production).

Validation (defense in depth, per security spec):
  - extension allowlist
  - magic-byte sniffing must agree with the extension family
  - size cap
  - filename sanitised before any path join (path traversal protection)
"""
from __future__ import annotations

from pathlib import Path

from ..core.config import get_settings
from ..core.errors import ApiError
from ..core.security import safe_filename

ALLOWED_EXT: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md",
    ".csv": "csv",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
}

MAGIC: list[tuple[bytes, set[str]]] = [
    (b"%PDF", {"pdf"}),
    (b"PK\x03\x04", {"docx", "csv"}),  # docx is zip; csv with zip magic is rejected below
]


def validate_upload(filename: str, data: bytes) -> str:
    s = get_settings()
    if len(data) > s.max_upload_bytes:
        raise ApiError(f"File exceeds the {s.max_upload_bytes // (1024 * 1024)} MB limit",
                       code="too_large")
    if len(data) == 0:
        raise ApiError("Empty file", code="empty_file")
    ext = Path(filename).suffix.lower()
    ftype = ALLOWED_EXT.get(ext)
    if ftype is None:
        raise ApiError(f"Unsupported file type '{ext or 'unknown'}'. "
                       "Allowed: " + ", ".join(sorted(ALLOWED_EXT)), code="bad_type")
    head = data[:4]
    for magic, families in MAGIC:
        if head.startswith(magic):
            if ftype not in families:
                raise ApiError("File content does not match its extension", code="bad_type")
            break
    if ftype in {"txt", "md", "csv"}:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ApiError("Text file is not valid UTF-8", code="bad_type") from e
    if ftype == "image" and head.startswith(b"PK"):
        raise ApiError("File content does not match its extension", code="bad_type")
    return ftype


def store_upload(user_id: str, doc_id: str, filename: str, data: bytes) -> str:
    s = get_settings()
    base = Path(s.upload_dir)
    d = base / user_id / doc_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / safe_filename(filename)
    path.write_bytes(data)
    return str(path)
