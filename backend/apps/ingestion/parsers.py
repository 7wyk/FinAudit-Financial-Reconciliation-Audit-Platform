"""
File parsing services — CSV and XLSX to DataFrames with validation.

Designed to be independent of Django views for testability.
"""

import io
import logging
from typing import Optional

import pandas as pd

from .normalization import parse_decimal_amount, parse_transaction_date, text_value

logger = logging.getLogger(__name__)

# Maximum rows to process per file
MAX_ROWS = 100_000


class RowLimitExceeded(ValueError):
    """Raised when a source file has more rows than the supported limit."""

    def __init__(self, max_rows: int = MAX_ROWS):
        super().__init__(
            f"File exceeds the maximum supported row limit of {max_rows:,} rows."
        )

# Required columns for a valid import (case-insensitive matching)
REQUIRED_COLUMNS = {
    "transaction_date",
    "amount",
}

# Optional but recognized columns
RECOGNIZED_COLUMNS = {
    "external_id",
    "transaction_date",
    "amount",
    "currency",
    "reference",
    "description",
    "counterparty",
    "source",
    "type",
    "category",
    "account",
}


def _normalize_column_name(col: str) -> str:
    """Normalize column name to snake_case lowercase."""
    return (
        col.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "_")
    )


def parse_csv(file_content: bytes, encoding: str = "utf-8") -> pd.DataFrame:
    """Parse CSV file content into a DataFrame."""
    try:
        df = pd.read_csv(
            io.BytesIO(file_content),
            encoding=encoding,
            dtype=str,  # Keep everything as strings initially
            keep_default_na=False,
            nrows=MAX_ROWS + 1,
        )
    except UnicodeDecodeError:
        # Fallback to latin-1
        df = pd.read_csv(
            io.BytesIO(file_content),
            encoding="latin-1",
            dtype=str,
            keep_default_na=False,
            nrows=MAX_ROWS + 1,
        )

    if len(df) > MAX_ROWS:
        raise RowLimitExceeded()
    df.columns = [_normalize_column_name(c) for c in df.columns]
    return df


def parse_xlsx(file_content: bytes, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """Parse XLSX file content into a DataFrame."""
    sheet = sheet_name or 0
    df = pd.read_excel(
        io.BytesIO(file_content),
        sheet_name=sheet,
        dtype=str,
        keep_default_na=False,
        nrows=MAX_ROWS + 1,
        engine="openpyxl",
    )
    if len(df) > MAX_ROWS:
        raise RowLimitExceeded()
    df.columns = [_normalize_column_name(c) for c in df.columns]
    return df


def parse_file(file_content: bytes, file_type: str) -> pd.DataFrame:
    """Dispatch to the correct parser based on file type."""
    parsers = {
        "csv": parse_csv,
        "xlsx": parse_xlsx,
    }
    parser = parsers.get(file_type.lower())
    if not parser:
        raise ValueError(f"Unsupported file type: {file_type}")
    return parser(file_content)


def validate_dataframe(df: pd.DataFrame) -> list[dict]:
    """
    Validate a parsed DataFrame structure.
    Returns a list of error dicts: [{"row": ..., "field": ..., "error": ...}]
    """
    errors = []

    if df.empty:
        errors.append({
            "row": 0,
            "field": "",
            "type": "structure",
            "error": "File contains no data rows.",
        })
        return errors

    # Check required columns
    df_columns = set(df.columns)
    missing = REQUIRED_COLUMNS - df_columns
    if missing:
        errors.append({
            "row": 0,
            "field": ", ".join(sorted(missing)),
            "type": "structure",
            "error": f"Missing required columns: {', '.join(sorted(missing))}",
        })
        return errors  # Can't validate rows without required columns

    # Row-level validation
    for idx, row in df.iterrows():
        row_num = idx + 2  # +2 for header row + 0-based index

        # Amount must be numeric
        amount = text_value(row.get("amount", ""))
        try:
            parse_decimal_amount(amount)
        except ValueError as exc:
            errors.append({
                "row": row_num,
                "field": "amount",
                "type": "validation",
                "error": str(exc),
                "raw_value": amount,
            })

        # Transaction date must be parseable
        date_val = text_value(row.get("transaction_date", ""))
        try:
            parse_transaction_date(date_val)
        except ValueError as exc:
            errors.append({
                "row": row_num,
                "field": "transaction_date",
                "type": "validation",
                "error": str(exc),
                "raw_value": date_val,
            })

    return errors
