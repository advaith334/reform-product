"""Derive a per-field confidence score from Mistral's word-level OCR scores.

Mistral does not return a confidence for each annotated field -- ``confidence_scores``
are OCR-level, one entry per word read off the page. So we work backwards: find where
each extracted value appears in the OCR word stream, then aggregate the confidences of
the words that back it.

What this measures is how legibly the source text was read, NOT whether the extractor
mapped that text to the right field. ``match_method`` keeps those apart:

``exact``      the value was found verbatim as a contiguous run of words.
``fuzzy``      found as a contiguous run, with minor differences in spacing or spelling.
``token``      the value is composed from scattered parts of the page (an address
               joined across lines, a part number in a different table cell from its
               description), so each token was located and scored on its own.
``unmatched``  the value never appeared on the page in any recognisable form -- a
               figure the model derived, or a genuine extraction error. Confidence is
               null, because there is no OCR reading to stand behind it.
``absent``     the field is not on this document at all, so there was nothing to score.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any, Optional, Sequence

#: Below this similarity a fuzzy window is not considered a match at all.
FUZZY_THRESHOLD = 0.80

#: How much longer or shorter than the value the OCR window may be, in tokens.
#: Covers the annotator joining or splitting tokens relative to the page.
WINDOW_SLACK = 2

#: Per-token similarity required before a token counts as found on the page.
TOKEN_THRESHOLD = 0.85

#: Fraction of a value's tokens that must be found for the token-level fallback
#: to produce a score rather than give up.
TOKEN_COVERAGE_THRESHOLD = 0.60

_PUNCT = re.compile(r"[^\w]+", re.UNICODE)
_NUMERIC_NOISE = re.compile(r"[^0-9.\-]")


@dataclass(frozen=True)
class OCRWord:
    """One scored word from the OCR output, with its normalised comparison form."""

    text: str
    confidence: float
    norm: str


@dataclass(frozen=True)
class FieldConfidence:
    """The confidence verdict for a single extracted field."""

    field_name: str
    field_value: Optional[str]
    min_confidence: Optional[float]
    mean_confidence: Optional[float]
    match_method: str  # exact | fuzzy | token | unmatched | absent
    match_ratio: Optional[float]


def _normalize(text: str) -> str:
    """Casefold and drop punctuation/accents so page text and extracted text compare."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _PUNCT.sub("", stripped).casefold()


def _as_decimal(text: str) -> Optional[Decimal]:
    cleaned = _NUMERIC_NOISE.sub("", text).strip(".-")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def build_words(pages: Sequence[Any]) -> list[OCRWord]:
    """Flatten per-page word confidence scores into one ordered list.

    ``pages`` are OCRPageObjects. Pages whose scores are absent (the granularity was
    not 'word', or the page had no text) simply contribute nothing.
    """
    words: list[OCRWord] = []
    for page in pages:
        scores = getattr(page, "confidence_scores", None)
        for word in (getattr(scores, "word_confidence_scores", None) or []):
            norm = _normalize(word.text)
            if norm:
                words.append(OCRWord(text=word.text, confidence=float(word.confidence), norm=norm))
    return words


def _aggregate(window: Sequence[OCRWord]) -> tuple[float, float]:
    confidences = [w.confidence for w in window]
    return min(confidences), sum(confidences) / len(confidences)


def _match_numeric(words: Sequence[OCRWord], value: Decimal) -> Optional[tuple[int, int]]:
    """Locate a number on the page by value, so 1496.0 still finds '1,496.00'.

    Tries single words first, then adjacent pairs -- OCR sometimes splits a figure
    across the decimal point or a thousands separator.
    """
    for i, word in enumerate(words):
        if _as_decimal(word.text) == value:
            return i, i + 1
    for i in range(len(words) - 1):
        joined = words[i].text + words[i + 1].text
        if _as_decimal(joined) == value:
            return i, i + 2
    return None


