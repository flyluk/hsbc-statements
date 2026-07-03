"""Route Citi Hong Kong PDFs to the correct parser."""

from __future__ import annotations

import pandas as pd

from ..pdf_utils import prepare_pdf_path
from .credit_card import parse_credit_card_pdf
from .detect import CitiStatementFormat, detect_format
from .estatement import parse_estatement_pdf
from .loan import parse_loan_pdf


def parse_pdf(source_path: str, password: str | None = None) -> pd.DataFrame:
    from pathlib import Path

    path = Path(source_path)
    readable_path, temp_path = prepare_pdf_path(path, password)
    try:
        fmt = detect_format(str(readable_path))
        if fmt == CitiStatementFormat.LOAN:
            return parse_loan_pdf(str(readable_path))
        if fmt == CitiStatementFormat.ESTATEMENT:
            return parse_estatement_pdf(str(readable_path))
        if fmt == CitiStatementFormat.CREDIT_CARD:
            return parse_credit_card_pdf(str(readable_path))
        raise ValueError(f"Unsupported Citi format: {fmt}")
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
