"""The background job that turns an upload into rows.

This is the same pipeline the CLI runs -- ``extraction.extract`` then ``db.load`` --
wrapped so that its progress and its failures are visible in the ``documents`` table
instead of only in the server log.
"""

from __future__ import annotations

import logging
import traceback
from pathlib import Path

from psycopg_pool import ConnectionPool

from .. import db
from ..extraction import extract
from ..ocr import make_client

logger = logging.getLogger(__name__)


def _set_status(pool: ConnectionPool, document_id: str, status: str, error: str | None = None) -> None:
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "update documents set status = %s, error = %s where id = %s",
            (status, error, document_id),
        )


def process_upload(pool: ConnectionPool, document_id: str, path: Path) -> None:
    """OCR, extract and persist one uploaded file.

    Defined as a plain ``def`` so Starlette runs it in the threadpool: the Mistral and
    psycopg clients underneath are both synchronous, and running them on the event loop
    would stall every other request for the duration of the OCR call.

    Never raises -- a failure is recorded on the row so the UI can show it.
    """
    _set_status(pool, document_id, "processing")
    try:
        result = extract(make_client(), path)
        with pool.connection() as conn:
            db.load(conn, result)
    except Exception as exc:  # noqa: BLE001 -- the row is the error channel
        logger.exception("Extraction failed for document %s", document_id)
        message = f"{type(exc).__name__}: {exc}".strip()
        try:
            _set_status(pool, document_id, "failed", message[:2000])
        except Exception:  # the database itself is the thing that broke
            logger.error("Could not record failure for %s:\n%s", document_id, traceback.format_exc())
