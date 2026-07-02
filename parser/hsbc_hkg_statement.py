"""Parse HSBC Hong Kong eStatement PDFs into transaction tables."""

from __future__ import annotations

import datetime
import re

import dateutil.parser
import pandas as pd

from .pdfminer_utils import (
    find_text,
    get_layouts,
    get_pages_content,
    get_table,
    get_text_in_boxes,
    get_top_most,
    get_underlined_text,
    sectionize,
    single_val,
)

footer = "The Hongkong and Shanghai Banking Corporation Limited"
months = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
day_pattern = r"\d{1,2}"
year_pattern = r"\d{4}"
header = f"{day_pattern} {'|'.join(months)} {year_pattern}"
ccy_default = "HKD"


def ser_carry_foward(ser):
    ser = ser.copy()
    for i in range(1, len(ser)):
        if ser.iloc[i] is None or ser.iloc[i] == "":
            ser.iloc[i] = ser.iloc[i - 1]
    return ser


def collapse_rows(df, data_cols):
    row_group = []
    prev_row = 0
    for i in range(len(df)):
        if not df[data_cols].iloc[i].isnull().all():
            row_group.append(prev_row)
            prev_row = i + 1
        else:
            row_group.append(prev_row)
    df = df.copy()
    df["RowGroup"] = row_group

    def combine_fn(vals):
        vals = [v for v in vals if v is not None]
        vals_set = set(vals)
        if len(vals_set) == 1:
            return vals_set.pop()
        return " ".join(str(v) for v in vals)

    fn_dict = {col: combine_fn for col in df.columns}
    df2 = df.groupby(["RowGroup"])[["Transaction Details"] + data_cols].agg(fn_dict)
    cols = ["Date", "Transaction Details"] + data_cols
    if "CCY" in df.columns:
        cols.append("CCY")
    return df2[cols].reset_index(drop=True)


def get_major_sections(pages):
    headers = get_text_in_boxes(pages)
    return sectionize(pages, headers)


def parse_date(date_txt, statement_date):
    date = dateutil.parser.parse(date_txt, default=statement_date)
    if date > statement_date:
        prior_year = datetime.date(statement_date.year - 1, statement_date.month, statement_date.day)
        date = dateutil.parser.parse(date_txt, default=prior_year)
    return date


def get_transaction_table(sections, statement_date):
    history_header = "Account Transaction History"
    transactions = single_val([s for s in sections if re.search(history_header, s["Text"])])
    if transactions is None:
        raise ValueError("Could not find 'Account Transaction History' section in PDF")

    accounts = get_underlined_text(transactions["Pages"])
    accounts_trans = sectionize(transactions["Pages"], accounts)

    dfs = []
    for trans in accounts_trans:
        for page in trans["Pages"]:
            df = get_table(page)
            if df is None:
                continue
            for col in ["CCY", "Date"]:
                if col in df.columns:
                    df[col] = ser_carry_foward(df[col])
            data_cols = ["Deposit", "Withdrawal", "Balance"]
            df = collapse_rows(df, data_cols)
            df["Account"] = trans["Text"]
            if "CCY" not in df.columns:
                df["CCY"] = ccy_default
            dfs.append(df)

    if not dfs:
        raise ValueError("No transaction rows found in PDF")

    df = pd.concat(dfs, ignore_index=True)
    df["Date"] = df["Date"].apply(lambda x: parse_date(x, statement_date))
    return df


def get_statement_date(layouts):
    objs = layouts[0]._objs
    date_objs = find_text(objs, header)
    date_obj = get_top_most(date_objs)
    date_txt = date_obj._objs[0].get_text().strip()
    return dateutil.parser.parse(date_txt).date()


def pdf_to_transaction_table(filename: str) -> pd.DataFrame:
    layouts = get_layouts(filename)
    statement_date = get_statement_date(layouts)
    pages = get_pages_content(layouts, header, footer)
    sections = get_major_sections(pages)
    df = get_transaction_table(sections, statement_date)

    col_order = ["Account", "Date", "Transaction Details", "Deposit", "Withdrawal", "Balance", "CCY"]
    return df[col_order]
