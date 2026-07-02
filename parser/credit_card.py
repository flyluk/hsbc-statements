"""Parse HSBC HK credit card statement PDFs."""

from __future__ import annotations

import datetime
import re
from collections import defaultdict

import pandas as pd
import pdfplumber
from pdfminer.high_level import extract_text

from .dates import parse_compact_date, parse_statement_date

POST_DATE = re.compile(r"^\d{2}[A-Z]{3}$")
AMOUNT = re.compile(r"^[\d,]+\.\d{2}(?:CR)?$")

FOOTER_MARKERS = (
    "Note:",
    "REWARDCASH",
    "minimum payment",
    "www.hsbc.com.hk",
    "Important information",
    "Please pay by",
    "Overdue / overlimit",
    "Thank you for choosing HSBC",
    "If you are paying by mail",
    "*For credit card",
    "handling fee equivalent",
    "exchange rate applied",
)


def _cluster_rows(words: list[dict], tolerance: float = 4.0) -> dict[float, list[dict]]:
    grouped: dict[float, list[dict]] = defaultdict(list)
    for word in words:
        key = round(word["top"] / tolerance) * tolerance
        grouped[key].append(word)
    return grouped


def _contains_footer(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in FOOTER_MARKERS)


def _statement_meta(pdf_path: str) -> tuple[str, datetime.date, str]:
    text = extract_text(pdf_path) or ""
    account = "Unknown Card"
    match = re.search(r"Account number\s*([\d ]+)", text, re.I)
    if match:
        account = match.group(1).strip()

    card_type = "Credit Card"
    match = re.search(r"Card type\s*(HSBC[^\n]+)", text, re.I)
    if match:
        card_type = match.group(1).strip()

    return f"{card_type} ({account})", parse_statement_date(pdf_path), account


def _parse_amount(text: str) -> tuple[float, str]:
    is_credit = text.endswith("CR")
    clean = text.replace("CR", "").replace(",", "")
    return float(clean), ("Credit" if is_credit else "Debit")


def _parse_page(page, account: str, statement_date: datetime.date) -> list[dict]:
    words = page.extract_words()
    rows = _cluster_rows(words)
    transactions: list[dict] = []
    current: dict | None = None

    for y in sorted(rows):
        row_words = sorted(rows[y], key=lambda w: w["x0"])
        post_tokens = [w for w in row_words if w["x0"] < 95]
        trans_tokens = [w for w in row_words if 95 <= w["x0"] < 135]
        desc_tokens = [w for w in row_words if 135 <= w["x0"] < 500]
        amt_tokens = [w for w in row_words if w["x0"] >= 500]

        post = post_tokens[0]["text"] if post_tokens else None
        trans = trans_tokens[0]["text"] if trans_tokens else None
        description = " ".join(w["text"] for w in desc_tokens).strip()
        amount_text = amt_tokens[-1]["text"] if amt_tokens else None

        if description and _contains_footer(description):
            if current:
                transactions.append(current)
                current = None
            break

        if post and POST_DATE.match(post) and amount_text and AMOUNT.match(amount_text):
            if current:
                transactions.append(current)
            amount, direction = _parse_amount(amount_text)
            post_date = parse_compact_date(post, statement_date).strftime("%Y-%m-%d")
            trans_date = (
                parse_compact_date(trans, statement_date).strftime("%Y-%m-%d")
                if trans and POST_DATE.match(trans)
                else post_date
            )
            current = {
                "Account": account,
                "Post Date": post_date,
                "Transaction Date": trans_date,
                "Transaction Details": description,
                "Amount": amount,
                "Credit/Debit": direction,
                "CCY": "HKD",
            }
            continue

        if current and description and not post:
            if _contains_footer(description):
                transactions.append(current)
                current = None
                break
            current["Transaction Details"] = f"{current['Transaction Details']} {description}".strip()

    if current:
        transactions.append(current)
    return transactions


def parse_credit_card_pdf(pdf_path: str) -> pd.DataFrame:
    account, statement_date, _ = _statement_meta(pdf_path)
    rows: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            rows.extend(_parse_page(page, account, statement_date))

    if not rows:
        raise ValueError("No transactions found in credit card statement")

    df = pd.DataFrame(rows)
    df["Post Date"] = pd.to_datetime(df["Post Date"])
    df["Transaction Date"] = pd.to_datetime(df["Transaction Date"])
    df = df[~df["Transaction Details"].astype(str).str.contains(
        r"\*For credit card|handling fee equivalent|exchange rate applied",
        case=False,
        na=False,
    )]
    return df.reset_index(drop=True)
