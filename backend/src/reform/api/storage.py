"""Uploaded files on local disk.

Files are stored under a UUID name, never the user's filename: that keeps two uploads
called ``invoice.pdf`` from colliding, and stops a crafted name from escaping the
uploads directory. The original name is kept in the database for display only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

from ..config import DOCUMENTS_DIR, PROJECT_ROOT, UPLOADS_DIR

#: Mistral OCR reads PDFs and images; anything else would just fail downstream.
ALLOWED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class UploadRejected(ValueError):
    """The upload is not something the pipeline can process."""


def validate(filename: str, content_type: Optional[str], size: int) -> str:
    """Check one upload and return the suffix to store it under."""
    suffix = Path(filename or "").suffix.lower()

    if suffix not in ALLOWED_SUFFIXES and content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadRejected(
            f"Unsupported file type {content_type or suffix or 'unknown'!r}. "
            "Upload a PDF, PNG, JPEG or WebP."
        )
    if size <= 0:
        raise UploadRejected("The uploaded file is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise UploadRejected(
            f"File is {size / 1_048_576:.1f} MB; the limit is "
            f"{MAX_UPLOAD_BYTES // 1_048_576} MB."
        )

    return suffix or ALLOWED_CONTENT_TYPES.get(content_type or "", ".pdf")


def save(data: bytes, suffix: str) -> tuple[str, Path]:
    """Write the bytes under a fresh UUID name. Returns (stored_name, absolute path)."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{suffix}"
    path = UPLOADS_DIR / stored_name
    path.write_bytes(data)
    return stored_name, path


def resolve(stored_path: Optional[str], source_file: str) -> Optional[Path]:
    """Find a document's file on disk.

    ``stored_path`` is set for uploads. Rows loaded by the CLI have none, so fall back
    to the curated sample directory. Both results are confined to their own directory.
    """
    if stored_path:
        candidate = (PROJECT_ROOT / stored_path).resolve()
        if candidate.is_relative_to(UPLOADS_DIR.resolve()) and candidate.is_file():
            return candidate
        return None

    candidate = (DOCUMENTS_DIR / Path(source_file).name).resolve()
    if candidate.is_relative_to(DOCUMENTS_DIR.resolve()) and candidate.is_file():
        return candidate
    return None


def delete(stored_path: Optional[str]) -> None:
    """Remove an uploaded file. Never touches the curated documents/ directory."""
    if not stored_path:
        return
    candidate = (PROJECT_ROOT / stored_path).resolve()
    if candidate.is_relative_to(UPLOADS_DIR.resolve()):
        candidate.unlink(missing_ok=True)
