"""Turn OCR markdown into validated ShipmentDocument rows, with per-field confidence.

Why two stages rather than one? ``ocr.process`` can do structured extraction itself via
``document_annotation_format``, and that was the first implementation. On these trade
documents it failed badly: it returned null for fields plainly present in the markdown
(invoice numbers, shipper and consignee names, every quantity and price) and degenerated
into repetition loops on string fields -- an ``hts_code`` came back as
``"8507600020 EAR99 CN 46/6159 CN 46/6159 CN ..."`` repeated for a kilobyte. Adding a
steering ``document_annotation_prompt`` did not help.

The OCR markdown itself is excellent, so the fix is to keep the OCR call and hand its
text to a strong general model via ``chat.parse``. That reproduces the documents'
ground truth exactly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from mistralai.client import Mistral

from .config import EXTRACTION_MODEL
from .confidence import FieldConfidence, OCRWord, score_field
from .models import (
    DOCUMENT_FIELDS,
    LINE_ITEM_FIELDS,
    NUMERIC_FIELDS,
    ShipmentDocument,
)
from .ocr import run_ocr

SYSTEM_PROMPT = (
    "You extract structured data from international trade documents -- bills of lading "
    "and commercial invoices. Copy every value verbatim from the document. Never add "
    "commentary, notes or parentheticals to a value. Use null only when a field is "
    "genuinely absent from the document; do not guess. For line items, take the "
    "extended/line total rather than the unit price, and keep tariff codes as digit "
    "strings with any leading zeros intact."
)


@dataclass
class ExtractionResult:
    """Everything one document yields -- cached to disk so `load` never calls Mistral."""

    source_file: str
    document: ShipmentDocument
    markdown: str
    ocr_model: str
    extraction_model: str
    ocr_avg_confidence: Optional[float]
    ocr_min_confidence: Optional[float]
    document_confidences: list[FieldConfidence]
    #: Parallel to ``document.line_items`` -- one list of field scores per line.
    line_item_confidences: list[list[FieldConfidence]]
    #: The scored OCR words, kept so `reform rescore` can re-run the confidence
    #: matcher after a tuning change without paying for OCR again.
    words: list[OCRWord]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "document": self.document.model_dump(),
            "markdown": self.markdown,
            "ocr_model": self.ocr_model,
            "extraction_model": self.extraction_model,
            "ocr_avg_confidence": self.ocr_avg_confidence,
            "ocr_min_confidence": self.ocr_min_confidence,
            "document_confidences": [asdict(c) for c in self.document_confidences],
            "line_item_confidences": [
                [asdict(c) for c in line] for line in self.line_item_confidences
            ],
            "words": [asdict(w) for w in self.words],
        }

    @classmethod
    def from_json_dict(cls, raw: dict[str, Any]) -> "ExtractionResult":
        return cls(
            source_file=raw["source_file"],
            document=ShipmentDocument.model_validate(raw["document"]),
            markdown=raw["markdown"],
            ocr_model=raw.get("ocr_model", ""),
            extraction_model=raw.get("extraction_model", ""),
            ocr_avg_confidence=raw.get("ocr_avg_confidence"),
            ocr_min_confidence=raw.get("ocr_min_confidence"),
            document_confidences=[FieldConfidence(**c) for c in raw["document_confidences"]],
            line_item_confidences=[
                [FieldConfidence(**c) for c in line] for line in raw["line_item_confidences"]
            ],
            words=[OCRWord(**w) for w in raw.get("words", [])],
        )


def annotate(client: Mistral, markdown: str) -> ShipmentDocument:
    """Pull the structured fields out of OCR markdown."""
    response = client.chat.parse(
        model=EXTRACTION_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Extract the shipment fields from this document:\n\n{markdown}",
            },
        ],
        response_format=ShipmentDocument,
        temperature=0,
    )
    parsed = response.choices[0].message.parsed
    return parsed if parsed is not None else ShipmentDocument()


def score_document(
    document: ShipmentDocument, words: list[OCRWord]
) -> tuple[list[FieldConfidence], list[list[FieldConfidence]]]:
    """Score every extracted field against the OCR word stream."""
    doc_scores = [
        score_field(words, name, getattr(document, name), numeric=name in NUMERIC_FIELDS)
        for name in DOCUMENT_FIELDS
    ]
    line_scores = [
        [
            score_field(words, name, getattr(item, name), numeric=name in NUMERIC_FIELDS)
            for name in LINE_ITEM_FIELDS
        ]
        for item in document.line_items
    ]
    return doc_scores, line_scores


def rescore(result: ExtractionResult) -> ExtractionResult:
    """Recompute confidences from cached OCR words. No API calls."""
    result.document_confidences, result.line_item_confidences = score_document(
        result.document, result.words
    )
    return result


def extract(client: Mistral, pdf_path: Path) -> ExtractionResult:
    """OCR one PDF, extract its fields, and score each field against the OCR words."""
    ocr = run_ocr(client, pdf_path)
    document = annotate(client, ocr.markdown)
    doc_scores, line_scores = score_document(document, ocr.words)

    return ExtractionResult(
        source_file=pdf_path.name,
        document=document,
        markdown=ocr.markdown,
        ocr_model=ocr.model,
        extraction_model=EXTRACTION_MODEL,
        ocr_avg_confidence=ocr.avg_confidence,
        ocr_min_confidence=ocr.min_confidence,
        document_confidences=doc_scores,
        line_item_confidences=line_scores,
        words=ocr.words,
    )
