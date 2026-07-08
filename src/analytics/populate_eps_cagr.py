import sqlite3
import pandas as pd

from cagr import calculate_cagr

conn = sqlite3.connect("nifty100.db")

pnl = pd.read_sql("""
SELECT company_id, year, eps
FROM profitandloss
ORDER BY company_id, year
""", conn)

for company_id, group in pnl.groupby("company_id"):

    group = group.sort_values("year").reset_index(drop=True)

    for i in range(len(group)):

        if i < 5:
            continue

        current_year = group.loc[i, "year"]
        end_eps = group.loc[i, "eps"]
        start_eps = group.loc[i - 5, "eps"]

        cagr_value, flag = calculate_cagr(
            start_eps,
            end_eps,
            5
        )

        conn.execute(
            """
            UPDATE financial_ratios
            SET eps_cagr_5yr = ?,
                eps_cagr_5yr_flag = ?
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

print("EPS CAGR population completed")

conn.close()