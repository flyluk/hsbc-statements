"""Parse Citi Hong Kong credit card statement PDFs."""

from __future__ import annotations

import re

import pandas as pd
import pdfplumber

from .common import (
    AMOUNT,
    cluster_rows,
    parse_amount,
    parse_citi_spaced_date,
    parse_statement_period_end,
    should_skip_line,
)

CARD_HEADER = re.compile(
    r"^(OCTOPUS\s+CITIBANK|CITI\s+CLEAR|CITIBANK).*(CARD|PLATINUM)",
    re.I,
)
SKIP_DESCRIPTIONS = {
    "BALANCE FORWARD",
    "STATEMENT BALANCE",
    "REBATE CREDIT",
}


def _card_name_from_context(ordered_rows: list[tuple[float, list[dict]]], header_idx: int) -> str | None:
    header_words = ordered_rows[header_idx][1]
    line = " ".join(w["text"] for w in sorted(header_words, key=lambda w: w["x0"]))
    if not CARD_HEADER.search(line):
        return None

    for _, number_words in ordered_rows[header_idx + 1 : header_idx + 4]:
        digits = [w["text"] for w in sorted(number_words, key=lambda w: w["x0"]) if re.fullmatch(r"\d{4}", w["text"])]
        if len(digits) >= 4:
            masked = "-".join(digits[:4])
            return f"{line.strip()} ({masked})"

    return re.sub(r"\s+", " ", line).strip()


def _parse_date_row(row_words: list[dict], statement_date) -> str | None:
    date_tokens = [w for w in sorted(row_words, key=lambda w: w["x0"]) if w["x0"] < 120]
    if len(date_tokens) < 3:
        return None
    token = " ".join(w["text"] for w in date_tokens[:3])
    try:
        return parse_citi_spaced_date(token, statement_date).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _parse_page(page, account: str | None, statement_date) -> tuple[list[dict], str | None]:
    words = page.extract_words()
    rows = cluster_rows(words)
    transactions: list[dict] = []
    current_account = account
    current: dict | None = None
    ordered = sorted(rows.items())

    for idx, (y, row_words) in enumerate(ordered):
        card = _card_name_from_context(ordered, idx)
        if card:
            current_account = card
            if current:
                transactions.append(current)
                current = None
            continue

        if not current_account:
            continue

        sorted_words = sorted(row_words, key=lambda w: w["x0"])
        date_value = _parse_date_row(row_words, statement_date)
        desc_tokens = [w for w in sorted_words if 150 <= w["x0"] < 500]
        amt_tokens = [w for w in sorted_words if w["x0"] >= 500 and AMOUNT.match(w["text"])]
        description = " ".join(w["text"] for w in desc_tokens).strip()

        if date_value and amt_tokens and description:
            if current:
                transactions.append(current)
            amount, direction = parse_amount(amt_tokens[-1]["text"])
            if description.upper() in SKIP_DESCRIPTIONS and direction == "Debit":
                current = None
                continue
            current = {
                "Account": current_account,
                "Date": date_value,
                "Transaction Details": description,
                "Amount": amount,
                "Credit/Debit": direction,
                "CCY": "HKD",
            }
            continue

        if current and description and not date_value:
            if should_skip_line(description):
                transactions.append(current)
                current = None
                continue
            current["Transaction Details"] = f"{current['Transaction Details']} {description}".strip()

    if current:
        transactions.append(current)

    return transactions, current_account


def parse_credit_card_pdf(pdf_path: str) -> pd.DataFrame:
    statement_date = parse_statement_period_end(pdf_path)
    rows: list[dict] = []
    account: str | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_rows, account = _parse_page(page, account, statement_date)
            rows.extend(page_rows)

    if not rows:
        raise ValueError("No transactions found in Citi credit card statement")

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df[~df["Transaction Details"].astype(str).str.upper().isin(SKIP_DESCRIPTIONS)]
    return df.reset_index(drop=True)
