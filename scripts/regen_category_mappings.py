#!/usr/bin/env python3
"""Regenerate category-mappings.yaml from an exported transactions workbook."""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKBOOK = ROOT / "output" / "transactions_20260703_140341.xlsx"
OUTPUT_PATH = ROOT / "category-mappings.yaml"

KEYWORDS = [
    "承上結餘", "B/F BALANCE", "MORTGAGE PAYMENT", "THANK YOU", "PAID BY AUTOPAY", "IFS PAYMENT",
    "DCC FEE", "HANDLING FEE", "INSTALMENT", "CLEAR CARD REBATE", "REBATE CREDIT", "BALANCE ADJUSTMENT",
    "APPLE.COM/BILL", "SMARTONE", "INLAND REVENUE", "BRACES AND FACES", "CITIBANK EUROPE",
    "PAYROLL", "CIGNA", "OCBC BK-AUTO", "TO FUTUSEC", "STANDING INSTRUCTION", "RATING AND VALUATION",
    "CREDIT INTEREST", "存入利息", "MANULIFE", "AIA INTERNATIONAL", "其他服務費", "流動銀行繳賬", "支付貸款",
    "CLP POWER", "DSG ENERGY", "APC COLL-WATER", "TO PAYME(HSBC)", "JOCKEY", "CINEMA", "UTMB.WORLD",
    "PAYPAL *", "GOOGLE*", "GOOGLE WORKSPACE", "MICROSOFT", "SPOTIFY", "DISNEY", "PLAYSTATION",
    "AMAZON PRIME", "AMAZON WEB SERVICES", "PDFE.COM", "IQIYI", "VELOVIEWER", "FUSION", "STARBUCKS",
    "MCDONALDS", "MCDONALD'S", "RESTAURANT", "FOODIES", "HOTPOT", "TOMYUMS", "MARKET PLACE", "MANNINGS",
    "SHELL HK", "UNIQLO", "FADDY LIGHTING", "LCX LIMITED", "FORTRESS", "HKETOLL", "AUTOTOLL", "TRIP.COM",
    "TRIP COM", "PAYALL-RENTAL", "PAYALL SERVICES FEE", "HSBC ITS", "DISCOVERY BAY S M LD",
    "DISCOVERY BAY RECREATION", "HKBN", "AEON CREDIT", "CR TO", "WKNFT", "MBKFT", "HSBC H.K. OFFICE RENTAL",
    "ATM WITHDRAWAL", "MOBILE WITHDRAWAL", "DROP-IN BOX", "支票提款", "退回發出支票", "CASH",
    "轉數快", "SUN HUNG KAI", "PLC LIGHTING", "DON DON TEI", "MAXIM'S", "NESPRESSO", "TASTE",
    "OCTOPUS", "PAYALL", "易辦事付款", "自動轉賬支出 CITIBANK", "存入本地匯款", "CURSOR",
    "ASSOC OF ATHL", "DELICACY FOOD", "SICHUAN", "THAI RESTAURANT", "PEKING", "CHUN SHUI TANG",
]

