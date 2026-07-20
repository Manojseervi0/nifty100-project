from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "nifty100.db"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"

METRIC_COLUMNS = {
    "compounded_sales_growth": "revenue_cagr",
    "compounded_profit_growth": "pat_cagr",
    "stock_price_cagr": "stock_price_cagr",
    "roe": "roe",
}

TEXT_PATTERN = re.compile(
    r"""
    (?:
        (?P<years>\d+)\s*Years?
        |
        (?P<ttm>TTM)
        |
        (?P<last_year>Last\s+Year)
    )
    \s*:?\s*
    (?P<value>[+-]?\d+(?:\.\d+)?)
    \s*%
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)

RATIO_COLUMN_MAP = {
    "revenue_cagr": "revenue_cagr_5yr",
    "pat_cagr": "pat_cagr_5yr",
}


def parse_analysis_text(raw_text: object) -> tuple[int, float] | None:
    """
    Parse analysis text and return:
    (period_years, value_pct)

    Rules:
    TTM       -> period_years = 0
    Last Year -> period_years = 1
    """

    if raw_text is None or pd.isna(raw_text):
        return None

    text = str(raw_text).strip()

    if not text:
        return None

    match = TEXT_PATTERN.search(text)

    if not match:
        return None

    if match.group("ttm"):
        period_years = 0

    elif match.group("last_year"):
        period_years = 1

    else:
        period_years = int(match.group("years"))

    value_pct = float(match.group("value"))

    return period_years, value_pct


def load_analysis_data(conn: sqlite3.Connection) -> pd.DataFrame:

    query = """
        SELECT
            company_id,
            compounded_sales_growth,
            compounded_profit_growth,
            stock_price_cagr,
            roe
        FROM analysis
        ORDER BY company_id, id
    """

    return pd.read_sql_query(query, conn)


def parse_analysis_dataframe(
    analysis_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    parsed_rows = []
    failure_rows = []

    for _, row in analysis_df.iterrows():

        company_id = row["company_id"]

        for source_column, metric_type in METRIC_COLUMNS.items():

            raw_text = row.get(source_column)

            parsed = parse_analysis_text(raw_text)

            if parsed is None:

                failure_rows.append(
                    {
                        "company_id": company_id,
                        "metric_type": metric_type,
                        "raw_text": raw_text,
                        "reason": "Regex pattern did not match",
                    }
                )

                continue

            period_years, value_pct = parsed

            parsed_rows.append(
                {
                    "company_id": company_id,
                    "metric_type": metric_type,
                    "period_years": period_years,
                    "value_pct": value_pct,
                }
            )

    parsed_df = pd.DataFrame(
        parsed_rows,
        columns=[
            "company_id",
            "metric_type",
            "period_years",
            "value_pct",
        ],
    )

    failures_df = pd.DataFrame(
        failure_rows,
        columns=[
            "company_id",
            "metric_type",
            "raw_text",
            "reason",
        ],
    )

    return parsed_df, failures_df


def get_latest_ratio_values(
    conn: sqlite3.Connection,
) -> pd.DataFrame:

    ratios_df = pd.read_sql_query(
        """
        SELECT
            company_id,
            year,
            revenue_cagr_5yr,
            pat_cagr_5yr
        FROM financial_ratios
        """,
        conn,
    )

    if ratios_df.empty:
        return ratios_df

    ratios_df["year_number"] = pd.to_numeric(
        ratios_df["year"]
        .astype(str)
        .str.extract(r"(\d{4})")[0],
        errors="coerce",
    )

    ratios_df = (
        ratios_df
        .sort_values(
            ["company_id", "year_number"],
            ascending=[True, False],
            na_position="last",
        )
        .drop_duplicates(
            subset=["company_id"],
            keep="first",
        )
        .reset_index(drop=True)
    )

    return ratios_df


def cross_validate_cagr(
    parsed_df: pd.DataFrame,
    latest_ratios_df: pd.DataFrame,
) -> pd.DataFrame:

    review_rows = []

    five_year_df = parsed_df[
        (parsed_df["period_years"] == 5)
        & (
            parsed_df["metric_type"]
            .isin(RATIO_COLUMN_MAP)
        )
    ].copy()

    if five_year_df.empty or latest_ratios_df.empty:

        return pd.DataFrame(
            columns=[
                "company_id",
                "metric_type",
                "parsed_value_pct",
                "computed_value_pct",
                "divergence_pct_points",
                "divergence_flag",
            ]
        )

    ratio_lookup = latest_ratios_df.set_index(
        "company_id"
    )

    for _, row in five_year_df.iterrows():

        company_id = row["company_id"]

        metric_type = row["metric_type"]

        parsed_value = row["value_pct"]

        computed_value = None

        if company_id in ratio_lookup.index:

            ratio_column = RATIO_COLUMN_MAP[
                metric_type
            ]

            candidate = ratio_lookup.loc[
                company_id,
                ratio_column,
            ]

            if isinstance(candidate, pd.Series):
                candidate = candidate.iloc[0]

            if pd.notna(candidate):

                computed_value = float(
                    candidate
                )

        if computed_value is None:

            divergence = None

            divergence_flag = (
                "NO_COMPUTED_VALUE"
            )

        else:

            divergence = abs(
                float(parsed_value)
                - computed_value
            )

            divergence_flag = (
                "REVIEW"
                if divergence > 5.0
                else "OK"
            )

        review_rows.append(
            {
                "company_id": company_id,
                "metric_type": metric_type,
                "parsed_value_pct": parsed_value,
                "computed_value_pct": computed_value,
                "divergence_pct_points": divergence,
                "divergence_flag": divergence_flag,
            }
        )

    return pd.DataFrame(review_rows)


def run_parser(
    db_path: Path,
    output_dir: Path,
) -> None:

    if not db_path.exists():

        raise FileNotFoundError(
            f"Database not found: {db_path}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with sqlite3.connect(db_path) as conn:

        analysis_df = load_analysis_data(
            conn
        )

        parsed_df, failures_df = (
            parse_analysis_dataframe(
                analysis_df
            )
        )

        latest_ratios_df = (
            get_latest_ratio_values(
                conn
            )
        )

        validation_df = (
            cross_validate_cagr(
                parsed_df,
                latest_ratios_df,
            )
        )

    parsed_path = (
        output_dir
        / "analysis_parsed.csv"
    )

    failures_path = (
        output_dir
        / "parse_failures.csv"
    )

    validation_path = (
        output_dir
        / "cagr_cross_validation.csv"
    )

    parsed_df.to_csv(
        parsed_path,
        index=False,
    )

    failures_df.to_csv(
        failures_path,
        index=False,
    )

    validation_df.to_csv(
        validation_path,
        index=False,
    )

    review_count = (
        int(
            (
                validation_df[
                    "divergence_flag"
                ]
                == "REVIEW"
            ).sum()
        )
        if not validation_df.empty
        else 0
    )

    print("=" * 60)

    print(
        "DAY 29 - NLP ANALYSIS "
        "PARSER COMPLETE"
    )

    print("=" * 60)

    print(
        f"Analysis source rows       : "
        f"{len(analysis_df)}"
    )

    print(
        f"Parsed metric records      : "
        f"{len(parsed_df)}"
    )

    print(
        f"Parse failures             : "
        f"{len(failures_df)}"
    )

    print(
        f"CAGR comparisons           : "
        f"{len(validation_df)}"
    )

    print(
        f"Divergence > 5 pct points  : "
        f"{review_count}"
    )

    print()

    print(
        f"Generated: {parsed_path}"
    )

    print(
        f"Generated: {failures_path}"
    )

    print(
        f"Generated: {validation_path}"
    )


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Parse structured financial "
            "metrics from analysis table."
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

    run_parser(
        args.db,
        args.output_dir,
    )


if __name__ == "__main__":
    main()