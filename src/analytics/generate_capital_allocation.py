import sqlite3
import pandas as pd

conn = sqlite3.connect("nifty100.db")

df = pd.read_sql("""
SELECT
    company_id,
    year,
    operating_activity,
    investing_activity,
    financing_activity
FROM cashflow
""", conn)

records = []

for _, row in df.iterrows():

    cfo = row["operating_activity"]
    cfi = row["investing_activity"]
    cff = row["financing_activity"]

    cfo_sign = "+" if cfo >= 0 else "-"
    cfi_sign = "+" if cfi >= 0 else "-"
    cff_sign = "+" if cff >= 0 else "-"

    pattern = (cfo_sign, cfi_sign, cff_sign)

    if pattern == ("+", "-", "-"):
        label = "Reinvestor"

    elif pattern == ("+", "+", "-"):
        label = "Liquidating Assets"

    elif pattern == ("-", "+", "+"):
        label = "Distress Signal"

    elif pattern == ("-", "-", "+"):
        label = "Growth Funded by Debt"

    elif pattern == ("+", "+", "+"):
        label = "Cash Accumulator"

    elif pattern == ("-", "-", "-"):
        label = "Pre-Revenue"

    elif pattern == ("+", "-", "+"):
        label = "Mixed"

    else:
        label = "Other"

    records.append({
        "company_id": row["company_id"],
        "year": row["year"],
        "cfo_sign": cfo_sign,
        "cfi_sign": cfi_sign,
        "cff_sign": cff_sign,
        "pattern_label": label
    })

output = pd.DataFrame(records)

output.to_csv(
    "output/capital_allocation.csv",
    index=False
)

print("capital_allocation.csv generated")