import sqlite3
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
REPORT_PATH = Path("reports") / "radar_charts"
REPORT_PATH.mkdir(parents=True, exist_ok=True)
DB_PATH = "nifty100.db"

def load_radar_data():
    """
    Load latest financial data for all companies.
    Companies without peer groups are retained.
    """

    conn = sqlite3.connect(DB_PATH)

    query = """
    SELECT

        fr.company_id,
        fr.year,

        pg.peer_group_name,
        pg.is_benchmark,

        fr.return_on_equity_pct,
        fr.return_on_capital_employed_pct,
        fr.net_profit_margin_pct,
        fr.debt_to_equity,
        fr.free_cash_flow_cr,
        fr.pat_cagr_5yr,
        fr.revenue_cagr_5yr,
        fr.composite_quality_score

    FROM financial_ratios fr

    LEFT JOIN peer_groups pg
        ON fr.company_id = pg.company_id
    """

    df = pd.read_sql(query, conn)

    conn.close()

    df = (
        df.sort_values("year")
          .drop_duplicates(
              subset="company_id",
              keep="last"
          )
    )

    return df

def generate_radar_chart(company_id: str):
    """
    Generate radar chart for one company.
    """

    df = load_radar_data()

    # Create FCF Score
    df["fcf_score"] = df["free_cash_flow_cr"].apply(
        lambda x: 100 if pd.notna(x) and x > 0 else 0
    )

    # Select company
    company = df[df["company_id"] == company_id]

    if company.empty:
        print(f"{company_id} not found.")
        return

    company = company.iloc[0]
    metrics = [
        "return_on_equity_pct",
        "return_on_capital_employed_pct",
        "net_profit_margin_pct",
        "debt_to_equity",
        "fcf_score",
        "pat_cagr_5yr",
        "revenue_cagr_5yr",
        "composite_quality_score",
    ]

    peer_group = company["peer_group_name"]

    # ---------- Reference ----------

    if pd.isna(peer_group):

        reference = df[metrics].mean()

        label = "Nifty100 Average"

    else:

        reference = (
            df[
                df["peer_group_name"] == peer_group
            ][metrics]
            .mean()
        )

        label = "Peer Average"

    company_values = (
        company[metrics]
        .fillna(0)
        .astype(float)
        .tolist()
    )

    reference_values = (
        reference
        .fillna(0)
        .astype(float)
        .tolist()
    )

    labels = [
        "ROE",
        "ROCE",
        "NPM",
        "D/E",
        "FCF",
        "PAT CAGR",
        "Revenue CAGR",
        "Score",
    ]

    angles = np.linspace(
        0,
        2 * np.pi,
        len(labels),
        endpoint=False
    ).tolist()

    company_values += company_values[:1]
    reference_values += reference_values[:1]
    angles += angles[:1]

    fig, ax = plt.subplots(
        figsize=(7, 7),
        subplot_kw=dict(polar=True)
    )

    ax.plot(
        angles,
        company_values,
        linewidth=2,
        label=company_id
    )

    ax.fill(
        angles,
        company_values,
        alpha=0.25
    )

    ax.plot(
        angles,
        reference_values,
        linestyle="--",
        linewidth=2,
        label=label
    )

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels)

    ax.set_title(company_id)

    ax.legend()

    plt.savefig(
        REPORT_PATH / f"{company_id}_radar.png",
        dpi=300,
        bbox_inches="tight"
    )

    plt.close()

    print(f"{company_id} radar generated.")

def generate_all_radar_charts():
    """
    Generate radar chart for every company.
    """

    df = load_radar_data()

    total = len(df)

    print(f"Generating {total} radar charts...\n")

    for i, company in enumerate(df["company_id"], start=1):

        generate_radar_chart(company)

        print(f"[{i}/{total}] Completed")

    print("\nAll radar charts generated successfully.")