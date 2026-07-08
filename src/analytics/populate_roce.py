import sqlite3
import pandas as pd

from ratios import calculate_roce

conn = sqlite3.connect("nifty100.db")

query = """
SELECT
    p.company_id,
    p.year,
    p.operating_profit,
    p.depreciation,
    b.equity_capital,
    b.reserves,
    b.borrowings
FROM profitandloss p
JOIN balancesheet b
ON p.company_id = b.company_id
AND p.year = b.year
"""

df = pd.read_sql(query, conn)

for _, row in df.iterrows():

    roce = calculate_roce(
        row["operating_profit"],
        row["depreciation"],
        row["equity_capital"],
        row["reserves"],
        row["borrowings"]
    )

    conn.execute(
        """
        UPDATE financial_ratios
        SET return_on_capital_employed_pct = ?
        WHERE company_id = ?
        AND year = ?
        """,
        (
            roce,
            row["company_id"],
            row["year"]
        )
    )

conn.commit()

print("ROCE population completed")

conn.close()