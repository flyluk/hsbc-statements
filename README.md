# HSBC HK Statement Extractor

Convert HSBC Hong Kong bank and credit card statements (PDF or CSV) into a single Excel workbook.

No browser automation, login, or OTP — you download statements yourself from [HSBC Online Banking](https://www.hsbc.com.hk/) or from eStatement email attachments, then run one local command.

## Requirements

- Python 3.10 or newer
- Dependencies listed in `requirements.txt`

Use a virtual environment so this project's packages stay separate from other Python tools on your machine (e.g. docling, streamlit).

## Quick start

```bash
git clone https://github.com/flyluk/hsbc-statements.git
cd hsbc-statements
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Drop PDF or CSV files into `statements/`, then:

```bash
python extract.py
```

Open the latest file in `output/` (e.g. `output/transactions_20260702_194533.xlsx`).

## Folder layout

```
hsbc-statements/
├── statements/     ← drop PDF or CSV files here (not committed to git)
├── output/         ← Excel output (not committed to git)
├── processed/      ← optional archive after successful parse
├── extract.py
├── excel-prompt.txt
├── parser/
└── requirements.txt
```

## Monthly workflow

1. Log in to HSBC Online Banking (or open an eStatement email)
2. Download the monthly **eStatement PDF** or a **CSV** export from transaction search
3. Copy files into `statements/`
4. Activate the venv and run `python extract.py`
5. Open the timestamped workbook in `output/`

To move successfully parsed files out of the inbox:

```bash
python extract.py --move-processed
```

## Supported files

| Format | Source |
|--------|--------|
| **PDF** | Monthly eStatement (plain or password-protected) |
| **CSV** | Transaction export from HSBC Online Banking |

Supported PDF layouts include account activity statements, eStatement transaction history, and credit card statements.

## Password-protected PDFs

PDFs downloaded directly from HSBC Online Banking are usually **not** password-protected.

Email eStatement attachments often are. Set a password only when needed:

```bash
cp .env.example .env
# edit .env and set HSBC_ESTMT_PASSWORD=...
```

Or pass it on the command line (avoid shell history on shared machines):

```bash
python extract.py --password 'your_password'
```

## Output

Each run writes a timestamped workbook to `output/transactions_YYYYMMDD_HHMMSS.xlsx` (unless you pass `--output`).

### Sheets

| Sheet | Included |
|-------|----------|
| **All Transactions** | Always — all rows from all input files |
| **One per account** | Always — HKD Current, Savings, each credit card, etc. |
| **One per source file** | Only with `--export-statements` |

### Columns

| Column | Description |
|--------|-------------|
| Account | Bank account or credit card name |
| Date | Transaction date (no time component) |
| Transaction Details | Description from the statement |
| Deposit | Credits — positive (bank deposits, card payments) |
| Withdrawal | Debits — positive (bank withdrawals, card charges) |
| Amount | Signed value — positive for credits, negative for debits |
| Balance | Running balance where available |
| CCY | Currency |
| Source File | Original PDF or CSV filename |

Credit card rows are normalized to the same schema as bank accounts. On **All Transactions**, the earliest B/F Balance row per account has `Amount` set from `Balance`.

## Excel summary sheets

`excel-prompt.txt` is a ready-made prompt for Cursor (or similar) to add formula-based **Summary** sheets to the exported workbook — monthly credit card and bank account breakdowns by category. Open the latest `output/transactions_*.xlsx`, paste the prompt, and let the assistant build the helper columns and `SUMIFS` tables.

## CLI options

```bash
python extract.py --help
```

| Option | Description |
|--------|-------------|
| `--input DIR` | Input folder (default: `statements/`) |
| `--output FILE` | Output Excel path (default: `output/transactions_YYYYMMDD_HHMMSS.xlsx`) |
| `--password` | PDF password (or use `HSBC_ESTMT_PASSWORD` in `.env`) |
| `--move-processed` | Move parsed files to `processed/` |
| `--export-statements` | Add one sheet per source statement file (default: skip) |

Processing prints elapsed time per file:

```
Processing 2026-01-03_Statement.pdf...
  OK (2026-01-03_Statement.pdf) — 1.2s
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `pip install requirements.txt` fails | Use `pip install -r requirements.txt` (note the `-r` flag) |
| Dependency conflict warnings after install | Create and use `.venv` as shown in Quick start — do not install into global Python |
| `No PDF or CSV files found` | Copy statement files into `statements/` first |
| PDF parse fails with password error | Set `HSBC_ESTMT_PASSWORD` in `.env` or pass `--password` |

## Privacy and security

This tool runs entirely on your machine. Nothing is uploaded anywhere.

**Never commit or share:**

- `statements/` — raw PDFs and CSVs contain account numbers and transactions
- `output/` — parsed Excel files contain the same data
- `.env` — may hold your eStatement PDF password

These paths are listed in `.gitignore`. Before pushing to a remote, run `git status` and confirm no statement files are staged.

## Credits

PDF parsing is adapted from [HsbcHongKongParser](https://github.com/jerenrich/HsbcHongKongParser) (ported to Python 3).

If HSBC changes statement layouts, parsing may need updates — open an issue with a **redacted** sample (account numbers and personal details removed).
