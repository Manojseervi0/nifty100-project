from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "nifty100.db"
OUTPUT_PATH = ROOT / "output" / "cashflow_intelligence.csv"


def extract_year(value: object) -> int | None:
    """Extract a four-digit year from an annual period label."""

    match = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return int(match.group()) if match else None


def classify_row(row: pd.Series) -> pd.Series:
    """Create analyst-friendly cash-flow classifications."""

    cfo = row.get("cash_from_operations_cr")
    capex = row.get("capex_cr")
    fcf = row.get("free_cash_flow_cr")

    if pd.isna(cfo):
        cfo_quality = "Unavailable"
    elif cfo > 0:
        cfo_quality = "Positive"
    elif cfo == 0:
        cfo_quality = "Neutral"
    else:
        cfo_quality = "Negative"

    if pd.isna(fcf):
        fcf_status = "Unavailable"
    elif fcf > 0:
        fcf_status = "Positive"
    elif fcf == 0:
        fcf_status = "Neutral"
    else:
        fcf_status = "Negative"

    if pd.isna(cfo) or cfo == 0 or pd.isna(capex):
        capex_intensity_pct = np.nan
        capex_band = "Unavailable"
    else:
        capex_intensity_pct = abs(float(capex)) / abs(float(cfo)) * 100
        if capex_intensity_pct < 25:
            capex_band = "Asset Light"
        elif capex_intensity_pct <= 60:
            capex_band = "Moderate"
        else:
            capex_band = "Capital Intensive"

    if cfo_quality == "Positive" and fcf_status == "Positive":
        signal = "Healthy"
    elif cfo_quality == "Positive":
        signal = "Watch"
    elif cfo_quality == "Unavailable":
        signal = "Insufficient Data"
    else:
        signal = "Risk"

    return pd.Series(
        {
            "cfo_quality": cfo_quality,
            "fcf_status": fcf_status,
            "capex_intensity_pct": capex_intensity_pct,
            "capex_band": capex_band,
            "cashflow_signal": signal,
        }
    )


def main() -> None:
    """Generate one latest-year cash-flow intelligence row per company."""

    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as connection:
        companies = pd.read_sql_query(
            """
            SELECT
                id AS company_id,
                company_name
            FROM companies
            ORDER BY id
            """,
            connection,
        )

        ratios = pd.read_sql_query(
            """
            SELECT
                company_id,
                year,
                cash_from_operations_cr,
                capex_cr,
                free_cash_flow_cr
            FROM financial_ratios
            """,
            connection,
        )

    ratios["year_number"] = ratios["year"].map(extract_year)
    ratios = ratios[ratios["year_number"].notna()].copy()

    for column in (
        "cash_from_operations_cr",
        "capex_cr",
        "free_cash_flow_cr",
    ):
        ratios[column] = pd.to_numeric(
            ratios[column],
            errors="coerce",
        )

    latest = (
        ratios.sort_values(
            ["company_id", "year_number"],
            ascending=[True, False],
        )
        .drop_duplicates("company_id", keep="first")
        .copy()
    )

    latest = latest[
        [
            "company_id",
            "year",
            "year_number",
            "cash_from_operations_cr",
            "capex_cr",
            "free_cash_flow_cr",
        ]
    ]

    output = companies.merge(
        latest,
        on="company_id",
        how="left",
        validate="one_to_one",
    )

    intelligence = output.apply(classify_row, axis=1)
    output = pd.concat([output, intelligence], axis=1)

    output = output[
        [
            "company_id",
            "company_name",
            "year",
            "cash_from_operations_cr",
            "capex_cr",
            "free_cash_flow_cr",
            "cfo_quality",
            "fcf_status",
            "capex_intensity_pct",
            "capex_band",
            "cashflow_signal",
        ]
    ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(OUTPUT_PATH, index=False)

    unique_companies = output["company_id"].nunique()
    print(f"Created: {OUTPUT_PATH.relative_to(ROOT)}")
    print(f"Rows: {len(output)}")
    print(f"Unique companies: {unique_companies}")
    print(
        "Status:",
        "PASS"
        if len(output) == 92 and unique_companies == 92
        else "FAIL",
    )


if __name__ == "__main__":
    main()
