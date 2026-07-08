import sqlite3

conn = sqlite3.connect("nifty100.db")
cur = conn.cursor()

log_lines = []

# PAT CAGR flags
cur.execute("""
SELECT company_id, year, pat_cagr_5yr_flag
FROM financial_ratios
WHERE pat_cagr_5yr_flag IS NOT NULL
AND pat_cagr_5yr_flag != 'NORMAL'
""")

for company_id, year, flag in cur.fetchall():
    log_lines.append(
        f"{company_id} | {year} | PAT CAGR | {flag}"
    )

# EPS CAGR flags
cur.execute("""
SELECT company_id, year, eps_cagr_5yr_flag
FROM financial_ratios
WHERE eps_cagr_5yr_flag IS NOT NULL
AND eps_cagr_5yr_flag != 'NORMAL'
""")

for company_id, year, flag in cur.fetchall():
    log_lines.append(
        f"{company_id} | {year} | EPS CAGR | {flag}"
    )

with open(
    "output/ratio_edge_cases.log",
    "w",
    encoding="utf-8"
) as f:

    for line in log_lines:
        f.write(line + "\n")

print(
    f"ratio_edge_cases.log generated with {len(log_lines)} entries"
)

conn.close()