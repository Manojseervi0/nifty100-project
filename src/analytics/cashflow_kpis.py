from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "nifty100.db"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"


# ---------------------------------------------------------------------------
# Sprint 2-compatible KPI helper functions
# ---------------------------------------------------------------------------

def calculate_fcf(
    operating_activity,
    investing_activity,
):
    """Calculate Free Cash Flow using the project definition: CFO + CFI."""
    if pd.isna(operating_activity) or pd.isna(investing_activity):
        return None

    return float(operating_activity) + float(investing_activity)


def calculate_cfo_quality_score(
    cfo,
    pat,
):
    """
    Classify a single-year CFO/PAT ratio.

    Kept backward-compatible with the Sprint 2 implementation.
    """
    ratio = calculate_cfo_pat_ratio(cfo, pat)

    if ratio is None:
        return None

    return classify_cfo_quality(ratio)


def calculate_cfo_pat_ratio(
    cfo,
    pat,
):
    """Return CFO/PAT ratio, or None when the ratio cannot be calculated."""
    if pd.isna(cfo) or pd.isna(pat) or float(pat) == 0:
        return None

    return float(cfo) / float(pat)


def classify_cfo_quality(score):
    """Classify the 5-year average CFO/PAT score."""
    if score is None or pd.isna(score):
        return "Insufficient Data"

    if score > 1.0:
        return "High Quality"

    if score >= 0.5:
        return "Moderate"

    return "Accrual Risk"


def calculate_capex_intensity(
    investing_activity,
    sales,
):
    """
    Classify CapEx intensity.

    Kept backward-compatible with the Sprint 2 implementation.
    """
    intensity = calculate_capex_intensity_pct(
        investing_activity,
        sales,
    )

    if intensity is None:
        return None

    return classify_capex_intensity(intensity)


def calculate_capex_intensity_pct(
    investing_activity,
    sales,
):
    """Calculate CapEx intensity percentage using abs(CFI) / Sales * 100."""
    if (
        pd.isna(investing_activity)
        or pd.isna(sales)
        or float(sales) == 0
    ):
        return None

    return (
        abs(float(investing_activity))
        / abs(float(sales))
    ) * 100


def classify_capex_intensity(intensity):
    """Return the project CapEx intensity label."""
    if intensity is None or pd.isna(intensity):
        return "Insufficient Data"

    if intensity < 3:
        return "Asset Light"

    if intensity <= 8:
        return "Moderate"

    return "Capital Intensive"


def calculate_fcf_conversion(
    fcf,
    operating_profit,
):
    """Calculate FCF conversion rate as FCF / Operating Profit * 100."""
    if (
        fcf is None
        or pd.isna(fcf)
        or pd.isna(operating_profit)
        or float(operating_profit) == 0
    ):
        return None

    return round(
        (float(fcf) / float(operating_profit)) * 100,
        2,
    )


def classify_capital_allocation(
    cfo,
    cfi,
    cff,
    cfo_pat_ratio=None,
):
    """Classify the project's capital allocation pattern."""
    if any(pd.isna(value) for value in (cfo, cfi, cff)):
        return "Insufficient Data"

    signs = (
        "+" if float(cfo) >= 0 else "-",
        "+" if float(cfi) >= 0 else "-",
        "+" if float(cff) >= 0 else "-",
    )

    if signs == ("+", "-", "-"):
        if (
            cfo_pat_ratio is not None
            and not pd.isna(cfo_pat_ratio)
            and cfo_pat_ratio > 1
        ):
            return "Shareholder Returns"

        return "Reinvestor"

    if signs == ("+", "+", "-"):
        return "Liquidating Assets"

    if signs == ("-", "+", "+"):
        return "Distress Signal"

    if signs == ("-", "-", "+"):
        return "Growth Funded by Debt"

    if signs == ("+", "+", "+"):
        return "Cash Accumulator"

    if signs == ("-", "-", "-"):
        return "Pre-Revenue"

    if signs == ("+", "-", "+"):
        return "Mixed"

    # The Sprint 2 rule sheet does not define (-, +, -).
    return "Other"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def add_year_number(df: pd.DataFrame) -> pd.DataFrame:
    """Extract a four-digit year so mixed labels like Mar 2024 sort correctly."""
    result = df.copy()

    result["year_number"] = pd.to_numeric(
        result["year"]
        .astype(str)
        .str.extract(r"(\d{4})", expand=False),
        errors="coerce",
    )

    return result


