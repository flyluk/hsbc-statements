#!/usr/bin/env python3
"""Extract HSBC HK statements from a drop folder into Excel."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from parser.parse_pdf import parse_pdf
from parser.accounts import normalize_account_name

ROOT = Path(__file__).resolve().parent
STATEMENTS_DIR = ROOT / "statements"
OUTPUT_DIR = ROOT / "output"
PROCESSED_DIR = ROOT / "processed"

SUPPORTED_EXTENSIONS = {".pdf", ".csv"}

STANDARD_COLUMNS = [
    "Account",
    "Date",
    "Transaction Details",
    "Deposit",
    "Withdrawal",
    "Amount",
    "Balance",
    "CCY",
    "Source File",
]


def _signed_amount(df: pd.DataFrame) -> pd.Series:
    amount = pd.Series(pd.NA, index=df.index, dtype="Float64")
    if "Deposit" in df.columns:
        deposit_mask = df["Deposit"].notna()
        amount.loc[deposit_mask] = df.loc[deposit_mask, "Deposit"].abs()
    if "Withdrawal" in df.columns:
        withdrawal_mask = df["Withdrawal"].notna()
        amount.loc[withdrawal_mask] = -df.loc[withdrawal_mask, "Withdrawal"].abs()
    return amount


def _date_only_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
            continue
        if "date" in col.lower():
            parsed = pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().any():
                df[col] = parsed.dt.date
    return df


def normalize_transaction_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Align credit card and bank rows to a common schema with signed Amount."""
    df = df.copy()

    if "Amount" in df.columns and "Credit/Debit" in df.columns:
        if "Date" not in df.columns:
            df["Date"] = pd.NaT
        missing_date = df["Date"].isna()
        if missing_date.any():
            for col in ("Transaction Date", "Post Date"):
                if col in df.columns:
                    df.loc[missing_date, "Date"] = df.loc[missing_date, col]
                    missing_date = df["Date"].isna()
                    if not missing_date.any():
                        break

        direction = df["Credit/Debit"].astype(str).str.strip().str.lower()
        is_credit = direction == "credit"
        is_debit = direction == "debit"

        df.loc[is_credit, "Deposit"] = df.loc[is_credit, "Amount"].abs()
        df.loc[is_debit, "Withdrawal"] = df.loc[is_debit, "Amount"].abs()

        df = df.drop(columns=["Amount", "Credit/Debit", "Post Date", "Transaction Date"], errors="ignore")

    if "Deposit" in df.columns:
        deposit_mask = df["Deposit"].notna() & (df["Deposit"] < 0)
        df.loc[deposit_mask, "Deposit"] = df.loc[deposit_mask, "Deposit"].abs()

    if "Withdrawal" in df.columns:
        withdrawal_mask = df["Withdrawal"].notna() & (df["Withdrawal"] < 0)
        df.loc[withdrawal_mask, "Withdrawal"] = df.loc[withdrawal_mask, "Withdrawal"].abs()

    df["Amount"] = _signed_amount(df)

    for col in STANDARD_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    return _date_only_columns(df[STANDARD_COLUMNS])


def normalize_csv_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "transaction date": "Date",
        "date": "Date",
        "transaction details": "Transaction Details",
        "description": "Transaction Details",
        "details": "Transaction Details",
        "deposit": "Deposit",
        "credit": "Deposit",
        "withdrawal": "Withdrawal",
        "debit": "Withdrawal",
        "balance": "Balance",
        "currency": "CCY",
        "ccy": "CCY",
        "account": "Account",
    }
    normalized = {col: rename_map.get(col.strip().lower(), col) for col in df.columns}
    df = df.rename(columns=normalized)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    return df


def normalize_accounts(df: pd.DataFrame) -> pd.DataFrame:
    if "Account" in df.columns:
        df = df.copy()
        df["Account"] = df["Account"].map(normalize_account_name)
    return df


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = normalize_csv_columns(df)
    if "Account" not in df.columns:
        df["Account"] = path.stem
    if "Source File" not in df.columns:
        df["Source File"] = path.name
    return normalize_transaction_frame(normalize_accounts(df))


def load_pdf(path: Path, password: str | None) -> pd.DataFrame:
    df = parse_pdf(str(path), password)
    df["Source File"] = path.name
    return normalize_transaction_frame(normalize_accounts(df))


