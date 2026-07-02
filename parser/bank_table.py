"""Parse HSBC bank account PDF tables (activities + eStatement history)."""

from __future__ import annotations

import datetime
import re
from collections import defaultdict

import pandas as pd
import pdfplumber

from .accounts import normalize_account_name
from .dates import is_valid_day_month_parts, parse_day_month, parse_statement_date

DATE_TOKEN = re.compile(r"^\d{1,2}-[A-Za-z]{3}$")
AMOUNT = re.compile(r"^[\d,]+\.\d{2}$")
CCY_RE = re.compile(r"^[A-Z]{3}$")

FOOTER_MARKERS = (
    "Important Notice",
    "fraudulent telephone",
    "Security and Fraud",
    "have any queries",
    "2233 3322",
    "to be from HSBC",
    "REWARDCASH",
    "HKD BEST LENDING RATE",
    "LENDING RATE",
    "Number of transactions",
    "Total Relationship Balance",
    "Savings Transaction Details",
    "As of",
    "disclose your personal details",
)

SECTION_HEADER_MARKERS = (
    "Foreign Currency Savings",
    "HKD Savings",
    "HKD Current Account",
    "ACCOUNT ACTIVITIES",
)

STOP_PAGE_MARKERS = (
    "Important Notice",
    "MESSAGES",
    "HKD BEST LENDING RATE",
    "Number of transactions",
    "Total Relationship Balance",
)


def _cluster_rows(words: list[dict], tolerance: float = 4.0) -> dict[float, list[dict]]:
    rows: dict[float, list[dict]] = defaultdict(list)
    for word in words:
        key = round(word["top"] / tolerance) * tolerance
        rows[key].append(word)
    return rows


def _column_bounds(words: list[dict]) -> dict[str, float] | None:
    rows = _cluster_rows(words, tolerance=3)
    header_row = None
    for y in sorted(rows):
        row_words = rows[y]
        texts = {word["text"] for word in row_words}
        if not {"Date", "Deposit", "Withdrawal", "Balance"}.issubset(texts):
            continue
        if "Details" in texts or "Transaction" in texts:
            header_row = row_words
            break

    if not header_row:
        return None

    anchors: dict[str, float] = {}
    for word in header_row:
        text = word["text"]
        if text == "Date":
            anchors["date"] = word["x0"]
        elif text == "CCY":
            anchors["ccy"] = word["x0"]
        elif text in {"Details", "Transaction"} and "details" not in anchors:
            anchors["details"] = word["x0"]
        elif text == "Deposit":
            anchors["deposit"] = word["x0"]
        elif text == "Withdrawal":
            anchors["withdrawal"] = word["x0"]
        elif text == "Balance":
            anchors["balance"] = word["x0"]

    if "date" not in anchors or "balance" not in anchors:
        return None
    return anchors


def _nearest_amount_column(x0: float, anchors: dict[str, float]) -> str | None:
    amount_cols = [name for name in ("deposit", "withdrawal", "balance") if name in anchors]
    if not amount_cols:
        return None
    return min(amount_cols, key=lambda name: abs(x0 - anchors[name]))


def _date_parts_from_row(row_words: list[dict], details_x: float, date_x: float) -> list[str]:
    parts = []
    for word in sorted(row_words, key=lambda item: item["x0"]):
        if word["x0"] >= details_x - 3:
            break
        if word["x0"] > date_x + 35:
            break
        parts.append(word["text"])

    if not is_valid_day_month_parts(parts):
        return []

    if len(parts) == 1 and DATE_TOKEN.match(parts[0]):
        return parts
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isalpha():
        return parts[:2]
    return []


def _amounts_from_row(row_words: list[dict], anchors: dict[str, float]) -> dict[str, float | None]:
    amounts = {"deposit": None, "withdrawal": None, "balance": None}
    for word in row_words:
        value = _parse_amount(word["text"])
        if value is None:
            continue
        column = _nearest_amount_column(word["x0"], anchors)
        if column:
            amounts[column] = value
    return amounts


def _details_from_row(row_words: list[dict], anchors: dict[str, float]) -> str:
    details_x = anchors.get("details", anchors["date"] + 30)
    ccy_x = anchors.get("ccy", details_x)
    left = min(details_x, ccy_x) - 3
    right = anchors.get("deposit", 9999) - 5
    words = [
        word["text"]
        for word in sorted(row_words, key=lambda item: item["x0"])
        if left <= word["x0"] < right and not _parse_amount(word["text"])
    ]
    return " ".join(words).strip()


def _ccy_from_row(row_words: list[dict], anchors: dict[str, float]) -> str | None:
    if "ccy" not in anchors:
        return None
    for word in row_words:
        if abs(word["x0"] - anchors["ccy"]) < 20 and CCY_RE.match(word["text"]):
            return word["text"]
    return None


def _clean_details(details: str) -> str:
    markers = FOOTER_MARKERS + (
        "Hongkong",
        "Thank you",
        "Corporation Limited",
        "CIFSTM",
        "IPSSTM",
        "and Shanghai Banking",
    )
    lowered = details.lower()
    cut_at = len(details)
    for marker in markers:
        idx = lowered.find(marker.lower())
        if idx != -1:
            cut_at = min(cut_at, idx)
    return details[:cut_at].strip()


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _is_footer_row(details: str) -> bool:
    return _contains_marker(details, FOOTER_MARKERS)


def _is_section_header_row(details: str) -> bool:
    if not details:
        return False
    normalized = details.strip().lower()
    return any(marker.lower() == normalized for marker in SECTION_HEADER_MARKERS)


def _should_stop_page(details: str) -> bool:
    return _contains_marker(details, STOP_PAGE_MARKERS)


