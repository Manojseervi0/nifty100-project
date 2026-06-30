import sqlite3

from analytics.cagr import calculate_cagr
from etl.normaliser import normalize_year

conn = sqlite3.connect("nifty100.db")
cur = conn.cursor()

cur.execute("""
SELECT DISTINCT company_id
FROM profitandloss
""")

companies = [row[0] for row in cur.fetchall()]
for company in companies:

    print("Processing:", company)

    cur.execute("""
    SELECT year, sales
    FROM profitandloss
    WHERE company_id = ?
    AND year != 'TTM'
    """, (company,))

    sales_by_year = {}

    for year, sales in cur.fetchall():
        sales_by_year[normalize_year(year)] = sales

    years = sorted(sales_by_year.keys())

    for year in years:
        start_year = year - 5

        if start_year not in sales_by_year:
            continue

        cagr, flag = calculate_cagr(
            sales_by_year[start_year],
            sales_by_year[year],
            5
        )

        # For now only print
        cur.execute("""
        UPDATE financial_ratios
        SET revenue_cagr_5yr = ?
        WHERE company_id = ?
        AND year LIKE ?
        """,
        (
            cagr,
            company,
            f"%{year}"
        ))
conn.commit()

print("Revenue CAGR population completed")
conn.close()