"""Shared date parsing for HSBC statements."""

from __future__ import annotations

import datetime
import re

import dateutil.parser
from pdfminer.high_level import extract_text

MONTHS = {
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
}


def parse_statement_date(pdf_path: str) -> datetime.date:
    text = extract_text(pdf_path) or ""
    patterns = (
        r"Statement date\s*(\d{1,2}\s+\w+\s+\d{4})",
        r"Statement date\s*(\d{1,2}\s+[A-Z]{3}\s+\d{4})",
        r"^\s*(\d{1,2}\s+\w+\s+\d{4})\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.M)
        if match:
            return dateutil.parser.parse(match.group(1), dayfirst=True).date()

    return datetime.date.today()


def parse_day_month(token: str, statement_date: datetime.date) -> datetime.date:
    parsed = dateutil.parser.parse(f"{token} {statement_date.year}", dayfirst=True).date()
    if parsed > statement_date:
        parsed = dateutil.parser.parse(f"{token} {statement_date.year - 1}", dayfirst=True).date()
    return parsed


def parse_compact_date(token: str, statement_date: datetime.date) -> datetime.date:
    """Parse HSBC compact dates like 18MAY or 03JAN."""
    match = re.match(r"^(\d{2})([A-Z]{3})$", token.upper())
    if not match:
        raise ValueError(f"Invalid compact date token: {token}")
    day, month = match.groups()
    return parse_day_month(f"{int(day)}-{month.title()}", statement_date)


def is_valid_day_month_parts(parts: list[str]) -> bool:
    if len(parts) == 1:
        return bool(re.match(r"^\d{1,2}-[A-Za-z]{3}$", parts[0]))
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isalpha() and len(parts[1]) == 3:
        return 1 <= int(parts[0]) <= 31 and parts[1].lower() in MONTHS
    return False
