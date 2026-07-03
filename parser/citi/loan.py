"""Parse Citi Hong Kong loan / mortgage statement PDFs."""

from __future__ import annotations

import datetime
import re

import pandas as pd
import pdfplumber
from pdfminer.high_level import extract_text

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _loan_account_name(pdf_path: str) -> str:
    text = extract_text(pdf_path) or ""
    number = "Unknown"
    match = re.search(r"Number\s*:\s*([\d-]+)", text, re.I)
    if match:
        number = match.group(1).strip()
    return f"Citi Mortgage ({number})"


def _split_cell_lines(table: list[list[str | None]]) -> list[list[str]]:
    if len(table) < 2:
        return []

    headers = [cell or "" for cell in table[0]]
    data_row = table[1]
    columns = [str(cell or "").split("\n") for cell in data_row]
    max_len = max(len(col) for col in columns)
    rows: list[list[str]] = []

    for idx in range(max_len):
        row = []
        for col_idx, col_lines in enumerate(columns):
            value = col_lines[idx].strip() if idx < len(col_lines) else ""
            row.append(value)
        if any(row):
            rows.append(row)

    return rows


def parse_loan_pdf(pdf_path: str) -> pd.DataFrame:
    account = _loan_account_name(pdf_path)
    transactions: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table or len(table) < 2:
                    continue
                header = " ".join(str(cell or "") for cell in table[0])
                if "Date" not in header or "Loan Balance" not in header:
                    continue

                for row in _split_cell_lines(table):
                    date_token = row[0] if row else ""
                    if not DATE_RE.match(date_token):
                        continue

                    amount = float(row[2].replace(",", "")) if row[2] else 0.0
                    interest = float(row[5].replace(",", "")) if len(row) > 5 and row[5] else 0.0
                    principal = float(row[6].replace(",", "")) if len(row) > 6 and row[6] else 0.0
                    balance_raw = row[7].replace(",", "") if len(row) > 7 and row[7] else ""
                    balance = float(balance_raw) if balance_raw else pd.NA
                    ref = row[1] if len(row) > 1 else ""

                    transactions.append(
                        {
                            "Account": account,
                            "Date": datetime.datetime.strptime(date_token, "%m/%d/%Y").date(),
                            "Transaction Details": f"Mortgage payment (ref {ref}, principal {principal:,.2f}, interest {interest:,.2f})",
                            "Deposit": pd.NA,
                            "Withdrawal": amount,
                            "Balance": balance,
                            "CCY": "HKD",
                        }
                    )

    if not transactions:
        raise ValueError("No transactions found in Citi loan statement")

    df = pd.DataFrame(transactions)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.reset_index(drop=True)
