"""Detect Citi Hong Kong statement PDF format."""

from __future__ import annotations

from enum import Enum

from pdfminer.high_level import extract_text


class CitiStatementFormat(str, Enum):
    LOAN = "loan"
    ESTATEMENT = "estatement"
    CREDIT_CARD = "credit_card"


def detect_format(pdf_path: str) -> CitiStatementFormat:
    text = extract_text(pdf_path) or ""

    if "LOAN STATEMENT" in text or "貸款結單" in text:
        return CitiStatementFormat.LOAN
    if "閣下戶口之交易記錄" in text or "閣下之戶口總覽" in text:
        return CitiStatementFormat.ESTATEMENT
    if "BALANCE FORWARD" in text or "STATEMENT BALANCE" in text:
        return CitiStatementFormat.CREDIT_CARD
    if "CITI CLEAR CARD" in text and "Page 1 of" in text:
        return CitiStatementFormat.CREDIT_CARD

    raise ValueError("Unrecognized Citi statement format")
