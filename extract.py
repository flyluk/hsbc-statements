#!/usr/bin/env python3
"""Extract HSBC HK statements from a drop folder into Excel."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
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
    return normalize_accounts(df)


def load_pdf(path: Path, password: str | None) -> pd.DataFrame:
    df = parse_pdf(str(path), password)
    df["Source File"] = path.name
    return normalize_accounts(df)


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


def export_excel(frames: list[pd.DataFrame], output_path: Path) -> None:
    combined = pd.concat(frames, ignore_index=True)
    sort_cols = [col for col in ("Date", "Transaction Date", "Account") if col in combined.columns]
    if sort_cols:
        combined = combined.sort_values(sort_cols, na_position="last")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    used_sheet_names: set[str] = set()

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        all_name = _unique_sheet_name("All Transactions", used_sheet_names)
        combined.to_excel(writer, sheet_name=all_name, index=False)

        if "Account" in combined.columns:
            for account, group in combined.groupby("Account", sort=True):
                sheet_name = _unique_sheet_name(str(account), used_sheet_names)
                group.to_excel(writer, sheet_name=sheet_name, index=False)

        if "Source File" in combined.columns:
            for source_file, group in combined.groupby("Source File", sort=True):
                sheet_name = _unique_sheet_name(Path(source_file).stem, used_sheet_names)
                group.to_excel(writer, sheet_name=sheet_name, index=False)


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
        default=OUTPUT_DIR / "transactions.xlsx",
        help=f"Output Excel file (default: {OUTPUT_DIR / 'transactions.xlsx'})",
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
    return parser.parse_args()


def main() -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    input_dir = args.input
    password = args.password or os.environ.get("HSBC_ESTMT_PASSWORD")

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
        try:
            if path.suffix.lower() == ".csv":
                frames.append(load_csv(path))
            else:
                frames.append(load_pdf(path, password))
            print(f"  OK ({path.name})")
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

    export_excel(frames, args.output)
    print(f"\nSaved {len(frames)} file(s) to {args.output}")

    if errors:
        print("\nSome files failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