def _match_text(words: Sequence[OCRWord], value: str) -> tuple[Optional[tuple[int, int]], float]:
    """Slide a token window over the page looking for the best match for ``value``."""
    target_tokens = [t for t in (_normalize(tok) for tok in value.split()) if t]
    if not target_tokens:
        return None, 0.0
    target = "".join(target_tokens)
    n = len(target_tokens)

    matcher = SequenceMatcher(autojunk=False)
    matcher.set_seq2(target)

    best: Optional[tuple[int, int]] = None
    best_ratio = 0.0

    sizes = {max(1, n + delta) for delta in range(-WINDOW_SLACK, WINDOW_SLACK + 1)}
    for size in sorted(sizes):
        for start in range(0, len(words) - size + 1):
            window = words[start : start + size]
            candidate = "".join(w.norm for w in window)
            matcher.set_seq1(candidate)
            # Cheap upper bounds first -- most windows are nowhere close.
            if matcher.real_quick_ratio() < best_ratio or matcher.quick_ratio() < best_ratio:
                continue
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio, best = ratio, (start, start + size)
                if ratio == 1.0:
                    return best, 1.0
    return best, best_ratio


def _match_tokens(
    words: Sequence[OCRWord], value: str
) -> tuple[Optional[list[float]], float]:
    """Score a value whose text is scattered across the page rather than contiguous.

    Extracted values are often composed: an address joined from separate lines with
    ", ", or a description whose part number sits in a different table row from its
    text. No contiguous window can match those, but every piece was still read, and
    its confidence is still the honest signal. So fall back to locating each token
    on its own and aggregating what we find.
    """
    tokens = [t for t in (_normalize(tok) for tok in value.split()) if t]
    if not tokens:
        return None, 0.0

    by_norm: dict[str, float] = {}
    for word in words:
        # Keep the worst reading of a repeated word -- the conservative choice.
        if word.norm not in by_norm or word.confidence < by_norm[word.norm]:
            by_norm[word.norm] = word.confidence

    matcher = SequenceMatcher(autojunk=False)
    found: list[float] = []
    for token in tokens:
        hit = by_norm.get(token)
        if hit is None:
            matcher.set_seq2(token)
            best_ratio, best_conf = TOKEN_THRESHOLD, None
            for norm, confidence in by_norm.items():
                matcher.set_seq1(norm)
                if matcher.real_quick_ratio() < best_ratio:
                    continue
                ratio = matcher.ratio()
                if ratio >= best_ratio:
                    best_ratio, best_conf = ratio, confidence
            hit = best_conf
        if hit is not None:
            found.append(hit)

    coverage = len(found) / len(tokens)
    if coverage < TOKEN_COVERAGE_THRESHOLD:
        return None, coverage
    return found, coverage


def score_field(
    words: Sequence[OCRWord],
    field_name: str,
    value: Any,
    *,
    numeric: bool = False,
) -> FieldConfidence:
    """Score one extracted field against the OCR word stream."""
    # The field simply is not on this document (a bill of lading has no invoice
    # number). That is a different fact from a value we failed to locate, so it gets
    # its own method rather than being lumped in with 'unmatched'.
    if value is None or (isinstance(value, str) and not value.strip()):
        return FieldConfidence(field_name, None, None, None, "absent", None)

    rendered = str(value)

    span: Optional[tuple[int, int]] = None
    ratio = 0.0
    method = "unmatched"

    if numeric:
        target = _as_decimal(rendered)
        if target is not None:
            span = _match_numeric(words, target)
            if span is not None:
                ratio, method = 1.0, "exact"

    if span is None:
        span, ratio = _match_text(words, rendered)
        if span is not None and ratio >= FUZZY_THRESHOLD:
            method = "exact" if ratio == 1.0 else "fuzzy"
        else:
            span = None

    if span is not None:
        minimum, mean = _aggregate(words[span[0] : span[1]])
        return FieldConfidence(field_name, rendered, minimum, mean, method, ratio)

    # Contiguous matching failed -- the value is probably composed from scattered
    # parts of the page. Score the pieces individually.
    confidences, coverage = _match_tokens(words, rendered)
    if confidences:
        return FieldConfidence(
            field_name,
            rendered,
            min(confidences),
            sum(confidences) / len(confidences),
            "token",
            coverage,
        )

    return FieldConfidence(field_name, rendered, None, None, "unmatched", None)
