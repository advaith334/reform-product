"""Pydantic schema for the fields we pull out of each trade document.

These models are handed to Mistral as the document-annotation response format, so
every ``description`` below is effectively part of the extraction prompt. Vague
wording here is the most common cause of bad extraction -- change it carefully.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

# Strips currency symbols, thousands separators and unit suffixes so values like
# "3,515.55 USD" or "1.00 ea" survive as Decimals.
_NUMERIC_NOISE = re.compile(r"[^0-9.\-]")


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Coerce a loosely formatted numeric string to Decimal, or None if unusable."""
    if value is None or isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if not isinstance(value, str):
        return None

    cleaned = _NUMERIC_NOISE.sub("", value.strip())
    # A stray trailing/leading separator, or nothing left at all, means no number.
    cleaned = cleaned.strip(".-")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


class LineItem(BaseModel):
    """A single goods line from the document's commodity or line-item table."""

    quantity: Optional[float] = Field(
        default=None,
        description=(
            "Number of units shipped for this line, as a plain number. "
            "Drop any unit suffix such as 'ea', 'PCS' or 'pallets'."
        ),
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the goods on this line, exactly as printed.",
    )
    value: Optional[float] = Field(
        default=None,
        description=(
            "The extended line total for this line -- quantity multiplied by unit "
            "price. This is the 'Extended price', 'Amount' or 'Total' column, NOT "
            "the unit price. If only a unit price is shown, multiply it by the quantity."
        ),
    )
    hts_code: Optional[str] = Field(
        default=None,
        description=(
            "Harmonized Tariff Schedule code for this line (also labelled HTS, HTSUS, "
            "HS code or tariff number). Keep every digit including leading zeros and "
            "return it as a string. Null if the document shows no tariff code."
        ),
    )

    @field_validator("quantity", "value", mode="before")
    @classmethod
    def _coerce_numeric(cls, v: Any) -> Any:
        d = _to_decimal(v)
        return None if d is None else float(d)


class ShipmentDocument(BaseModel):
    """Fields common to bills of lading and commercial invoices.

    A given document will only carry some of these -- a bill of lading has no
    invoice number or HTS codes, an invoice has no B/L number. Return null rather
    than guessing.
    """

    bill_of_lading_number: Optional[str] = Field(
        default=None,
        description=(
            "The bill of lading number, often labelled 'B/L number', 'BOL', "
            "'HBL' or 'MBL'. Null if this document is not a bill of lading."
        ),
    )
    invoice_number: Optional[str] = Field(
        default=None,
        description=(
            "The commercial invoice number, labelled 'Invoice number' or 'Invoice no.'. "
            "Null if the document carries no invoice number."
        ),
    )
    shipper_name: Optional[str] = Field(
        default=None,
        description=(
            "Name of the shipper, exporter or seller sending the goods -- the company "
            "name only, without its address."
        ),
    )
    shipper_address: Optional[str] = Field(
        default=None,
        description=(
            "Full postal address of the shipper/exporter, including street, city, "
            "state, postal code and country. Join multiple lines with ', '. "
            "Do not repeat the company name."
        ),
    )
    consignee_name: Optional[str] = Field(
        default=None,
        description=(
            "Name of the consignee -- the party the goods are consigned to, labelled "
            "'Consignee' or 'Consigned to'. Company name only, without its address."
        ),
    )
    consignee_address: Optional[str] = Field(
        default=None,
        description=(
            "Full postal address of the consignee, including street, city, state, "
            "postal code and country. Join multiple lines with ', '. "
            "Do not repeat the company name."
        ),
    )
    line_items: list[LineItem] = Field(
        default_factory=list,
        description=(
            "Every goods line from the document's commodity or line-item table, in "
            "the order printed. Empty list if the document has no itemised table."
        ),
    )
    total_value_of_goods: Optional[float] = Field(
        default=None,
        description=(
            "The grand total value of the goods for the whole document -- the "
            "'Invoice total', 'Grand total' or 'Total' figure. A plain number with "
            "no currency symbol or thousands separators."
        ),
    )

    @field_validator("total_value_of_goods", mode="before")
    @classmethod
    def _coerce_total(cls, v: Any) -> Any:
        d = _to_decimal(v)
        return None if d is None else float(d)


#: Document-level fields that get a confidence score. Order drives report output.
DOCUMENT_FIELDS = (
    "bill_of_lading_number",
    "invoice_number",
    "shipper_name",
    "shipper_address",
    "consignee_name",
    "consignee_address",
    "total_value_of_goods",
)

#: Line-item fields that get a confidence score.
LINE_ITEM_FIELDS = ("quantity", "description", "value", "hts_code")

#: Fields whose printed form differs from the extracted form (commas, currency),
#: so the confidence matcher should compare them numerically.
NUMERIC_FIELDS = frozenset({"quantity", "value", "total_value_of_goods"})
