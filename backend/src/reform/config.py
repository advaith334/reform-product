"""Environment-backed settings."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS_DIR = PROJECT_ROOT / "documents"
OUTPUT_DIR = PROJECT_ROOT / "out"
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"

#: Where the API writes files uploaded through the browser. Kept out of
#: DOCUMENTS_DIR so `reform extract` still means "the curated sample set".
UPLOADS_DIR = PROJECT_ROOT / "uploads"

# Must run before the module-level os.environ.get calls below, or a model name
# set in .env would be silently ignored in favour of the default.
load_dotenv(PROJECT_ROOT / ".env")

#: Alias so the pipeline tracks Mistral's current OCR release. Pin a dated id
#: (e.g. "mistral-ocr-4-1") if reproducibility matters more than upgrades.
OCR_MODEL = os.environ.get("MISTRAL_OCR_MODEL", "mistral-ocr-latest")

#: Model for the second-stage field extraction over the OCR markdown. The OCR
#: endpoint's own document-annotation feature was tried first and rejected: on these
#: documents it left most fields null and looped on string fields. See extraction.py.
EXTRACTION_MODEL = os.environ.get("MISTRAL_EXTRACTION_MODEL", "mistral-large-latest")

#: Browsers the dev frontend is served from; comma-separated to override.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]


def mistral_api_key() -> str:
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise RuntimeError("MISTRAL_API_KEY is not set (expected in .env)")
    return key


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to .env, e.g.\n"
            "  DATABASE_URL=postgresql://postgres:postgres@localhost:5432/reform"
        )
    return url
