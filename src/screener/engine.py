import sqlite3
from pathlib import Path

import pandas as pd
import yaml

CONFIG_PATH = Path("config") / "screener_config.yaml"
DB_PATH = Path("nifty100.db")


def load_config() -> dict:
    """
    Load screener configuration from YAML file.
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_financial_ratios() -> pd.DataFrame:
    """
    Load the financial_ratios table from the SQLite database.
    """
    conn = sqlite3.connect(DB_PATH)

    try:
        df = pd.read_sql_query(
            "SELECT * FROM financial_ratios",
            conn
        )
    finally:
        conn.close()

    return df


def load_screener_data() -> pd.DataFrame:
    """
    Load all data required for the screener.

    Notes
    -----
    `fr.year` is stored as a text label such as "Mar 2019" or
    "Dec 2023". The trailing 4 characters are cast to an integer
    (`year_numeric`) so the calling code can reliably determine the
    most recent fiscal year per company. Sorting on the raw text
    column is unsafe: e.g. "Dec 2023" < "Mar 2019" alphabetically,
    since 'D' < 'M', which silently picks the wrong year.

    When the `market_cap` join produces more than one candidate row
    for the same (company_id, year) pair, rows with a non-null
    `pe_ratio` are ordered first so that the subsequent
    `drop_duplicates(keep="first")` prefers the row that actually
    carries valuation data.
    """

    conn = sqlite3.connect(DB_PATH)

    query = """
    SELECT
        fr.company_id,
        c.company_name,
        fr.year,
        CAST(SUBSTR(fr.year, -4) AS INTEGER) AS year_numeric,

        fr.return_on_equity_pct,
        fr.return_on_capital_employed_pct,
        fr.net_profit_margin_pct,
        fr.operating_profit_margin_pct,
        fr.debt_to_equity,
        fr.interest_coverage,
        fr.asset_turnover,
        fr.free_cash_flow_cr,
        fr.revenue_cagr_5yr,
        fr.pat_cagr_5yr,
        fr.eps_cagr_5yr,
        fr.composite_quality_score,
        fr.dividend_payout_ratio_pct,

        mc.market_cap_crore,
        mc.pe_ratio,
        mc.pb_ratio,
        mc.dividend_yield_pct,

        pl.sales,
        pl.net_profit,
        pl.dividend_payout,

        s.broad_sector

    FROM financial_ratios fr

    LEFT JOIN companies c
        ON fr.company_id = c.id

    LEFT JOIN market_cap mc
        ON fr.company_id = mc.company_id
       AND CAST(SUBSTR(fr.year, -4) AS INTEGER) = mc.year

    LEFT JOIN profitandloss pl
        ON fr.company_id = pl.company_id
       AND fr.year = pl.year

    LEFT JOIN sectors s
        ON fr.company_id = s.company_id

    ORDER BY
        fr.company_id,
        year_numeric,
        (mc.pe_ratio IS NULL)
    """

    df = pd.read_sql_query(query, conn)

    conn.close()

    df = df.drop_duplicates(
        subset=["company_id", "year"],
        keep="first"
    )

    return df


def get_latest_year_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return exactly one row per company: the row for that company's
    most recent fiscal year.

    Requires a numeric year column (`year_numeric`) to sort on. If
    it's not already present (e.g. the DataFrame came from
    somewhere other than `load_screener_data`), it's derived from
    the last 4 digits of the `year` text column.

    This must be used instead of `df.sort_values("year")` — the raw
    `year` column ("Mar 2019", "Dec 2023", ...) does not sort
    chronologically as a string.
    """

    if "year_numeric" not in df.columns:
        df = df.copy()
        df["year_numeric"] = (
            df["year"]
            .astype(str)
            .str.extract(r"(\d{4})")
            .astype(int)
        )

    return (
        df.sort_values("year_numeric")
          .drop_duplicates(subset="company_id", keep="last")
          .reset_index(drop=True)
    )


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """
    Apply dynamic screener filters to the financial ratios DataFrame.
    Filters are combined with AND semantics; a filter key with a
    value of None is ignored (not applied).
    """

    result = df.copy()

    # ---------------------------------------------------------
    # Profitability Filters
    # ---------------------------------------------------------

    if filters.get("min_roe") is not None:
        result = result[
            result["return_on_equity_pct"] >= filters["min_roe"]
        ]

    if filters.get("min_opm") is not None:
        result = result[
            result["operating_profit_margin_pct"] >=
            filters["min_opm"]
        ]

    # ---------------------------------------------------------
    # Leverage Filters
    # ---------------------------------------------------------

    if filters.get("max_de") is not None:
        result = result[
            (result["broad_sector"] == "Financials")
            | (result["debt_to_equity"] <= filters["max_de"])
        ]

    if filters.get("min_icr") is not None:
        icr = result["interest_coverage"].fillna(float("inf"))
        result = result[icr >= filters["min_icr"]]

    # ---------------------------------------------------------
    # Cash Flow Filters
    # ---------------------------------------------------------

    if filters.get("min_fcf") is not None:
        result = result[
            result["free_cash_flow_cr"] >= filters["min_fcf"]
        ]

    # ---------------------------------------------------------
    # Growth Filters
    # ---------------------------------------------------------

    if filters.get("min_revenue_cagr_5yr") is not None:
        result = result[
            result["revenue_cagr_5yr"] >=
            filters["min_revenue_cagr_5yr"]
        ]

    if filters.get("min_pat_cagr_5yr") is not None:
        result = result[
            result["pat_cagr_5yr"] >= filters["min_pat_cagr_5yr"]
        ]

    if filters.get("min_eps_cagr_5yr") is not None:
        result = result[
            result["eps_cagr_5yr"] >= filters["min_eps_cagr_5yr"]
        ]

    # ---------------------------------------------------------
    # Valuation Filters
    # ---------------------------------------------------------

    if filters.get("max_pe") is not None:
        result = result[
            result["pe_ratio"].notna()
            & (result["pe_ratio"] <= filters["max_pe"])
        ]

    if filters.get("max_pb") is not None:
        result = result[
            result["pb_ratio"] <= filters["max_pb"]
        ]

    if filters.get("min_dividend_yield") is not None:
        result = result[
            result["dividend_yield_pct"] >=
            filters["min_dividend_yield"]
        ]

    # ---------------------------------------------------------
    # Size Filters
    # ---------------------------------------------------------

    if filters.get("min_market_cap") is not None:
        result = result[
            result["market_cap_crore"] >= filters["min_market_cap"]
        ]

    if filters.get("min_sales") is not None:
        result = result[
            result["sales"] >= filters["min_sales"]
        ]

    if filters.get("min_net_profit") is not None:
        result = result[
            result["net_profit"] >= filters["min_net_profit"]
        ]

    # ---------------------------------------------------------
    # Efficiency Filters
    # ---------------------------------------------------------

    if filters.get("min_asset_turnover") is not None:
        result = result[
            result["asset_turnover"] >= filters["min_asset_turnover"]
        ]

    return result.sort_values(
        by="composite_quality_score",
        ascending=False
    ).reset_index(drop=True)


