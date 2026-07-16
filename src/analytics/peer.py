import sqlite3

import pandas as pd

DB_PATH = "nifty100.db"


def load_peer_data() -> pd.DataFrame:
    """
    Load peer groups joined with financial ratios.
    """

    conn = sqlite3.connect(DB_PATH)

    query = """
    SELECT

        pg.peer_group_name,
        pg.company_id,
        pg.is_benchmark,

        fr.year,

        fr.return_on_equity_pct,
        fr.return_on_capital_employed_pct,
        fr.net_profit_margin_pct,
        fr.debt_to_equity,
        fr.free_cash_flow_cr,
        fr.revenue_cagr_5yr,
        fr.pat_cagr_5yr,
        fr.eps_cagr_5yr,
        fr.interest_coverage,
        fr.asset_turnover,
        fr.composite_quality_score

    FROM peer_groups pg

    LEFT JOIN financial_ratios fr

        ON pg.company_id = fr.company_id
    """

    df = pd.read_sql(query, conn)

    conn.close()

    return df

RANK_METRICS = {
    "return_on_equity_pct": False,
    "return_on_capital_employed_pct": False,
    "net_profit_margin_pct": False,
    "debt_to_equity": True,          # inverse ranking
    "free_cash_flow_cr": False,
    "revenue_cagr_5yr": False,
    "pat_cagr_5yr": False,
    "eps_cagr_5yr": False,
    "interest_coverage": False,
    "asset_turnover": False,
}


def compute_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute percentile rank for each metric within each peer group.
    """

    results = []

    for peer_group, group in df.groupby("peer_group_name"):

        for metric, inverse in RANK_METRICS.items():

            temp = group.copy()

            temp = temp.dropna(subset=[metric])

            if temp.empty:
                continue

            # Compute percentile so that higher value = higher percentile
            temp["percentile_rank"] = temp[metric].rank(
                pct=True,
                ascending=True
            )

            # For Debt-to-Equity only, lower is better
            if inverse:
                temp["percentile_rank"] = (
                    1 - temp["percentile_rank"]
                )

            temp["metric"] = metric

            temp["value"] = temp[metric]

            results.append(

                temp[
                    [
                        "company_id",
                        "peer_group_name",
                        "year",
                        "metric",
                        "value",
                        "percentile_rank",
                        "is_benchmark",
                    ]
                ]

            )

    return pd.concat(
        results,
        ignore_index=True
    )

def save_peer_percentiles(df: pd.DataFrame):
    """
    Save peer percentile rankings into SQLite.
    """

    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS peer_percentiles (

        company_id TEXT,

        peer_group_name TEXT,

        metric TEXT,

        value REAL,

        percentile_rank REAL,

        year INTEGER,

        is_benchmark INTEGER
    )
    """)

    conn.execute("DELETE FROM peer_percentiles")

    df.to_sql(
        "peer_percentiles",
        conn,
        if_exists="append",
        index=False
    )

    conn.commit()

    conn.close()

    print("peer_percentiles table populated.")