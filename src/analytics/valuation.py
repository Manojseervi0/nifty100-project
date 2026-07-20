import sqlite3
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "nifty100.db"
OUTPUT_DIR = PROJECT_ROOT / "output"

def main() -> None:
    """
    Build the latest valuation dataset and calculate FCF yield.
    """
    query = """
    WITH latest_market_cap AS (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY company_id
                ORDER BY year DESC, CAST(id AS INTEGER) DESC
            ) AS row_num
        FROM market_cap
    ),
    latest_ratios AS (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY company_id
                ORDER BY
                    CAST(SUBSTR(year, -4) AS INTEGER) DESC,
                    CAST(id AS INTEGER) DESC
            ) AS row_num
        FROM financial_ratios
        WHERE year != 'TTM'
    )
    SELECT
    c.id AS company_id,
    c.company_name,
    s.broad_sector AS sector,
    mc.year AS valuation_year,
    mc.market_cap_crore,
    mc.pe_ratio,
    mc.pb_ratio,
    mc.ev_ebitda,
    fr.free_cash_flow_cr
FROM companies c
LEFT JOIN latest_market_cap mc
    ON c.id = mc.company_id
   AND mc.row_num = 1
LEFT JOIN latest_ratios fr
    ON c.id = fr.company_id
   AND fr.row_num = 1
LEFT JOIN sectors s
    ON c.id = s.company_id
ORDER BY c.id
    """

    pe_history_query = """
    SELECT
        company_id,
        year,
        pe_ratio
    FROM market_cap
    WHERE pe_ratio IS NOT NULL
    ORDER BY company_id, year DESC
    """

    with sqlite3.connect(DB_PATH) as conn:
        valuation = pd.read_sql_query(query, conn)
        pe_history = pd.read_sql_query(
            pe_history_query,
            conn,
        )

    valuation["fcf_yield_pct"] = (
        valuation["free_cash_flow_cr"]
        / valuation["market_cap_crore"]
        * 100
    ).where(
        valuation["market_cap_crore"].notna()
        & valuation["market_cap_crore"].ne(0)
    )
    # Keep one P/E value per company and year
    pe_history = (
        pe_history
        .sort_values(
            ["company_id", "year"],
            ascending=[True, False],
        )
        .drop_duplicates(
            subset=["company_id", "year"],
            keep="last",
        )
    )

    # Use the latest 5 available years for each company
    five_year_pe = (
        pe_history
        .groupby("company_id", group_keys=False)
        .head(5)
    )

    five_year_median_pe = (
        five_year_pe
        .groupby("company_id")["pe_ratio"]
        .median()
    )

    valuation["5yr_median_PE"] = (
        valuation["company_id"]
        .map(five_year_median_pe)
    )

    # Latest P/E median within each broad sector
    valuation["sector_median_pe"] = (
        valuation
        .groupby("sector")["pe_ratio"]
        .transform("median")
    )

    # Calculate P/E difference from sector median
    valid_pe = (
        valuation["pe_ratio"].notna()
        & valuation["sector_median_pe"].notna()
        & valuation["sector_median_pe"].ne(0)
    )

    valuation["PE_vs_sector_median_pct"] = (
        (
            valuation["pe_ratio"]
            - valuation["sector_median_pe"]
        )
        / valuation["sector_median_pe"]
        * 100
    ).where(valid_pe)

    # Apply valuation flags
    valuation["flag"] = pd.NA

    valuation.loc[
        valid_pe
        & (
            valuation["pe_ratio"]
            > valuation["sector_median_pe"] * 1.5
        ),
        "flag",
    ] = "Caution"

    valuation.loc[
        valid_pe
        & (
            valuation["pe_ratio"]
            < valuation["sector_median_pe"] * 0.7
        ),
        "flag",
    ] = "Discount"

    valuation.loc[
        valid_pe & valuation["flag"].isna(),
        "flag",
    ] = "Fair"
# ----------------------------------
# Generate Valuation Output Files
# ----------------------------------

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    valuation_summary = valuation[
        [
            "company_id",
            "company_name",
            "sector",
            "pe_ratio",
            "pb_ratio",
            "ev_ebitda",
            "fcf_yield_pct",
            "5yr_median_PE",
            "PE_vs_sector_median_pct",
            "flag",
        ]
    ].copy()

    valuation_summary = valuation_summary.rename(
        columns={
            "pe_ratio": "P/E",
            "pb_ratio": "P/B",
            "ev_ebitda": "EV/EBITDA",
        }
    )

    summary_path = OUTPUT_DIR / "valuation_summary.xlsx"

    valuation_summary.to_excel(
        summary_path,
        index=False,
    )

    valuation_flags = valuation_summary[
        valuation_summary["flag"].isin(
            ["Caution", "Discount"]
        )
    ].copy()

    flags_path = OUTPUT_DIR / "valuation_flags.csv"

    valuation_flags.to_csv(
        flags_path,
        index=False,
    )
    print(f"Rows: {len(valuation)}")
    print(
        "Unique companies:",
        valuation["company_id"].nunique(),
    )
    print(
        "Missing FCF yield:",
        valuation["fcf_yield_pct"].isna().sum(),
    )

    print(
        valuation[
            [
                "company_id",
                "market_cap_crore",
                "free_cash_flow_cr",
                "fcf_yield_pct",
            ]
        ].head(10)
    )

    print(
        "Missing 5yr Median P/E:",
        valuation["5yr_median_PE"].isna().sum(),
    )

    print(
        "Missing Sector Median P/E:",
        valuation["sector_median_pe"].isna().sum(),
    )

    print(
        valuation[
            [
                "company_id",
                "pe_ratio",
                "5yr_median_PE",
                "sector_median_pe",
            ]
        ].head(10)
    )

    print(
        "Missing PE vs Sector Median:",
        valuation["PE_vs_sector_median_pct"].isna().sum(),
    )

    print(
        "Missing Flags:",
        valuation["flag"].isna().sum(),
    )

    print("\nFlag Counts:")
    print(
        valuation["flag"]
        .value_counts(dropna=False)
    )

    print(
        valuation[
            [
                "company_id",
                "pe_ratio",
                "sector_median_pe",
                "PE_vs_sector_median_pct",
                "flag",
            ]
        ].head(10)
    )

    print(
        "\nValuation summary rows:",
        len(valuation_summary),
    )

    print(
        "Valuation flags rows:",
        len(valuation_flags),
    )

    print(
        "Summary file:",
        summary_path,
    )

    print(
        "Flags file:",
        flags_path,
    )

if __name__ == "__main__":
    main()