RULES = [
    {"category": "Opening Balance", "priority": 1,
     "match": {"transaction_details_contains_any": ["承上結餘", "B/F BALANCE"]}},
    {"category": "Mortgage", "priority": 2,
     "match": {"is_mortgage": 1}},
    {"category": "Card Payment", "priority": 10,
     "match": {"is_cc": 1, "transaction_details_regex_any": [
         "THANK YOU", "PAID BY AUTOPAY", r"IFS PAYMENT\s*-", r"AUTOPAY\s*-THANK YOU"]}},
    {"category": "DCC Fees", "priority": 11,
     "match": {"is_cc": 1, "transaction_details_contains_any": ["DCC FEE"]}},
    {"category": "Instalment Fee", "priority": 12,
     "match": {"is_cc": 1, "transaction_details_contains_all": ["INSTALMENT", "HANDLING FEE"]}},
    {"category": "Instalment", "priority": 13,
     "match": {"is_cc": 1, "transaction_details_contains_any": ["BT INSTALMENT", "MOB INSTALMENT", "INSTALMENT PGM"]}},
    {"category": "Adjustment", "priority": 14,
     "match": {"is_cc": 1, "transaction_details_contains_any": [
         "CLEAR CARD REBATE", "REBATE CREDIT", "BALANCE ADJUSTMENT", "BAL ADJUSTMENT"]}},
    {"category": "Apple", "priority": 15,
     "match": {"is_cc": 1, "transaction_details_contains_any": ["APPLE.COM/BILL"]}},
    {"category": "Mobile", "priority": 16,
     "match": {"is_cc": 1, "transaction_details_contains_any": ["SMARTONE"]}},
    {"category": "Tax Payment", "priority": 17,
     "match": {"transaction_details_contains_any": ["INLAND REVENUE DEPT", "INLAND REVENUE"]}},
    {"category": "Medical/Dental", "priority": 18,
     "match": {"is_cc": 1, "transaction_details_contains_any": ["BRACES AND FACES"]}},
    {"category": "Bank Fees", "priority": 19,
     "match": {"transaction_details_contains_any": ["PAYALL SERVICES FEE"]}},
    {"category": "Cash/Cheque", "priority": 20,
     "match": {"is_cc": 0, "transaction_details_contains_any": [
         "ATM WITHDRAWAL", "MOBILE WITHDRAWAL", "DROP-IN BOX CHQ", "支票提款", "退回發出支票"],
         "transaction_details_regex_any": [r"^CASH$", r"^\d{6,}\s+港元$"]}},
    {"category": "Transport/Tolls", "priority": 21,
     "match": {"is_cc": 1, "transaction_details_contains_any": ["HKETOLL", "AUTOTOLL"]}},
    {"category": "Fuel", "priority": 22,
     "match": {"transaction_details_contains_any": ["SHELL HK"]}},
    {"category": "Travel", "priority": 23,
     "match": {"is_cc": 1, "transaction_details_contains_any": ["TRIP.COM", "TRIP COM"]}},
    {"category": "Property Management Fee", "priority": 24,
     "match": {"is_cc": 0, "transaction_details_contains_any": ["DISCOVERY BAY S M LD"]}},
    {"category": "Rent", "priority": 25,
     "match": {"transaction_details_contains_any": ["PAYALL-RENTAL", "HSBC H.K. OFFICE RENTAL"]}},
    {"category": "Entertainment", "priority": 26,
     "match": {"transaction_details_contains_any": [
         "TO PAYME(HSBC)", "DISCOVERY BAY RECREATION", "JOCKEY", "CINEMA", "UTMB.WORLD", "ASSOC OF ATHL",
         "CREDIT CARD PAYMENT"]}},
    {"category": "Alipay", "priority": 30,
     "match": {"is_cc": 0, "transaction_details_regex_any": [r"A852-\d+"]}},
    {"category": "Claims Payout", "priority": 31,
     "match": {"is_cc": 0, "transaction_details_contains_any": ["CITIBANK EUROPE PLC"]}},
    {"category": "Salary", "priority": 32,
     "match": {"is_cc": 0, "transaction_details_contains_any": ["PAYROLL", "CIGNA"]}},
    {"category": "Car Loan", "priority": 33,
     "match": {"is_cc": 0, "transaction_details_contains_any": ["OCBC BK-AUTO"]}},
    {"category": "Investment", "priority": 34,
     "match": {"is_cc": 0, "transaction_details_contains_any": ["TO FUTUSEC"]}},
    {"category": "Octopus", "priority": 35,
     "match": {"transaction_details_contains_any": ["OCTOPUS"],
               "transaction_details_regex_any": [r"OCTOPUS\d{10}", r"OCTOPUS \d+ ADD-VA", r"OCTOPUS BALANCE REV"]}},
    {"category": "Standing Order", "priority": 36,
     "match": {"is_cc": 0, "transaction_details_contains_any": ["STANDING INSTRUCTION"]}},
    {"category": "Government", "priority": 37,
     "match": {"transaction_details_contains_any": ["RATING AND VALUATION", "TRAFFIC TICKETS"]}},
    {"category": "Interest", "priority": 38,
     "match": {"is_cc": 0, "transaction_details_contains_any": ["CREDIT INTEREST", "存入利息"]}},
    {"category": "Insurance", "priority": 39,
     "match": {"is_cc": 0, "transaction_details_contains_any": ["MANULIFE", "AIA INTERNATIONAL"]}},
    {"category": "Management Fee", "priority": 40,
     "match": {"is_cc": 0, "transaction_details_contains_any": ["其他服務費"]}},
    {"category": "Credit Payment", "priority": 41,
     "match": {"is_cc": 0, "is_mortgage": 0,
               "transaction_details_contains_any": ["流動銀行繳賬", "AEON CREDIT", "自動轉賬支出 CITIBANK"],
               "transaction_details_regex_any": [r"MBKFT\d", r"NC\d+\(", r"N\d{10,}\("]}},
    {"category": "VTC", "priority": 41.5,
     "match": {"is_cc": 0, "is_mortgage": 0,
               "transaction_details_regex_any": [r"HSBC ITS\(A\)L[-_]FRMT"]}},
    {"category": "Internal Transfer", "priority": 42,
     "match": {"is_cc": 0, "is_mortgage": 0,
               "transaction_details_contains_any": [
                   "存入本地匯款", "CR TO", "流動銀行轉帳"],
               "transaction_details_regex_any": [r"WKNFT\d", r"N\d{10,}\(", r"NC\d+\("]}},
    {"category": "Utilities", "priority": 42.9,
     "match": {"transaction_details_contains_any": ["CLP POWER", "DSG ENERGY", "APC COLL-WATER", "HKBN"]}},
    {"category": "Personal Transfer", "priority": 43,
     "match": {"is_mortgage": 0,
               "transaction_details_contains_any": ["轉數快", "CURSOR"],
               "transaction_details_regex_any": [r"HC[A-Z0-9]{10,}", r"\*{2,}"]}},
    {"category": "Software/Subscription", "priority": 50,
     "match": {"is_cc": 1,
               "transaction_details_contains_any": [
                   "PAYPAL *", "GOOGLE*", "GOOGLE WORKSPACE", "MICROSOFT", "SPOTIFY", "DISNEY",
                   "PLAYSTATION", "IQIYI", "VELOVIEWER", "AMAZON PRIME", "AMAZON WEB SERVICES",
                   "PDFE.COM", "CURSOR", "pdfguru", "Nintendo", "SCMP", "STP*V*", "Google AR"]}},
    {"category": "Groceries", "priority": 51,
     "match": {"is_cc": 1,
               "transaction_details_contains_any": [
                   "FUSION", "MARKET PLACE", "MANNINGS", "NESPRESSO", "TASTEXFRESH", "Nespresso"],
               "transaction_details_regex_any": [r"TASTE \d"]}},
    {"category": "Dining", "priority": 52,
     "match": {"is_cc": 1,
               "transaction_details_contains_any": [
                   "STARBUCKS", "MCDONALDS", "MCDONALD'S", "RESTAURANT", "FOODIES", "HOTPOT",
                   "TOMYUMS", "CHUN SHUI TANG", "SICHUAN", "THAI RESTAURANT", "DELICACY FOOD",
                   "PEKING", "DON DON TEI", "MAXIM'S", "SUN THAI", "PEONY", "UNDER BIG BANYAN",
                   "CITY HALL", "EFTPAY", "KPay*", "BBMSL", "GAIA VEGGIE", "BEANS", "GOLDEN DRAGON",
                   "DAB-PA", "WAYFOONG", "Omotesando", "SUN THAI", "SICHUAN HOUSE", "PEKING GARDEN",
                   "CUPPING ROOM", "ELEPHANT GROUNDS", "Harbourside Grill", "NHA TRANG", "VIETMIAM",
                   "CHOI FOOK", "PACIFIC COFFEE", "NOC COFFEE", "KAM LUNG MOTORS", "THE SUNSET BAY",
                   "ART OF CANTON", "ORERYUSHIO", "XIHE YA YUAN", "TAI HING", "FOODHALL", "UMIMACHIDON",
                   "PHI COFFEE", "PANCAKE", "JASMINE (", "GOOBNE", "THE COFFEE ACADEMICS", "OUTBACK STEAKHOUSE",
                   "PUTIEN", "TONKICHI", "FAT KEE SEAFOOD", "KWAN CHOI KEE"]}},
    {"category": "Home/Shopping", "priority": 53,
     "match": {"transaction_details_contains_any": [
         "UNIQLO", "FADDY LIGHTING", "LCX LIMITED", "FORTRESS", "TILES FAMILY",
         "SUN HUNG KAI", "PLC LIGHTING", "BEST BUY ELECTRIC", "CERAMIC", "CAM2 LIMITED",
         "POLO RALPH LAUREN", "QFPay*", "Sino Trend", "OR TA LIMITED", "LUCKY TIDE",
         "TIN SHING MARBLE", "PLC LOCKS", "HING FAT FLOWER", "JAPAN HOME", "LA CREATION",
         "UNICORN STORES", "SP STEELCASE", "WATSON'S", "China Elegant"]}},
    {"category": "Transfer/Other", "priority": 999, "match": {"default": True}},
]


