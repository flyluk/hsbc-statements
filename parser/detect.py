"""Detect HSBC HK statement PDF format."""

from __future__ import annotations

from enum import Enum

from pdfminer.high_level import extract_text


class StatementFormat(str, Enum):
    ACCOUNT_ACTIVITIES = "account_activities"
    CREDIT_CARD = "credit_card"
    ESTATEMENT = "estatement"


def detect_format(pdf_path: str) -> StatementFormat:
    text = extract_text(pdf_path) or ""

    if "ACCOUNT ACTIVITIES" in text or "Statement of Account" in text:
        return StatementFormat.ACCOUNT_ACTIVITIES
    if "Description of transaction" in text and "Post date" in text:
        return StatementFormat.CREDIT_CARD
    if "Account Transaction History" in text or "HSBC One Account Transaction History" in text:
        return StatementFormat.ESTATEMENT

    raise ValueError("Unrecognized HSBC statement format")
