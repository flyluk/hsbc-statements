"""Shared helpers for Citi statement parsers."""

from __future__ import annotations

import datetime
import re
from collections import defaultdict

import dateutil.parser
from pdfminer.high_level import extract_text

DATE_MM_DD_YY = re.compile(r"^\d{2}/\d{2}/\d{2}$")
AMOUNT = re.compile(r"^[\d,]+\.\d{2}(?:CR)?$")
CITI_SPACED_DATE = re.compile(r"^([A-Z]{3})\s+(\d{1,2})\s+(\d{2})$", re.I)

SKIP_MARKERS = (
    "提存記錄",
    "總結",
    "戶口結餘",
    "現時儲蓄年利率",
    "HKN2ESA",
    "閣下戶口之交易記錄",
    "Page ",
    "Contactless Payments",
    "APPLICABLE FINANCE CHARGE",
    "MAIN CARD",
    "CARD NUMBER",
    "CREDIT LIMIT",
)


def cluster_rows(words: list[dict], tolerance: float = 3.0) -> dict[float, list[dict]]:
    rows: dict[float, list[dict]] = defaultdict(list)
    for word in words:
        key = round(word["top"] / tolerance) * tolerance
        rows[key].append(word)
    return rows


def parse_amount(text: str) -> tuple[float, str]:
    is_credit = text.upper().endswith("CR")
    clean = text.upper().replace("CR", "").replace(",", "")
    return float(clean), ("Credit" if is_credit else "Debit")


def parse_statement_period_end(pdf_path: str) -> datetime.date:
    text = extract_text(pdf_path) or ""
    match = re.search(r"月結單日期（月/日/年）\s*(\d{2}/\d{2}/\d{2})\s*-\s*(\d{2}/\d{2}/\d{2})", text)
    if match:
        return datetime.datetime.strptime(match.group(2), "%m/%d/%y").date()

    match = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", text)
    if match:
        return dateutil.parser.parse(match.group(0), dayfirst=False).date()

    match = re.search(r"Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.I)
    if match:
        return dateutil.parser.parse(match.group(1), dayfirst=False).date()

    return datetime.date.today()


def parse_citi_spaced_date(token: str, statement_date: datetime.date) -> datetime.date:
    match = CITI_SPACED_DATE.match(token.strip())
    if not match:
        raise ValueError(f"Invalid Citi date token: {token}")
    month, day, year_suffix = match.groups()
    year = 2000 + int(year_suffix)
    parsed = dateutil.parser.parse(f"{int(day)}-{month.title()}-{year}", dayfirst=True).date()
    if parsed > statement_date:
        parsed = parsed.replace(year=year - 1)
    return parsed


def parse_mm_dd_yy(token: str) -> datetime.date:
    return datetime.datetime.strptime(token, "%m/%d/%y").date()


def should_skip_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return any(marker in stripped for marker in SKIP_MARKERS)
