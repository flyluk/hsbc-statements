"""Apply category-mappings.yaml rules to transaction DataFrames."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

DEFAULT_MAPPINGS_PATH = Path(__file__).resolve().parent.parent / "category-mappings.yaml"

MORTGAGE_SPLIT_RE = re.compile(
    r"principal\s+([\d,]+\.?\d*).*interest\s+([\d,]+\.?\d*)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class CategoryMappings:
    rules: list[dict[str, Any]]
    helper_columns: dict[str, Any]
    default_category: str = "Transfer/Other"


def _load_yaml_text(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_mappings(path: Path | None = None) -> CategoryMappings:
    path = path or DEFAULT_MAPPINGS_PATH
    config = _load_yaml_text(path)
    rules = sorted(config.get("rules", []), key=lambda rule: rule.get("priority", 999))
    return CategoryMappings(
        rules=rules,
        helper_columns=config.get("helper_columns", {}),
    )


def _account_contains(account: str, tokens: list[str]) -> bool:
    upper = account.upper()
    return any(token.upper() in upper for token in tokens)


def compute_is_cc(account: str, helper_columns: dict[str, Any]) -> int:
    tokens = helper_columns.get("IsCC", {}).get("account_contains_any", [])
    return int(_account_contains(account, tokens))


def compute_is_mortgage(account: str, details: str, helper_columns: dict[str, Any]) -> int:
    cfg = helper_columns.get("IsMortgage", {})
    if _account_contains(account, cfg.get("account_contains_any", [])):
        return 1
    upper = details.upper()
    for token in cfg.get("transaction_details_contains_any", []):
        if token.upper() in upper:
            return 1
    return 0


def _details_match(details: str, match: dict[str, Any]) -> bool:
    if match.get("default"):
        return True

    upper = details.upper()
    if "transaction_details_contains_all" in match:
        if not all(token.upper() in upper for token in match["transaction_details_contains_all"]):
            return False

    contains_hits = False
    if "transaction_details_contains_any" in match:
        contains_hits = any(token.upper() in upper for token in match["transaction_details_contains_any"])

    regex_hits = False
    if "transaction_details_regex_any" in match:
        regex_hits = any(
            re.search(pattern, details, re.IGNORECASE)
            for pattern in match["transaction_details_regex_any"]
        )

    has_contains = "transaction_details_contains_any" in match
    has_regex = "transaction_details_regex_any" in match
    if has_contains or has_regex:
        if not (contains_hits or regex_hits):
            return False

    if "account_contains_any" in match:
        # account checked separately when needed
        pass

    return True


def match_rule(
    *,
    account: str,
    details: str,
    is_cc: int,
    is_mortgage: int,
    rule: dict[str, Any],
) -> bool:
    match = rule.get("match", {})
    if match.get("default"):
        return True

    if "is_cc" in match and is_cc != int(match["is_cc"]):
        return False
    if "is_mortgage" in match and is_mortgage != int(match["is_mortgage"]):
        return False
    if "account_contains_any" in match and not _account_contains(account, match["account_contains_any"]):
        return False
    return _details_match(details, match)


def categorize_row(
    *,
    account: str,
    details: str,
    is_cc: int,
    is_mortgage: int,
    mappings: CategoryMappings,
) -> str:
    for rule in mappings.rules:
        if match_rule(
            account=account,
            details=details,
            is_cc=is_cc,
            is_mortgage=is_mortgage,
            rule=rule,
        ):
            return rule["category"]
    return mappings.default_category


def parse_mortgage_split(details: str) -> tuple[float | None, float | None]:
    match = MORTGAGE_SPLIT_RE.search(details)
    if not match:
        return None, None
    principal = float(match.group(1).replace(",", ""))
    interest = float(match.group(2).replace(",", ""))
    return principal, interest


def apply_categories(df: pd.DataFrame, mappings_path: Path | None = None) -> pd.DataFrame:
    """Add Category, Month, IsCC, IsMortgage, Mortgage Principal, Mortgage Interest."""
    mappings = load_mappings(mappings_path)
    df = df.copy()

    accounts = df["Account"].astype(str)
    details = df["Transaction Details"].astype(str)

    df["IsCC"] = [
        compute_is_cc(account, mappings.helper_columns)
        for account in accounts
    ]
    df["IsMortgage"] = [
        compute_is_mortgage(account, detail, mappings.helper_columns)
        for account, detail in zip(accounts, details, strict=True)
    ]
    df["Category"] = [
        categorize_row(
            account=account,
            details=detail,
            is_cc=is_cc,
            is_mortgage=is_mortgage,
            mappings=mappings,
        )
        for account, detail, is_cc, is_mortgage in zip(
            accounts, details, df["IsCC"], df["IsMortgage"], strict=True
        )
    ]
    df["Month"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m")

    principals: list[float | None] = []
    interests: list[float | None] = []
    for detail, is_mortgage in zip(details, df["IsMortgage"], strict=True):
        if is_mortgage != 1:
            principals.append(None)
            interests.append(None)
            continue
        principal, interest = parse_mortgage_split(detail)
        principals.append(principal)
        interests.append(interest)

    df["Mortgage Principal"] = principals
    df["Mortgage Interest"] = interests
    return df
