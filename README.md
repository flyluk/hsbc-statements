# HSBC & Citi HK Statement Extractor

Convert HSBC and Citi Hong Kong bank, credit card, and loan statements (PDF or CSV) into a single Excel workbook.

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

Drop PDF or CSV files into `statements/hsbc/` or `statements/citi/`, then:

```bash
python extract.py
```

Open the latest file in `output/` (e.g. `output/transactions_20260702_194533.xlsx`).

## Folder layout

```
hsbc-statements/
├── statements/
│   ├── hsbc/       ← HSBC PDF or CSV files
│   └── citi/       ← Citi PDF files (eStatement, credit card, loan)
├── output/         ← Excel output (not committed to git)
├── processed/      ← optional archive after successful parse
│   ├── hsbc/
│   └── citi/
├── extract.py
├── excel-prompt.txt
├── parser/
│   ├── citi/       ← Citi-specific parsers
│   └── ...
└── requirements.txt
```

## Monthly workflow

1. Log in to HSBC or Citi online banking (or open an eStatement email)
2. Download monthly **eStatement PDFs** or a **CSV** export (HSBC transaction search)
3. Copy HSBC files into `statements/hsbc/` and Citi files into `statements/citi/`
4. Activate the venv and run `python extract.py`
5. Open the timestamped workbook in `output/`

To move successfully parsed files out of the inbox:

```bash
python extract.py --move-processed
```

## Supported files

| Bank | Format | Source |
|------|--------|--------|
| **HSBC** | PDF | Monthly eStatement (plain or password-protected) |
| **HSBC** | CSV | Transaction export from HSBC Online Banking |
| **Citi** | PDF | Citigold consolidated eStatement (bank accounts) |
| **Citi** | PDF | Credit card eStatement |
| **Citi** | PDF | Mortgage / loan statement |

HSBC PDF layouts include account activity statements, eStatement transaction history, and credit card statements.

## Password-protected PDFs

PDFs downloaded directly from HSBC Online Banking are usually **not** password-protected.

Email eStatement attachments often are. Set a password only when needed:

```bash
cp .env.example .env
# edit .env and set HSBC_ESTMT_PASSWORD=... and/or CITI_ESTMT_PASSWORD=...
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
| Source File | Bank subfolder and original filename (e.g. `citi/eStatement_January.pdf`) |

Credit card rows are normalized to the same schema as bank accounts. On **All Transactions**, the earliest opening-balance row per account (`B/F BALANCE`, `承上結餘`, or `BALANCE FORWARD`) has `Amount` set from `Balance`.

Citi Citigold eStatements, standalone Citi credit card PDFs, and Citi mortgage statements are auto-detected and merged into the same workbook as HSBC data. CSV import is supported for HSBC only.

## Excel summary sheets

`excel-prompt.txt` is a ready-made prompt for Cursor (or similar) to add formula-based **Summary** sheets to the exported workbook. It builds three monthly breakdown tables from **All Transactions**:

| Table | Scope | Header colour |
|-------|--------|---------------|
| **Credit Card** | Spending by category (excludes card payments like THANK YOU) | Blue |
| **Bank Account** | Cheque/savings activity by category (excludes mortgage rows) | Green |
| **Mortgage** | Principal vs interest split (Citi loan statement + linked bank payments) | Purple |

The prompt adds hidden helper columns (`Category`, `Month`, `IsCC`, `IsMortgage`, principal/interest) and uses `SUMIFS` formulas with In / Out / Net columns per month.

**Workflow:** open the latest `output/transactions_*.xlsx`, paste the contents of `excel-prompt.txt`, and let the assistant build the sheets. Use generic category-mapping patterns only — do not commit real names, account numbers, or transaction references to the prompt file.

## CLI options

```bash
python extract.py --help
```

| Option | Description |
|--------|-------------|
| `--input DIR` | Root folder with `hsbc/` and `citi/` subfolders (default: `statements/`) |
| `--output FILE` | Output Excel path (default: `output/transactions_YYYYMMDD_HHMMSS.xlsx`) |
| `--password` | PDF password (or use `HSBC_ESTMT_PASSWORD` / `CITI_ESTMT_PASSWORD` in `.env`) |
| `--move-processed` | Move parsed files to `processed/hsbc/` or `processed/citi/` |
| `--export-statements` | Add one sheet per source statement file (default: skip) |

Processing prints elapsed time per file:

```
Processing [hsbc] 2026-01-03_Statement.pdf...
  OK (2026-01-03_Statement.pdf) — 1.2s
Processing [citi] eStatement_January.pdf...
  OK (eStatement_January.pdf) — 0.2s
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `pip install requirements.txt` fails | Use `pip install -r requirements.txt` (note the `-r` flag) |
| Dependency conflict warnings after install | Create and use `.venv` as shown in Quick start — do not install into global Python |
| `No PDF or CSV files found` | Copy statements into `statements/hsbc/` or `statements/citi/` |
| PDF parse fails with password error | Set `HSBC_ESTMT_PASSWORD` / `CITI_ESTMT_PASSWORD` in `.env` or pass `--password` |

## Privacy and security

This tool runs entirely on your machine. Nothing is uploaded anywhere.

**Never commit or share:**

- `statements/` — raw PDFs and CSVs contain account numbers and transactions
- `output/` — parsed Excel files contain the same data
- `.env` — may hold your eStatement PDF password
- Personal identifiers in `excel-prompt.txt` — use generic mapping patterns; keep your own name/account references in a local copy only

These paths are listed in `.gitignore`. Before pushing to a remote, run `git status` and confirm no statement files are staged.

## Credits

PDF parsing is adapted from [HsbcHongKongParser](https://github.com/jerenrich/HsbcHongKongParser) (ported to Python 3).

If HSBC changes statement layouts, parsing may need updates — open an issue with a **redacted** sample (account numbers and personal details removed).
