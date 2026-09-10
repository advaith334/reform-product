"""Read a PDF with Mistral OCR, keeping the word-level confidence scores.

This stage only turns pixels into text. Pulling structured fields out of that text is
the job of ``extraction.py``.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# mistralai v2 moved every import path -- it is `mistralai.client`, not `mistralai`.
# v1-era tutorials will not run against the installed SDK.
from mistralai.client import Mistral

from .config import OCR_MODEL, mistral_api_key
from .confidence import OCRWord, build_words


@dataclass
class OCRResult:
    """Page text plus the confidence signal that backs it."""

    markdown: str
    words: list[OCRWord]
    model: str
    avg_confidence: Optional[float]
    min_confidence: Optional[float]


def make_client() -> Mistral:
    return Mistral(api_key=mistral_api_key())


def _page_aggregates(pages: list[Any]) -> tuple[Optional[float], Optional[float]]:
    """Mean of the per-page averages, and the worst per-page minimum."""
    averages, minimums = [], []
    for page in pages:
        scores = getattr(page, "confidence_scores", None)
        if scores is None:
            continue
        averages.append(float(scores.average_page_confidence_score))
        minimums.append(float(scores.minimum_page_confidence_score))
    if not averages:
        return None, None
    return sum(averages) / len(averages), min(minimums)


def run_ocr(client: Mistral, pdf_path: Path) -> OCRResult:
    response = client.ocr.process(
        model=OCR_MODEL,
        document={
            # Inline base64 rather than files.upload + signed URL: these documents are
            # small, and this leaves nothing behind in Mistral's file storage.
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,"
            f"{base64.b64encode(pdf_path.read_bytes()).decode()}",
        },
        # The only granularity that populates per-word scores, which the field-level
        # confidence matcher needs. It fills the page aggregates too.
        confidence_scores_granularity="word",
        include_image_base64=False,
    )

    pages = list(response.pages or [])
    avg_conf, min_conf = _page_aggregates(pages)
    return OCRResult(
        markdown="\n\n".join(page.markdown or "" for page in pages),
        words=build_words(pages),
        model=response.model or OCR_MODEL,
        avg_confidence=avg_conf,
        min_confidence=min_conf,
    )
