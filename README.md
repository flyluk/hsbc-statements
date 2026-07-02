# HSBC HK Statement Extractor

Convert HSBC Hong Kong bank and credit card statements (PDF or CSV) into a single Excel workbook.

No browser automation, login, or OTP — you download statements yourself from [HSBC Online Banking](https://www.hsbc.com.hk/) or from eStatement email attachments, then run one local command.

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

Open `output/transactions.xlsx`.

## Folder layout

```
hsbc-statements/
├── statements/     ← drop PDF or CSV files here (not committed to git)
├── output/         ← Excel output (not committed to git)
├── processed/      ← optional archive after successful parse
├── extract.py
├── parser/
└── requirements.txt
```

## Monthly workflow

1. Log in to HSBC Online Banking (or open an eStatement email)
2. Download the monthly **eStatement PDF** or a **CSV** export from transaction search
3. Copy files into `statements/`
4. Run `python extract.py`
5. Open `output/transactions.xlsx`

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

`output/transactions.xlsx` includes:

- **All Transactions** — every row from all input files, combined
- One sheet per account (when the PDF contains multiple accounts)
- One sheet per source file

Columns: Account, Date, Transaction Details, Deposit, Withdrawal, Balance, CCY, Source File

## CLI options

```bash
python extract.py --help
```

| Option | Description |
|--------|-------------|
| `--input DIR` | Input folder (default: `statements/`) |
| `--output FILE` | Output Excel path (default: `output/transactions.xlsx`) |
| `--password` | PDF password (or use `HSBC_ESTMT_PASSWORD` in `.env`) |
| `--move-processed` | Move parsed files to `processed/` |

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
