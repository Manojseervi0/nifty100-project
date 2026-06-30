import sqlite3

conn = sqlite3.connect("nifty100.db")
cur = conn.cursor()

columns = [
    "revenue_cagr_5yr REAL",
    "pat_cagr_5yr REAL",
    "eps_cagr_5yr REAL",
    "composite_quality_score REAL"
]

for column in columns:
    try:
        cur.execute(
            f"ALTER TABLE financial_ratios ADD COLUMN {column}"
        )
        print(f"Added: {column}")
    except Exception as e:
        print(f"Skipped: {column} -> {e}")

conn.commit()
conn.close()

print("Done")