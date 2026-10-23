"""Canonical transaction normalization for validated import rows."""

import math
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd


MAX_AMOUNT_DIGITS = 24
MAX_AMOUNT_DECIMAL_PLACES = 6


def text_value(value: Any) -> str:
    """Return a stable string value while preserving empty source cells."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def parse_decimal_amount(value: Any) -> Decimal:
    """Parse a finite monetary value without using binary floating point."""
    raw_value = text_value(value).replace(",", "")
    if not raw_value:
        raise ValueError("Amount is empty.")
    try:
        amount = Decimal(raw_value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Amount '{text_value(value)}' is not a valid decimal.") from exc

    if not amount.is_finite():
        raise ValueError(f"Amount '{text_value(value)}' must be finite.")

    digits = len(amount.as_tuple().digits)
    decimal_places = max(0, -amount.as_tuple().exponent)
    if digits > MAX_AMOUNT_DIGITS or decimal_places > MAX_AMOUNT_DECIMAL_PLACES:
        raise ValueError(
            "Amount exceeds the supported precision "
            f"({MAX_AMOUNT_DIGITS} digits, {MAX_AMOUNT_DECIMAL_PLACES} decimal places)."
        )
    return amount


def parse_transaction_date(value: Any) -> date:
    """Parse a source date into the canonical date representation."""
    raw_value = text_value(value)
    if not raw_value:
        raise ValueError("Transaction date is empty.")
    try:
        return pd.to_datetime(raw_value, format="mixed", dayfirst=False).date()
    except (TypeError, ValueError, pd.errors.ParserError) as exc:
        raise ValueError(f"Date '{raw_value}' cannot be parsed.") from exc


def normalize_reference(value: Any) -> str:
    """Normalize references for deterministic comparison without altering raw data."""
    return re.sub(r"[^a-z0-9]+", "", text_value(value).lower())


def normalize_counterparty(value: Any) -> str:
    """Normalize counterparty formatting while retaining word boundaries."""
    normalized = re.sub(r"[^a-z0-9]+", " ", text_value(value).lower())
    return " ".join(normalized.split())


@dataclass(frozen=True)
class NormalizedTransaction:
    """In-memory canonical form used before persistence."""

    external_id: str
    transaction_date: date
    amount: Decimal
    currency: str
    reference: str
    normalized_reference: str
    description: str
    counterparty: str
    normalized_counterparty: str
    raw_data: dict[str, str]


def normalize_row(row: Any) -> NormalizedTransaction:
    """Convert one already-validated source row to canonical values."""
    raw_data = {str(column): text_value(value) for column, value in row.items()}
    reference = text_value(row.get("reference", ""))
    counterparty = text_value(row.get("counterparty", ""))

    return NormalizedTransaction(
        external_id=text_value(row.get("external_id", "")),
        transaction_date=parse_transaction_date(row.get("transaction_date", "")),
        amount=parse_decimal_amount(row.get("amount", "")),
        currency=text_value(row.get("currency", "")).upper(),
        reference=reference,
        normalized_reference=normalize_reference(reference),
        description=text_value(row.get("description", "")),
        counterparty=counterparty,
        normalized_counterparty=normalize_counterparty(counterparty),
        raw_data=raw_data,
    )
