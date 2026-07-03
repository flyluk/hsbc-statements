"""Parse Citi Citigold consolidated eStatement PDFs (bank accounts)."""

from __future__ import annotations

import re

import pandas as pd
import pdfplumber

from .common import (
    AMOUNT,
    DATE_MM_DD_YY,
    cluster_rows,
    parse_mm_dd_yy,
    should_skip_line,
)

ACCOUNT_LABELS = {
    "支票戶口": "Citi Cheque Account",
    "bankatwork儲蓄戶口": "Citi Bank At Work Savings",
    "月結單儲蓄戶口": "Citi Statement Savings",
    "通知存款": "Citi Notice Deposit",
    "證券戶口": "Citi Securities Account",
}

TRANSACTION_STARTERS = (
    "自動轉賬",
    "支付貸款",
    "存入本地匯款",
    "存入利息",
    "流動銀行繳賬",
    "承上結餘",
)


def _format_account(label: str, number: str | None, currency: str | None) -> str:
    key = label.replace(" ", "").lower()
    base = ACCOUNT_LABELS.get(key, label.strip())
    if not number:
        return base
    ccy = currency or "HKD"
    return f"{base} ({number} {ccy})"


def _account_header(line: str) -> tuple[str, str | None, str | None] | None:
    normalized = line.replace(" ", "").lower()
    for key, label in ACCOUNT_LABELS.items():
        if key in normalized:
            number_match = re.search(r"\b(\d{6,12})\b", line)
            currency = "USD" if "美元" in line else "HKD"
            return label, number_match.group(1) if number_match else None, currency
    return None


def _amount_tokens(row_words: list[dict]) -> list[tuple[float, str]]:
    return [(w["x0"], w["text"]) for w in row_words if AMOUNT.match(w["text"])]


def _inline_description(row_words: list[dict]) -> str:
    desc_tokens = [w for w in sorted(row_words, key=lambda w: w["x0"]) if 140 <= w["x0"] < 340]
    return " ".join(w["text"] for w in desc_tokens).strip()


def _is_date_row(row_words: list[dict]) -> bool:
    return any(w["x0"] < 75 and DATE_MM_DD_YY.match(w["text"]) for w in row_words)


def _is_transaction_starter(description: str) -> bool:
    return any(description.startswith(starter) for starter in TRANSACTION_STARTERS)


def _flush_suffix(transactions: list[dict], pending_suffix: list[str]) -> None:
    if not pending_suffix or not transactions:
        return
    extra = " ".join(pending_suffix).strip()
    if extra and transactions[-1]["Transaction Details"] != "承上結餘":
        transactions[-1]["Transaction Details"] = (
            f"{transactions[-1]['Transaction Details']} {extra}".strip()
        )


def _parse_transaction_row(
    row_words: list[dict],
    account: str,
    currency: str,
    description: str,
) -> dict | None:
    sorted_words = sorted(row_words, key=lambda w: w["x0"])
    post_tokens = [w for w in sorted_words if w["x0"] < 75]
    trans_tokens = [w for w in sorted_words if 75 <= w["x0"] < 140]
    amount_tokens = _amount_tokens(sorted_words)

    post = post_tokens[0]["text"] if post_tokens else None
    if not post or not DATE_MM_DD_YY.match(post):
        return None

    description = description.strip()
    if description == "戶口結餘":
        return None

    trans_date = trans_tokens[0]["text"] if trans_tokens else post
    date_value = parse_mm_dd_yy(trans_date if DATE_MM_DD_YY.match(trans_date) else post)

    deposit = pd.NA
    withdrawal = pd.NA
    balance = pd.NA

    for x0, text in amount_tokens:
        value = float(text.replace(",", ""))
        if x0 >= 500:
            balance = value
        elif x0 >= 410:
            deposit = value
        elif x0 >= 330:
            withdrawal = value

    if description == "承上結餘" and pd.notna(balance):
        return {
            "Account": account,
            "Date": date_value,
            "Transaction Details": description,
            "Deposit": pd.NA,
            "Withdrawal": pd.NA,
            "Balance": balance,
            "CCY": currency,
        }

    if pd.isna(deposit) and pd.isna(withdrawal):
        return None

    if not description:
        description = "Transaction"

    return {
        "Account": account,
        "Date": date_value,
        "Transaction Details": description,
        "Deposit": deposit,
        "Withdrawal": withdrawal,
        "Balance": balance,
        "CCY": currency,
    }


def _parse_page(page) -> list[dict]:
    words = page.extract_words()
    rows = cluster_rows(words)
    transactions: list[dict] = []
    current_account: str | None = None
    current_currency = "HKD"
    pending_account_number: str | None = None
    pending_prefix: list[str] = []
    pending_suffix: list[str] = []
    ordered_rows = sorted(rows.items())

    for _, row_words in ordered_rows:
        sorted_words = sorted(row_words, key=lambda w: w["x0"])
        line = " ".join(w["text"] for w in sorted_words)

        lone_number = (
            len(sorted_words) == 1
            and sorted_words[0]["text"].isdigit()
            and 6 <= len(sorted_words[0]["text"]) <= 12
            and sorted_words[0]["x0"] < 150
        )
        if lone_number:
            pending_account_number = sorted_words[0]["text"]
            continue

        header = _account_header(line)
        if header:
            label, number, currency = header
            if label == "Citi Statement Savings" and pending_account_number and not number:
                number = pending_account_number
            current_account = _format_account(label, number, currency)
            current_currency = currency or "HKD"
            pending_account_number = None
            pending_prefix = []
            pending_suffix = []
            continue

        if not current_account:
            continue

        if _is_date_row(sorted_words):
            _flush_suffix(transactions, pending_suffix)
            pending_suffix = []

            inline = _inline_description(row_words)
            parts = pending_prefix + ([inline] if inline else [])
            description = " ".join(parts).strip()
            pending_prefix = []

            txn = _parse_transaction_row(row_words, current_account, current_currency, description)
            if txn:
                transactions.append(txn)
            continue

        desc_tokens = [w for w in sorted_words if w["x0"] >= 140]
        description = " ".join(w["text"] for w in desc_tokens).strip()
        if not description or should_skip_line(description):
            continue

        if _is_transaction_starter(description):
            _flush_suffix(transactions, pending_suffix)
            pending_suffix = []
            pending_prefix.append(description)
        else:
            pending_suffix.append(description)

    _flush_suffix(transactions, pending_suffix)

    return transactions


def parse_estatement_pdf(pdf_path: str) -> pd.DataFrame:
    rows: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            rows.extend(_parse_page(page))

    if not rows:
        raise ValueError("No transactions found in Citi eStatement")

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.reset_index(drop=True)