def get_filter_pass_counts(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """
    Diagnostic helper: for each active filter, report how many rows
    of `df` satisfy that filter ON ITS OWN (independent of the
    others), versus how many satisfy it as part of the full chained
    AND. Used by the UI to explain an empty result set instead of
    just showing a blank table.

    Returns a DataFrame with columns: filter, threshold,
    passes_alone, passes_in_combination, total_rows.
    """

    total = len(df)

    single_checks = {}

    if filters.get("min_roe") is not None:
        single_checks["min_roe"] = (
            df["return_on_equity_pct"] >= filters["min_roe"]
        )
    if filters.get("min_opm") is not None:
        single_checks["min_opm"] = (
            df["operating_profit_margin_pct"] >= filters["min_opm"]
        )
    if filters.get("max_de") is not None:
        single_checks["max_de"] = (
            (df["broad_sector"] == "Financials")
            | (df["debt_to_equity"] <= filters["max_de"])
        )
    if filters.get("min_icr") is not None:
        single_checks["min_icr"] = (
            df["interest_coverage"].fillna(float("inf"))
            >= filters["min_icr"]
        )
    if filters.get("min_fcf") is not None:
        single_checks["min_fcf"] = (
            df["free_cash_flow_cr"] >= filters["min_fcf"]
        )
    if filters.get("min_revenue_cagr_5yr") is not None:
        single_checks["min_revenue_cagr_5yr"] = (
            df["revenue_cagr_5yr"] >= filters["min_revenue_cagr_5yr"]
        )
    if filters.get("min_pat_cagr_5yr") is not None:
        single_checks["min_pat_cagr_5yr"] = (
            df["pat_cagr_5yr"] >= filters["min_pat_cagr_5yr"]
        )
    if filters.get("min_eps_cagr_5yr") is not None:
        single_checks["min_eps_cagr_5yr"] = (
            df["eps_cagr_5yr"] >= filters["min_eps_cagr_5yr"]
        )
    if filters.get("max_pe") is not None:
        single_checks["max_pe"] = (
            df["pe_ratio"].notna() & (df["pe_ratio"] <= filters["max_pe"])
        )
    if filters.get("max_pb") is not None:
        single_checks["max_pb"] = df["pb_ratio"] <= filters["max_pb"]
    if filters.get("min_dividend_yield") is not None:
        single_checks["min_dividend_yield"] = (
            df["dividend_yield_pct"] >= filters["min_dividend_yield"]
        )
    if filters.get("min_market_cap") is not None:
        single_checks["min_market_cap"] = (
            df["market_cap_crore"] >= filters["min_market_cap"]
        )
    if filters.get("min_sales") is not None:
        single_checks["min_sales"] = df["sales"] >= filters["min_sales"]
    if filters.get("min_net_profit") is not None:
        single_checks["min_net_profit"] = (
            df["net_profit"] >= filters["min_net_profit"]
        )
    if filters.get("min_asset_turnover") is not None:
        single_checks["min_asset_turnover"] = (
            df["asset_turnover"] >= filters["min_asset_turnover"]
        )

    rows = []
    combined = pd.Series(True, index=df.index)

    for name, mask in single_checks.items():
        combined = combined & mask
        rows.append({
            "filter": name,
            "threshold": filters[name],
            "passes_alone": int(mask.sum()),
            "passes_in_combination": int(combined.sum()),
            "total_rows": total,
        })

    return pd.DataFrame(rows)


def run_preset(df: pd.DataFrame, preset_name: str) -> pd.DataFrame:
    """
    Run one predefined screener preset.
    """

    config = load_config()
    presets = config.get("presets", {})

    if preset_name not in presets:
        raise ValueError(f"Unknown preset: {preset_name}")

    filters = presets[preset_name]

    return apply_filters(df, filters)


def run_all_presets(df: pd.DataFrame) -> dict:
    """
    Run all screener presets.
    """

    config = load_config()
    results = {}

    for preset in config["presets"]:
        results[preset] = run_preset(df, preset)

    return results


def normalize_sector_scores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize composite quality scores within each sector
    to a 0-100 scale.
    """

    result = df.copy()

    result["sector_quality_score"] = (
        result
        .groupby("broad_sector")["composite_quality_score"]
        .transform(
            lambda x: (
                (x - x.min()) / (x.max() - x.min()) * 100
            )
            if x.max() != x.min()
            else 100
        )
    )

    result["sector_quality_score"] = (
        result["sector_quality_score"].round(2)
    )

    return result