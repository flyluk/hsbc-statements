"""Open HSBC PDFs, decrypting with an empty password when needed."""

from __future__ import annotations

import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def prepare_pdf_path(source: Path, password: str | None = None) -> tuple[Path, Path | None]:
    """Return a readable PDF path and an optional temp file to delete afterward."""
    reader = PdfReader(str(source))
    if not reader.is_encrypted:
        return source, None

    passwords = [password] if password else ["", None]
    decrypted = False
    for candidate in passwords:
        if candidate is None:
            continue
        reader = PdfReader(str(source))
        result = reader.decrypt(candidate)
        if result:
            decrypted = True
            break

    if not decrypted:
        if password:
            raise ValueError(f"Could not decrypt {source.name} — check your eStatement password")
        raise ValueError(
            f"{source.name} is password-protected — use --password or set HSBC_ESTMT_PASSWORD in .env"
        )

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    temp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    temp.close()
    temp_path = Path(temp.name)
    with open(temp_path, "wb") as fh:
        writer.write(fh)
    return temp_path, temp_path
