from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np
import pandas as pd
from dateutil import parser as date_parser


_WHITESPACE_RE = re.compile(r"\s+")
_BILL_CLEAN_RE = re.compile(r"[^A-Za-z0-9]+")
_PUNCT_RE = re.compile(r"[^\w\s]")
_LEADING_COMPANY_TERMS_RE = re.compile(r"^(m\/s|ms|m s)\s+", re.IGNORECASE)
_TRAILING_COMPANY_TERMS_RE = re.compile(
    r"\b(pvt|private|ltd|limited|co|company|inc|llp|llc|corp|corporation)\b\.?",
    re.IGNORECASE,
)
_SCIENTIFIC_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?[eE][+-]?\d+$")
_ISO_LIKE_DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T].*)?$")


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def normalize_text(val: Any, case_insensitive: bool = True, trim: bool = True) -> str:
    """Normalize generic text with optional trim/case handling."""
    if _is_missing(val):
        return ""

    text = str(val)
    if trim:
        text = text.strip()
        text = _WHITESPACE_RE.sub(" ", text)
    if case_insensitive:
        text = text.casefold()
    return text


def normalize_bill_number(val: Any) -> str:
    """
    Normalize invoice/bill identifiers so common format variants collapse:
    INV-001, inv001, INV/001 -> INV001
    """
    text = normalize_text(val, case_insensitive=False, trim=True)
    if not text:
        return ""
    text = _BILL_CLEAN_RE.sub("", text.upper())
    # Some sources left-pad bill numbers before an alphanumeric prefix
    # (example: 01AS-0018922 vs 1AS-0018922). Treat only leading padding
    # as formatting noise; keep internal invoice digits unchanged.
    text = text.lstrip("0") or "0"
    return text


def _normalize_excel_serial(serial: float) -> str:
    dt = pd.to_datetime(serial, unit="D", origin="1899-12-30", errors="coerce")
    if pd.isna(dt):
        return ""
    return dt.strftime("%Y-%m-%d")


def normalize_date(val: Any) -> str:
    """
    Normalize date-like values to YYYY-MM-DD.
    Supports strings with common formats and Excel serial dates.
    """
    if _is_missing(val):
        return ""

    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")

    if isinstance(val, np.datetime64):
        parsed = pd.to_datetime(val, errors="coerce")
        return parsed.strftime("%Y-%m-%d") if pd.notna(parsed) else ""

    if isinstance(val, (int, float, np.integer, np.floating)):
        if np.isfinite(val):
            return _normalize_excel_serial(float(val))
        return ""

    text = normalize_text(val, case_insensitive=False, trim=True)
    if not text:
        return ""

    if text.isdigit():
        # Handles Excel serial values represented as strings.
        serial_date = _normalize_excel_serial(float(text))
        if serial_date:
            return serial_date

    # Avoid pandas warning for ISO-like datetime strings when dayfirst=True.
    if _ISO_LIKE_DATE_RE.match(text):
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=False)
    else:
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            parsed = pd.to_datetime(text, errors="coerce", dayfirst=False)
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d")

    # Final fallback for edge formats.
    try:
        parsed_dt = date_parser.parse(text, dayfirst=True, fuzzy=True)
        return parsed_dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _scientific_to_plain(text: str) -> str:
    try:
        decimal_val = Decimal(text)
        plain = format(decimal_val, "f")
        if "." in plain:
            plain = plain.rstrip("0").rstrip(".")
        return plain
    except (InvalidOperation, ValueError):
        return text


def normalize_barcode(val: Any) -> str:
    """
    Normalize barcode-like values, preserving digits while fixing scientific notation.
    Example: 1.23E+11 -> 123000000000
    """
    if _is_missing(val):
        return ""

    if isinstance(val, (int, np.integer)):
        return str(int(val))

    if isinstance(val, (float, np.floating)):
        if not np.isfinite(val):
            return ""
        if float(val).is_integer():
            return str(int(val))
        text_float = format(Decimal(str(val)), "f")
        return text_float.rstrip("0").rstrip(".")

    text = normalize_text(val, case_insensitive=False, trim=True)
    if not text:
        return ""

    # Drop common wrappers that come from CSV/Excel exports.
    text = text.strip("\"'`")
    text = text.replace(",", "")
    if _SCIENTIFIC_RE.match(text):
        text = _scientific_to_plain(text)

    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    elif re.fullmatch(r"\d+\.\d+", text):
        # Excel/CSV may still surface barcode-like integers with decimal noise.
        try:
            dec = Decimal(text)
            if dec == dec.to_integral_value():
                text = str(dec.to_integral_value())
        except Exception:
            pass

    # Keep alphanumeric identifiers but remove separators.
    cleaned = re.sub(r"[^A-Za-z0-9]", "", text)
    return cleaned.upper()


def normalize_identifier(val: Any) -> str:
    """
    Normalize party/customer identifiers by removing legal suffixes,
    punctuation, and noisy spacing.
    Example: M/S Sharma Traders Pvt. Ltd. -> sharma traders
    """
    text = normalize_text(val, case_insensitive=True, trim=True)
    if not text:
        return ""

    text = _LEADING_COMPANY_TERMS_RE.sub("", text)
    text = _TRAILING_COMPANY_TERMS_RE.sub(" ", text)
    text = _PUNCT_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text