def deduplicate_company_year(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Keep one record per company-year.

    Some source tables contain duplicate company-year rows. Keeping the last
    database row makes the Day 31 aggregation deterministic without multiplying
    rows during joins.
    """
    if df.empty:
        return df

    return (
        df.sort_values("_rowid")
        .drop_duplicates(
            subset=["company_id", "year"],
            keep="last",
        )
        .reset_index(drop=True)
    )


def load_project_data(
    conn: sqlite3.Connection,
):
    companies = pd.read_sql_query(
        """
        SELECT
            c.id AS company_id,
            c.company_name,
            s.broad_sector AS sector
        FROM companies AS c
        LEFT JOIN sectors AS s
            ON s.company_id = c.id
        ORDER BY c.id
        """,
        conn,
    )

    cashflow = pd.read_sql_query(
        """
        SELECT
            rowid AS _rowid,
            company_id,
            year,
            operating_activity,
            investing_activity,
            financing_activity,
            net_cash_flow
        FROM cashflow
        """,
        conn,
    )

    profit_loss = pd.read_sql_query(
        """
        SELECT
            rowid AS _rowid,
            company_id,
            year,
            sales,
            operating_profit,
            net_profit
        FROM profitandloss
        """,
        conn,
    )

    balance_sheet = pd.read_sql_query(
        """
        SELECT
            rowid AS _rowid,
            company_id,
            year,
            borrowings
        FROM balancesheet
        """,
        conn,
    )

    cashflow = deduplicate_company_year(cashflow)
    profit_loss = deduplicate_company_year(profit_loss)
    balance_sheet = deduplicate_company_year(balance_sheet)

    return (
        companies,
        add_year_number(cashflow),
        add_year_number(profit_loss),
        add_year_number(balance_sheet),
    )


def select_latest_record(
    df: pd.DataFrame,
    company_id: str,
):
    company_df = df[
        df["company_id"] == company_id
    ].copy()

    company_df = company_df.dropna(
        subset=["year_number"]
    )

    if company_df.empty:
        return None

    company_df = company_df.sort_values(
        ["year_number", "_rowid"],
        ascending=[False, False],
    )

    return company_df.iloc[0]


def find_matching_year_record(
    df: pd.DataFrame,
    company_id: str,
    year_number,
):
    if pd.isna(year_number):
        return None

    rows = df[
        (df["company_id"] == company_id)
        & (df["year_number"] == year_number)
    ].copy()

    if rows.empty:
        return None

    return rows.sort_values(
        "_rowid",
        ascending=False,
    ).iloc[0]


def get_previous_borrowings(
    balance_sheet: pd.DataFrame,
    company_id: str,
    latest_year_number,
):
    rows = balance_sheet[
        (balance_sheet["company_id"] == company_id)
        & balance_sheet["year_number"].notna()
        & (
            balance_sheet["year_number"]
            < latest_year_number
        )
    ].copy()

    if rows.empty:
        return None

    rows = rows.sort_values(
        ["year_number", "_rowid"],
        ascending=[False, False],
    )

    value = rows.iloc[0]["borrowings"]

    if pd.isna(value):
        return None

    return float(value)


# ---------------------------------------------------------------------------
# Day 31 calculations
# ---------------------------------------------------------------------------

def calculate_five_year_cfo_quality(
    company_cashflow: pd.DataFrame,
    profit_loss: pd.DataFrame,
    company_id: str,
):
    """
    Calculate the average CFO/PAT ratio over the latest five available
    company cash-flow years for which matching PAT exists.
    """
    rows = (
        company_cashflow
        .dropna(subset=["year_number"])
        .sort_values(
            ["year_number", "_rowid"],
            ascending=[False, False],
        )
        .head(5)
    )

    ratios = []

    for _, cf_row in rows.iterrows():
        pl_row = find_matching_year_record(
            profit_loss,
            company_id,
            cf_row["year_number"],
        )

        if pl_row is None:
            continue

        ratio = calculate_cfo_pat_ratio(
            cf_row["operating_activity"],
            pl_row["net_profit"],
        )

        if ratio is not None and np.isfinite(ratio):
            ratios.append(ratio)

    if not ratios:
        return None

    return round(float(np.mean(ratios)), 4)


def calculate_fcf_cagr_5yr(
    company_cashflow: pd.DataFrame,
):
    """
    Calculate 5-year FCF CAGR using the latest year and a record five years
    earlier. CAGR is only mathematically meaningful here when both FCF values
    are positive.
    """
    rows = (
        company_cashflow
        .dropna(subset=["year_number"])
        .sort_values(
            ["year_number", "_rowid"],
            ascending=[False, False],
        )
        .drop_duplicates(
            subset=["year_number"],
            keep="first",
        )
    )

    if rows.empty:
        return None

    latest = rows.iloc[0]
    target_year = latest["year_number"] - 5

    base_rows = rows[
        rows["year_number"] == target_year
    ]

    if base_rows.empty:
        return None

    base = base_rows.iloc[0]

    latest_fcf = calculate_fcf(
        latest["operating_activity"],
        latest["investing_activity"],
    )

    base_fcf = calculate_fcf(
        base["operating_activity"],
        base["investing_activity"],
    )

    if (
        latest_fcf is None
        or base_fcf is None
        or base_fcf <= 0
        or latest_fcf <= 0
    ):
        return None

    cagr = (
        (latest_fcf / base_fcf) ** (1 / 5)
        - 1
    ) * 100

    return round(float(cagr), 2)


def build_cashflow_intelligence(
    companies: pd.DataFrame,
    cashflow: pd.DataFrame,
    profit_loss: pd.DataFrame,
    balance_sheet: pd.DataFrame,
):
    intelligence_rows = []
    distress_rows = []

    for _, company in companies.iterrows():
        company_id = company["company_id"]
        company_name = company["company_name"]
        sector = company["sector"]

        company_cf = cashflow[
            cashflow["company_id"] == company_id
        ].copy()

        latest_cf = select_latest_record(
            cashflow,
            company_id,
        )

        # Preserve the full 92-company universe even when cash-flow data is absent.
        if latest_cf is None:
            intelligence_rows.append(
                {
                    "company_id": company_id,
                    "sector": sector,
                    "cfo_quality_score": None,
                    "cfo_quality_label": "Insufficient Data",
                    "capex_intensity_pct": None,
                    "capex_label": "Insufficient Data",
                    "fcf_cagr_5yr": None,
                    "fcf_conversion_pct": None,
                    "distress_flag": False,
                    "deleveraging_flag": False,
                    "capital_allocation_label": "Insufficient Data",
                }
            )
            continue

        latest_year = latest_cf["year_number"]

        latest_pl = find_matching_year_record(
            profit_loss,
            company_id,
            latest_year,
        )

        latest_bs = find_matching_year_record(
            balance_sheet,
            company_id,
            latest_year,
        )

        cfo = latest_cf["operating_activity"]
        cfi = latest_cf["investing_activity"]
        cff = latest_cf["financing_activity"]

        latest_pat = (
            latest_pl["net_profit"]
            if latest_pl is not None
            else None
        )

        latest_sales = (
            latest_pl["sales"]
            if latest_pl is not None
            else None
        )

        latest_operating_profit = (
            latest_pl["operating_profit"]
            if latest_pl is not None
            else None
        )

        latest_cfo_pat_ratio = (
            calculate_cfo_pat_ratio(
                cfo,
                latest_pat,
            )
        )

        cfo_quality_score = (
            calculate_five_year_cfo_quality(
                company_cf,
                profit_loss,
                company_id,
            )
        )

        cfo_quality_label = (
            classify_cfo_quality(
                cfo_quality_score,
            )
        )

        capex_intensity_pct = (
            calculate_capex_intensity_pct(
                cfi,
                latest_sales,
            )
        )

        capex_label = (
            classify_capex_intensity(
                capex_intensity_pct,
            )
        )

        latest_fcf = calculate_fcf(
            cfo,
            cfi,
        )

        fcf_conversion_pct = (
            calculate_fcf_conversion(
                latest_fcf,
                latest_operating_profit,
            )
        )

        fcf_cagr_5yr = (
            calculate_fcf_cagr_5yr(
                company_cf,
            )
        )

        distress_flag = bool(
            pd.notna(cfo)
            and pd.notna(cff)
            and float(cfo) < 0
            and float(cff) > 0
        )

        deleveraging_flag = False

        if (
            latest_bs is not None
            and pd.notna(latest_bs["borrowings"])
            and pd.notna(cff)
            and float(cff) < 0
        ):
            previous_borrowings = (
                get_previous_borrowings(
                    balance_sheet,
                    company_id,
                    latest_year,
                )
            )

            if previous_borrowings is not None:
                deleveraging_flag = bool(
                    float(latest_bs["borrowings"])
                    < previous_borrowings
                )

        capital_allocation_label = (
            classify_capital_allocation(
                cfo,
                cfi,
                cff,
                latest_cfo_pat_ratio,
            )
        )

        intelligence_rows.append(
            {
                "company_id": company_id,
                "sector": sector,
                "cfo_quality_score": cfo_quality_score,
                "cfo_quality_label": cfo_quality_label,
                "capex_intensity_pct": (
                    round(capex_intensity_pct, 2)
                    if capex_intensity_pct is not None
                    else None
                ),
                "capex_label": capex_label,
                "fcf_cagr_5yr": fcf_cagr_5yr,
                "fcf_conversion_pct": fcf_conversion_pct,
                "distress_flag": distress_flag,
                "deleveraging_flag": deleveraging_flag,
                "capital_allocation_label": capital_allocation_label,
            }
        )

        if distress_flag:
            distress_rows.append(
                {
                    "company_id": company_id,
                    "company_name": company_name,
                    "sector": sector,
                    "year": latest_cf["year"],
                    "cfo_value": cfo,
                    "cff_value": cff,
                    "latest_net_profit": latest_pat,
                }
            )

    intelligence_df = pd.DataFrame(intelligence_rows)
    distress_df = pd.DataFrame(
        distress_rows,
        columns=[
            "company_id",
            "company_name",
            "sector",
            "year",
            "cfo_value",
            "cff_value",
            "latest_net_profit",
        ],
    )

    return intelligence_df, distress_df


def run_cashflow_intelligence(
    db_path: Path,
    output_dir: Path,
):
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sqlite3.connect(db_path) as conn:
        (
            companies,
            cashflow,
            profit_loss,
            balance_sheet,
        ) = load_project_data(conn)

    intelligence_df, distress_df = (
        build_cashflow_intelligence(
            companies,
            cashflow,
            profit_loss,
            balance_sheet,
        )
    )

    intelligence_path = (
        output_dir
        / "cashflow_intelligence.xlsx"
    )

    distress_path = (
        output_dir
        / "distress_alerts.csv"
    )

    intelligence_df.to_excel(
        intelligence_path,
        index=False,
        engine="openpyxl",
    )

    distress_df.to_csv(
        distress_path,
        index=False,
    )

    missing_cashflow_count = int(
        (
            intelligence_df[
                "capital_allocation_label"
            ]
            == "Insufficient Data"
        ).sum()
    )

    print("=" * 68)
    print(
        "DAY 31 - CASH FLOW INTELLIGENCE MODULE COMPLETE"
    )
    print("=" * 68)
    print(
        f"Companies processed        : "
        f"{len(intelligence_df)}"
    )
    print(
        f"Distress alerts            : "
        f"{len(distress_df)}"
    )
    print(
        f"Deleveraging companies     : "
        f"{int(intelligence_df['deleveraging_flag'].sum())}"
    )
    print(
        f"Missing cash-flow cases    : "
        f"{missing_cashflow_count}"
    )
    print()
    print(
        f"Generated: {intelligence_path}"
    )
    print(
        f"Generated: {distress_path}"
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate Sprint 5 Day 31 "
            "cash-flow intelligence outputs."
        )
    )

    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    args = parser.parse_args()

    run_cashflow_intelligence(
        args.db,
        args.output_dir,
    )


if __name__ == "__main__":
    main()