def extract_keyword_hits(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    extracted: dict[str, Counter] = {}
    for cat in sorted(df["Category"].dropna().unique()):
        sub = df[df["Category"] == cat]
        kws: Counter = Counter()
        for detail in sub["Transaction Details"].astype(str):
            text = detail.upper()
            for kw in KEYWORDS:
                if kw.upper() in text:
                    kws[kw] += 1
            if re.search(r"A852-\d+", text):
                kws["A852-… (Alipay)"] += 1
            if re.search(r"OCTOPUS\d{10}", text):
                kws["OCTOPUS########## (bank top-up)"] += 1
            if re.search(r"MBKFT\d", text):
                kws["MBKFT… (mobile banking)"] += 1
            if re.search(r"WKNFT\d", text):
                kws["WKNFT… (wire transfer in)"] += 1
            if re.search(r"NC\d+\(", text) or re.search(r"N\d{10,}\(", text):
                kws["N…/NC… (card bill payment)"] += 1
            if re.search(r"HC\d{10,}", text):
                kws["HC… (FPS/transfer ref)"] += 1
        extracted[cat] = kws

    return {cat: dict(counter.most_common()) for cat, counter in extracted.items() if counter}


def redact_detail(text: str) -> str:
    text = str(text)
    text = re.sub(r"\d{4,}", "…", text)
    text = re.sub(r"LUK[^,\n]{0,40}", "…", text, flags=re.I)
    text = re.sub(r"CHAN[^,\n]{0,40}", "…", text, flags=re.I)
    text = re.sub(r"YU FEI", "…", text, flags=re.I)
    text = re.sub(r"LEE [A-Z* ]{3,20}", "… ", text)
    text = re.sub(r"WONG [A-Z* ]{3,20}", "… ", text)
    text = re.sub(r"LEUNG [A-Z* ]{3,20}", "… ", text)
    return text.strip()[:80]


def category_signatures(df: pd.DataFrame, category: str, limit: int = 8) -> list[dict]:
    sub = df[df["Category"] == category]
    counts = Counter(redact_detail(d) for d in sub["Transaction Details"])
    return [{"pattern": pat, "count": cnt} for pat, cnt in counts.most_common(limit)]


def category_summary(df: pd.DataFrame) -> dict[str, dict]:
    summaries: dict[str, dict] = {}
    hits = extract_keyword_hits(df)
    for cat in sorted(df["Category"].dropna().unique()):
        sub = df[df["Category"] == cat]
        summaries[cat] = {
            "count": int(len(sub)),
            "is_cc": sorted(int(v) for v in sub["IsCC"].dropna().unique()),
            "is_mortgage": sorted(int(v) for v in sub["IsMortgage"].dropna().unique()),
            "keyword_hits": hits.get(cat, {}),
            "signatures": category_signatures(df, cat),
        }
    return summaries


def build_config(workbook: Path, df: pd.DataFrame) -> dict:
    rel_workbook = workbook.relative_to(ROOT) if workbook.is_relative_to(ROOT) else workbook
    return {
        "source": {
            "workbook": str(rel_workbook),
            "sheet": "All Transactions",
            "row_count": len(df),
            "extracted_from_columns": [
                "Transaction Details", "Account", "Category", "IsCC", "IsMortgage",
            ],
        },
        "helper_columns": {
            "IsCC": {
                "description": "1 for credit card accounts",
                "account_contains_any": ["Visa", "Credit Card", "CLEAR CARD", "CARD", "PLATINUM"],
            },
            "IsMortgage": {
                "description": "1 for Citi mortgage / loan statement rows and linked mortgage payments",
                "account_contains_any": ["Mortgage"],
                "transaction_details_contains_any": ["Mortgage payment", "支付貸款"],
            },
            "Month": {"formula": 'TEXT(Date, "YYYY-MM")'},
            "Category": {"description": "Assigned by rules below"},
        },
        "card_payment_exclusions": ["Card Payment"],
        "summary_scope": {
            "credit_card_table": {"filter": "IsCC = 1 AND Category not in card_payment_exclusions"},
            "bank_account_table": {
                "filter": "IsCC = 0 AND IsMortgage = 0",
                "inflow_column": "Deposit",
                "opening_balance_uses": "Amount",
            },
            "mortgage_table": {"filter": "IsMortgage = 1"},
        },
        "rules": RULES,
        "categories": category_summary(df),
    }


def write_yaml(config: dict, path: Path) -> None:
    header = """# Category mapping rules — auto-generated by scripts/regen_category_mappings.py
# Evaluate rules top-to-bottom; first match wins. Default: Transfer/Other
# Privacy: patterns only — no personal names or account numbers in this file.

"""
    path.write_text(header, encoding="utf-8")
    with path.open("a", encoding="utf-8") as fh:
        yaml.dump(config, fh, default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    workbook = Path(argv[0]) if argv else DEFAULT_WORKBOOK
    if not workbook.is_absolute():
        workbook = ROOT / workbook

    df = pd.read_excel(workbook, sheet_name="All Transactions")
    config = build_config(workbook, df)
    write_yaml(config, OUTPUT_PATH)
    print(f"Wrote {OUTPUT_PATH} ({len(df)} rows, {df['Category'].nunique()} categories)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
