import sqlite3
import pandas as pd

from cagr import calculate_cagr
conn = sqlite3.connect("nifty100.db")

pnl = pd.read_sql("""
SELECT company_id, year, net_profit
FROM profitandloss
ORDER BY company_id, year
""", conn)

for company_id, group in pnl.groupby("company_id"):

    group = group.sort_values("year").reset_index(drop=True)

    for i in range(len(group)):

        if i < 5:
            continue

        current_year = group.loc[i, "year"]
        end_pat = group.loc[i, "net_profit"]
        start_pat = group.loc[i - 5, "net_profit"]

        cagr_value, flag = calculate_cagr(
            start_pat,
            end_pat,
            5
        )

        conn.execute(
            """
            UPDATE financial_ratios
            SET pat_cagr_5yr = ?,
                pat_cagr_5yr_flag = ?
            WHERE company_id = ?
              AND year = ?
            """,
            (
                cagr_value,
                flag,
                company_id,
                current_year
            )
        )

conn.commit()

print("PAT CAGR population completed")

conn.close()