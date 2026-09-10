"""Persist extraction results into Postgres.

Loading is idempotent: a document is keyed by ``source_file``, and its line items and
confidence rows are replaced wholesale on each load rather than appended.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import psycopg
from psycopg.rows import dict_row

from .config import SCHEMA_PATH, database_url
from .confidence import FieldConfidence
from .models import LINE_ITEM_FIELDS
from .extraction import ExtractionResult


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url(), row_factory=dict_row)


def init_schema(conn: psycopg.Connection) -> None:
    """Apply sql/schema.sql. Safe to call repeatedly."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA_PATH.read_text())
    conn.commit()


def _money(value: Any) -> Optional[Decimal]:
    """Go through str so a float never introduces binary rounding into numeric()."""
    return None if value is None else Decimal(str(value))


def _confidence_rows(
    document_id: str,
    line_item_id: Optional[str],
    scores: list[FieldConfidence],
) -> list[tuple]:
    return [
        (
            document_id,
            line_item_id,
            score.field_name,
            score.field_value,
            score.min_confidence,
            score.mean_confidence,
            score.match_method,
            score.match_ratio,
        )
        for score in scores
    ]


def load(conn: psycopg.Connection, result: ExtractionResult) -> str:
    """Upsert one extraction result. Returns the document id."""
    doc = result.document

    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            insert into documents (
                source_file, bill_of_lading_number, invoice_number,
                shipper_name, shipper_address, consignee_name, consignee_address,
                total_value_of_goods, ocr_markdown,
                ocr_avg_confidence, ocr_min_confidence, ocr_model, extraction_model,
                extracted_at, original_filename, status, error
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s, 'complete', null)
            on conflict (source_file) do update set
                bill_of_lading_number = excluded.bill_of_lading_number,
                invoice_number        = excluded.invoice_number,
                shipper_name          = excluded.shipper_name,
                shipper_address       = excluded.shipper_address,
                consignee_name        = excluded.consignee_name,
                consignee_address     = excluded.consignee_address,
                total_value_of_goods  = excluded.total_value_of_goods,
                ocr_markdown          = excluded.ocr_markdown,
                ocr_avg_confidence    = excluded.ocr_avg_confidence,
                ocr_min_confidence    = excluded.ocr_min_confidence,
                ocr_model             = excluded.ocr_model,
                extraction_model      = excluded.extraction_model,
                extracted_at          = excluded.extracted_at,
                -- A row inserted by the API is 'processing' until this lands.
                -- Its original_filename is already set; don't clobber it.
                original_filename     = coalesce(documents.original_filename, excluded.original_filename),
                status                = 'complete',
                error                 = null
            returning id
            """,
            (
                result.source_file,
                doc.bill_of_lading_number,
                doc.invoice_number,
                doc.shipper_name,
                doc.shipper_address,
                doc.consignee_name,
                doc.consignee_address,
                _money(doc.total_value_of_goods),
                result.markdown,
                result.ocr_avg_confidence,
                result.ocr_min_confidence,
                result.ocr_model,
                result.extraction_model,
                result.source_file,
            ),
        )
        document_id = cur.fetchone()["id"]

        # Replace rather than merge, so a re-extraction that finds fewer lines does
        # not leave stale ones behind. Line-item confidences cascade with their line.
        cur.execute("delete from line_items where document_id = %s", (document_id,))
        cur.execute("delete from field_confidences where document_id = %s", (document_id,))

        confidence_rows = _confidence_rows(document_id, None, result.document_confidences)

        for index, item in enumerate(doc.line_items, start=1):
            cur.execute(
                """
                insert into line_items (document_id, line_no, quantity, description, value, hts_code)
                values (%s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    document_id,
                    index,
                    _money(item.quantity),
                    item.description,
                    _money(item.value),
                    item.hts_code,
                ),
            )
            line_item_id = cur.fetchone()["id"]
            scores = (
                result.line_item_confidences[index - 1]
                if index - 1 < len(result.line_item_confidences)
                else []
            )
            confidence_rows.extend(_confidence_rows(document_id, line_item_id, scores))

        if confidence_rows:
            cur.executemany(
                """
                insert into field_confidences (
                    document_id, line_item_id, field_name, field_value,
                    min_confidence, mean_confidence, match_method, match_ratio
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                confidence_rows,
            )

    return str(document_id)


__all__ = ["connect", "init_schema", "load", "LINE_ITEM_FIELDS"]
