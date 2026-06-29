import pandas as pd
import re


def normalize_year(year):
    if pd.isna(year):
        return None

    year = str(year).strip()

    if year == "TTM":
        return None

    match = re.search(r"\d{4}", year)

    if match:
        return int(match.group())

    return None


def normalize_ticker(ticker):
    return str(ticker).strip().upper()