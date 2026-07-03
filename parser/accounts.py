"""Normalize HSBC account names for consistent reporting."""

from __future__ import annotations

ACCOUNT_ALIASES = {
    "foreign currency savings": "HKD Savings",
    "fcy savings": "HKD Savings",
    "hkd savings account": "HKD Savings",
    "hkd savings": "HKD Savings",
}


def normalize_account_name(name: str) -> str:
    return ACCOUNT_ALIASES.get(name.strip().lower(), name.strip())
