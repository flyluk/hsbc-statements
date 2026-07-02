"""Route HSBC PDFs to the correct parser."""

from __future__ import annotations

import pandas as pd

from .bank_table import parse_bank_pdf
from .credit_card import parse_credit_card_pdf
from .detect import StatementFormat, detect_format
from .hsbc_hkg_statement import pdf_to_transaction_table
from .pdf_utils import prepare_pdf_path


def parse_pdf(source_path: str, password: str | None = None) -> pd.DataFrame:
    from pathlib import Path

    path = Path(source_path)
    readable_path, temp_path = prepare_pdf_path(path, password)
    try:
        fmt = detect_format(str(readable_path))
        if fmt == StatementFormat.CREDIT_CARD:
            return parse_credit_card_pdf(str(readable_path))
        if fmt in {StatementFormat.ACCOUNT_ACTIVITIES, StatementFormat.ESTATEMENT}:
            try:
                return parse_bank_pdf(str(readable_path))
            except ValueError:
                if fmt == StatementFormat.ESTATEMENT:
                    return pdf_to_transaction_table(str(readable_path))
                raise
        raise ValueError(f"Unsupported format: {fmt}")
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
