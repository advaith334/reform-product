"""Read-side queries.

Kept separate from :mod:`reform.db`, which owns the write path shared with the CLI.
Everything here returns API DTOs rather than raw rows, so the route handlers stay thin.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import psycopg

from ..models import DOCUMENT_FIELDS, LINE_ITEM_FIELDS
from .schemas import DocumentDetail, DocumentSummary, ExtractedField, LineItemOut


def _float(value: Any) -> Optional[float]:
    """numeric() comes back as Decimal; JSON wants a float."""
    return float(value) if isinstance(value, Decimal) else value


def _display(value: Any) -> Optional[str]:
    """Stringify a column for display without inventing formatting.

    Decimals are normalised so a numeric(14,2) total reads as "3515.55" and a
    quantity of 1 reads as "1" rather than "1.00" -- but nothing is rounded.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


def _summary_row_to_dto(row: dict[str, Any]) -> DocumentSummary:
    return DocumentSummary(
        id=str(row["id"]),
        source_file=row["source_file"],
        original_filename=row.get("original_filename"),
        status=row["status"],
        error=row.get("error"),
        uploaded_at=row.get("uploaded_at"),
        extracted_at=row.get("extracted_at"),
        identifier=row.get("invoice_number") or row.get("bill_of_lading_number"),
        line_item_count=row.get("line_item_count") or 0,
        ocr_avg_confidence=_float(row.get("ocr_avg_confidence")),
        ocr_min_confidence=_float(row.get("ocr_min_confidence")),
        worst_field_confidence=_float(row.get("worst_field_confidence")),
        unmatched_field_count=row.get("unmatched_field_count") or 0,
    )


#: Aggregates the list and detail views share. Correlated subqueries rather than joins
#: so a document with no line items still comes back with zeroes instead of vanishing.
_SUMMARY_SELECT = """
    select d.*,
           (select count(*) from line_items li where li.document_id = d.id)
             as line_item_count,
           (select min(fc.min_confidence) from field_confidences fc
             where fc.document_id = d.id and fc.field_value is not null)
             as worst_field_confidence,
           (select count(*) from field_confidences fc
             where fc.document_id = d.id
               and fc.field_value is not null
               and fc.match_method = 'unmatched')
             as unmatched_field_count
      from documents d
"""


def list_documents(conn: psycopg.Connection) -> list[DocumentSummary]:
    with conn.cursor() as cur:
        cur.execute(_SUMMARY_SELECT + " order by d.uploaded_at desc, d.source_file")
        return [_summary_row_to_dto(row) for row in cur.fetchall()]


def _fetch_document_row(conn: psycopg.Connection, document_id: str) -> Optional[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(_SUMMARY_SELECT + " where d.id = %s", (document_id,))
        return cur.fetchone()


def _confidence_index(
    conn: psycopg.Connection, document_id: str
) -> dict[tuple[Optional[str], str], dict[str, Any]]:
    """Every confidence row for a document, keyed by (line_item_id, field_name).

    One query for the whole document; the field loops below are pure dict lookups.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            select line_item_id, field_name, field_value,
                   min_confidence, mean_confidence, match_method, match_ratio
              from field_confidences
             where document_id = %s
            """,
            (document_id,),
        )
        return {
            (str(row["line_item_id"]) if row["line_item_id"] else None, row["field_name"]): row
            for row in cur.fetchall()
        }


def _field(
    name: str,
    value: Any,
    score: Optional[dict[str, Any]],
) -> ExtractedField:
    """Pair a column value with its confidence row.

    The value comes from ``documents``/``line_items`` -- the confidence row's own
    ``field_value`` is only the string the matcher saw, so it is not authoritative here.

    A field the model never extracted carries no confidence at all: the matcher records
    it as 'unmatched', but there is nothing to be unconfident about, so the score is
    dropped and the UI shows a plain placeholder.
    """
    if value is None:
        return ExtractedField(name=name, value=None)

    return ExtractedField(
        name=name,
        value=_display(value),
        min_confidence=_float(score["min_confidence"]) if score else None,
        mean_confidence=_float(score["mean_confidence"]) if score else None,
        match_method=score["match_method"] if score else None,
        match_ratio=_float(score["match_ratio"]) if score else None,
    )


def get_document(conn: psycopg.Connection, document_id: str) -> Optional[DocumentDetail]:
    row = _fetch_document_row(conn, document_id)
    if row is None:
        return None

    scores = _confidence_index(conn, document_id)

    # DOCUMENT_FIELDS / LINE_ITEM_FIELDS drive the order, so the UI shows fields in
    # the same sequence the extraction schema declares them.
    fields = [_field(name, row.get(name), scores.get((None, name))) for name in DOCUMENT_FIELDS]

    with conn.cursor() as cur:
        cur.execute(
            "select * from line_items where document_id = %s order by line_no",
            (document_id,),
        )
        line_rows = cur.fetchall()

    line_items = [
        LineItemOut(
            id=str(line["id"]),
            line_no=line["line_no"],
            fields=[
                _field(name, line.get(name), scores.get((str(line["id"]), name)))
                for name in LINE_ITEM_FIELDS
            ],
        )
        for line in line_rows
    ]

    return DocumentDetail(
        **_summary_row_to_dto(row).model_dump(),
        ocr_model=row.get("ocr_model"),
        extraction_model=row.get("extraction_model"),
        fields=fields,
        line_items=line_items,
    )


def get_file_location(conn: psycopg.Connection, document_id: str) -> Optional[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "select stored_path, content_type, original_filename, source_file"
            "  from documents where id = %s",
            (document_id,),
        )
        return cur.fetchone()