def _is_garbage_transaction(details: str) -> bool:
    if not details:
        return True
    if "%" in details:
        return True
    if _contains_marker(details, ("2233 3000", "BEST LENDING RATE", "5.2500%", "5.1250%")):
        return True
    if len(details) > 180 and _contains_marker(details, ("fraudulent", "suspicious third parties")):
        return True
    return False


def _new_transaction(
    account: str,
    date_value: str,
    details: str,
    amounts: dict[str, float | None],
    ccy: str | None,
) -> dict:
    return {
        "Account": account,
        "Date": date_value,
        "Transaction Details": details,
        "Deposit": amounts["deposit"],
        "Withdrawal": amounts["withdrawal"],
        "Balance": amounts["balance"],
        "CCY": ccy if ccy else "HKD",
    }


def _has_movement(amounts: dict[str, float | None]) -> bool:
    return amounts["deposit"] is not None or amounts["withdrawal"] is not None


def _parse_date_token(parts: list[str], statement_date: datetime.date) -> str | None:
    if not parts:
        return None

    if len(parts) == 1 and DATE_TOKEN.match(parts[0]):
        token = parts[0]
    elif len(parts) >= 2 and parts[0].isdigit() and parts[1].isalpha():
        token = f"{parts[0]}-{parts[1]}"
    else:
        return None

    parsed = parse_day_month(token, statement_date)
    return parsed.strftime("%Y-%m-%d")


def _parse_amount(text: str) -> float | None:
    if not AMOUNT.match(text):
        return None
    return float(text.replace(",", ""))


def _extract_account_name(page_text: str) -> str:
    for pattern in (
        r"(HKD Current Account)",
        r"(HKD Savings(?:\s+Account)?)",
        r"(Foreign Currency Savings)",
        r"(FCY Savings)",
    ):
        match = re.search(pattern, page_text, re.I)
        if match:
            return normalize_account_name(match.group(1).strip())
    return "Unknown Account"


def _parse_page_transactions(
    page,
    statement_date: datetime.date,
    account: str,
    current: dict | None = None,
    last_date: str | None = None,
) -> tuple[list[dict], dict | None, str | None]:
    words = page.extract_words()
    anchors = _column_bounds(words)
    if not anchors:
        return [], current, last_date

    header_words = [w for w in words if w["text"] == "Date"]
    if not header_words:
        return [], current, last_date
    header_y = min(word["top"] for word in header_words)
    rows = _cluster_rows([w for w in words if w["top"] > header_y + 6])

    transactions: list[dict] = []
    details_x = anchors.get("details", anchors["date"] + 30)
    date_x = anchors["date"]

    for y in sorted(rows):
        row_words = sorted(rows[y], key=lambda w: w["x0"])
        date_parts = _date_parts_from_row(row_words, details_x, date_x)
        details = _clean_details(_details_from_row(row_words, anchors))
        amounts = _amounts_from_row(row_words, anchors)
        ccy = _ccy_from_row(row_words, anchors)

        if _should_stop_page(details):
            break

        if not details and not date_parts and not any(amounts.values()):
            continue
        if _is_footer_row(details):
            continue

        if _is_section_header_row(details):
            if current:
                transactions.append(current)
                current = None
            continue

        date_value = _parse_date_token(date_parts, statement_date) if date_parts else None
        if date_value:
            last_date = date_value
            if current:
                transactions.append(current)
            current = _new_transaction(account, date_value, details, amounts, ccy)
            continue

        if current is None:
            if _has_movement(amounts) and last_date and details:
                current = _new_transaction(account, last_date, details, amounts, ccy)
            continue

        if details and "B/F BALANCE" in details.upper():
            transactions.append(current)
            current = None
            continue

        if ccy and current.get("CCY") and ccy != current["CCY"]:
            transactions.append(current)
            current = _new_transaction(account, current["Date"], details, amounts, ccy)
            continue

        if _has_movement(amounts) and _has_movement(
            {"deposit": current.get("Deposit"), "withdrawal": current.get("Withdrawal"), "balance": None}
        ):
            transactions.append(current)
            current = _new_transaction(account, current["Date"], details, amounts, ccy or current.get("CCY"))
            continue

        if details:
            if _is_footer_row(details):
                continue
            current["Transaction Details"] = (
                f"{current['Transaction Details']} {details}".strip()
                if current["Transaction Details"]
                else details
            )
            current["Transaction Details"] = _clean_details(current["Transaction Details"])
        for key, column in (("Deposit", "deposit"), ("Withdrawal", "withdrawal"), ("Balance", "balance")):
            if amounts[column] is not None:
                current[key] = amounts[column]
        if ccy:
            current["CCY"] = ccy

    completed = [row for row in transactions if not _is_garbage_transaction(row["Transaction Details"])]
    return completed, current, last_date


def parse_bank_pdf(pdf_path: str) -> pd.DataFrame:
    statement_date = parse_statement_date(pdf_path)
    rows: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        account = "Unknown Account"
        current: dict | None = None
        last_date: str | None = None

        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if any(
                marker in page_text
                for marker in ("Current Account", "Savings", "Transaction History", "ACCOUNT ACTIVITIES")
            ):
                new_account = _extract_account_name(page_text)
                if new_account != account and current is not None:
                    rows.append(current)
                    current = None
                account = new_account

            page_rows, current, last_date = _parse_page_transactions(
                page, statement_date, account, current, last_date
            )
            rows.extend(page_rows)

        if current is not None:
            rows.append(current)

    if not rows:
        raise ValueError("No transactions found in bank account statement")

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    df["Account"] = df["Account"].map(normalize_account_name)
    df["Transaction Details"] = df["Transaction Details"].map(_clean_details)
    df = df[~df["Transaction Details"].map(_is_garbage_transaction)]
    return df.reset_index(drop=True)