def collect_files(input_dir: Path) -> list[Path]:
    files = []
    for path in sorted(input_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
    return files


def _unique_sheet_name(name: str, used: set[str]) -> str:
    for char in (":", "\\", "/", "?", "*", "[", "]"):
        name = name.replace(char, "_")
    name = name[:31]
    base = name
    counter = 2
    while name in used:
        suffix = f" ({counter})"
        name = f"{base[: 31 - len(suffix)]}{suffix}"
        counter += 1
    used.add(name)
    return name


def _fill_earliest_bf_amounts(df: pd.DataFrame) -> pd.DataFrame:
    """Set Amount from Balance on the earliest B/F BALANCE row per account."""
    df = df.copy()
    bf_mask = df["Transaction Details"].astype(str).str.contains(
        r"B/F\s*BALANCE", case=False, na=False, regex=True
    )
    if not bf_mask.any():
        return df

    earliest = (
        df.loc[bf_mask]
        .sort_values(["Account", "Date"])
        .groupby("Account", sort=False)
        .head(1)
        .index
    )
    df.loc[earliest, "Amount"] = df.loc[earliest, "Balance"]
    return df


def _apply_date_formats(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame) -> None:
    ws = writer.sheets[sheet_name]
    for col_idx, col in enumerate(df.columns, start=1):
        if "date" not in col.lower():
            continue
        for row_idx in range(2, len(df) + 2):
            cell = ws.cell(row=row_idx, column=col_idx)
            if cell.value is not None:
                cell.number_format = "yyyy-mm-dd"


def export_excel(
    frames: list[pd.DataFrame],
    output_path: Path,
    *,
    export_statements: bool = False,
) -> None:
    combined = _date_only_columns(pd.concat(frames, ignore_index=True))
    sort_cols = [col for col in ("Date", "Account") if col in combined.columns]
    if sort_cols:
        combined = combined.sort_values(sort_cols, na_position="last")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    used_sheet_names: set[str] = set()

    with pd.ExcelWriter(
        output_path,
        engine="openpyxl",
        date_format="yyyy-mm-dd",
        datetime_format="yyyy-mm-dd",
    ) as writer:
        all_name = _unique_sheet_name("All Transactions", used_sheet_names)
        all_transactions = _fill_earliest_bf_amounts(combined)
        all_transactions.to_excel(writer, sheet_name=all_name, index=False)
        _apply_date_formats(writer, all_name, all_transactions)

        if "Account" in combined.columns:
            for account, group in combined.groupby("Account", sort=True):
                sheet_name = _unique_sheet_name(str(account), used_sheet_names)
                group.to_excel(writer, sheet_name=sheet_name, index=False)
                _apply_date_formats(writer, sheet_name, group)

        if export_statements and "Source File" in combined.columns:
            for source_file, group in combined.groupby("Source File", sort=True):
                sheet_name = _unique_sheet_name(Path(source_file).stem, used_sheet_names)
                group.to_excel(writer, sheet_name=sheet_name, index=False)
                _apply_date_formats(writer, sheet_name, group)


def timestamped_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"transactions_{stamp}.xlsx"


def move_to_processed(path: Path) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    destination = PROCESSED_DIR / path.name
    if destination.exists():
        destination.unlink()
    shutil.move(str(path), str(destination))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert HSBC HK statements (PDF/CSV) dropped in statements/ into Excel."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=STATEMENTS_DIR,
        help=f"Folder containing statement files (default: {STATEMENTS_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output Excel file (default: output/transactions_YYYYMMDD_HHMMSS.xlsx)",
    )
    parser.add_argument(
        "--password",
        help="Only needed for password-protected PDFs (or set HSBC_ESTMT_PASSWORD in .env)",
    )
    parser.add_argument(
        "--move-processed",
        action="store_true",
        help="Move successfully parsed files to processed/",
    )
    parser.add_argument(
        "--export-statements",
        action="store_true",
        help="Add one sheet per source statement file (default: skip)",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    input_dir = args.input
    password = args.password or os.environ.get("HSBC_ESTMT_PASSWORD")
    output_path = args.output or timestamped_output_path()

    input_dir.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = collect_files(input_dir)
    if not files:
        print(f"No PDF or CSV files found in {input_dir}")
        print("Drop your HSBC statements there and run again.")
        return 1

    frames: list[pd.DataFrame] = []
    errors: list[str] = []

    for path in files:
        print(f"Processing {path.name}...")
        started = time.perf_counter()
        try:
            if path.suffix.lower() == ".csv":
                frames.append(load_csv(path))
            else:
                frames.append(load_pdf(path, password))
            elapsed = time.perf_counter() - started
            print(f"  OK ({path.name}) — {elapsed:.1f}s")
            if args.move_processed:
                move_to_processed(path)
        except Exception as exc:
            msg = f"{path.name}: {exc}"
            errors.append(msg)
            print(f"  FAILED — {exc}")

    if not frames:
        print("\nNo files were parsed successfully.")
        for err in errors:
            print(f"  - {err}")
        return 1

    export_excel(frames, output_path, export_statements=args.export_statements)
    print(f"\nSaved {len(frames)} file(s) to {output_path}")

    if errors:
        print("\nSome files failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
