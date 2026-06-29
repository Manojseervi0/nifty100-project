import sqlite3
import pandas as pd

DB_PATH = "nifty100.db"

FILES = {
    "companies": ("data/companies.xlsx", 1),
    "profitandloss": ("data/profitandloss.xlsx", 1),
    "balancesheet": ("data/balancesheet.xlsx", 1),
    "cashflow": ("data/cashflow.xlsx", 1),
    "analysis": ("data/analysis.xlsx", 1),
    "documents": ("data/documents.xlsx", 1),
    "prosandcons": ("data/prosandcons.xlsx", 1),
    "financial_ratios": ("data/financial_ratios.xlsx", 0),
    "sectors": ("data/sectors.xlsx", 0),
    "peer_groups": ("data/peer_groups.xlsx", 0),
    "stock_prices": ("data/stock_prices.xlsx", 0),
    "market_cap": ("data/market_cap.xlsx", 0),
}

conn = sqlite3.connect(DB_PATH)

for table_name, (file_path, header_row) in FILES.items():

    print(f"\nLoading {table_name}...")

    df = pd.read_excel(file_path, header=header_row)

    if "company_id" in df.columns:
        df["company_id"] = (
            df["company_id"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

    if "id" in df.columns:
        df["id"] = (
            df["id"]
            .astype(str)
            .str.strip()
        )

    df.to_sql(
        table_name,
        conn,
        if_exists="replace",
        index=False
    )

    print(f"{len(df)} rows loaded")

conn.close()

print("\nDatabase load complete.")