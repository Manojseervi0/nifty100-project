import sqlite3
import pandas as pd

conn = sqlite3.connect("nifty100.db")

df = pd.read_sql("""
SELECT
    company_id,
    year,
    return_on_equity_pct,
    return_on_capital_employed_pct,
    debt_to_equity,
    free_cash_flow_cr
FROM financial_ratios
""", conn)

for _, row in df.iterrows():

    roe = row["return_on_equity_pct"] or 0
    roce = row["return_on_capital_employed_pct"] or 0
    fcf = row["free_cash_flow_cr"] or 0
    de = row["debt_to_equity"]

    roe_score = min(max(roe, 0), 100)

    roce_score = min(max(roce, 0), 100)

    fcf_score = 100 if fcf > 0 else 0

    if de is None:
        de_score = 0
    elif de <= 1:
        de_score = 100
    elif de <= 2:
        de_score = 70
    elif de <= 5:
        de_score = 40
    else:
        de_score = 0

    quality_score = round(
        (0.30 * roe_score) +
        (0.25 * fcf_score) +
        (0.25 * roce_score) +
        (0.20 * de_score),
        2
    )

    conn.execute(
        """
        UPDATE financial_ratios
        SET composite_quality_score = ?
        WHERE company_id = ?
        AND year = ?
        """,
        (
            quality_score,
            row["company_id"],
            row["year"]
        )
    )

conn.commit()

print("Composite Quality Score populated")

conn.close()