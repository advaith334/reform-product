"""Response DTOs.

The frontend renders every extracted value through one component, so the API hands it
one shape -- :class:`ExtractedField` -- for both document-level and line-level fields.
Value and confidence travel together; the UI never has to join them itself.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ExtractedField(BaseModel):
    """One extracted value with the OCR confidence that backs it.

    ``min_confidence`` is the score the UI colours by: it is the worst-scoring OCR word
    among those that back this value, so it answers "how much should I distrust the
    weakest part of this?" rather than "how good is it on average".
    """

    name: str
    #: Always stringified -- the UI displays it verbatim and never does arithmetic.
    value: Optional[str] = None
    min_confidence: Optional[float] = None
    mean_confidence: Optional[float] = None
    #: 'exact' | 'fuzzy' | 'unmatched', or None when the field was not extracted.
    match_method: Optional[str] = None
    match_ratio: Optional[float] = None


class LineItemOut(BaseModel):
    id: str
    line_no: int
    fields: list[ExtractedField]


class DocumentSummary(BaseModel):
    id: str
    source_file: str
    original_filename: Optional[str] = None
    status: str
    error: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    extracted_at: Optional[datetime] = None
    #: A quick identity for the list view: invoice number, else B/L number.
    identifier: Optional[str] = None
    line_item_count: int = 0
    ocr_avg_confidence: Optional[float] = None
    ocr_min_confidence: Optional[float] = None
    #: Worst per-field confidence across the whole document -- what to triage on.
    worst_field_confidence: Optional[float] = None
    unmatched_field_count: int = 0


class DocumentDetail(DocumentSummary):
    ocr_model: Optional[str] = None
    extraction_model: Optional[str] = None
    fields: list[ExtractedField] = []
    line_items: list[LineItemOut] = []


class UploadAccepted(BaseModel):
    id: str
    status: str
    original_filename: str
