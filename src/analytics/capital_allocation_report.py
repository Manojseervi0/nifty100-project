from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "nifty100.db"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"

TICKER_ALIASES = {
    "AGTL": "ATGL",
}

EXPECTED_PATTERNS = [
    "Reinvestor",
    "Shareholder Returns",
    "Liquidating Assets",
    "Distress Signal",
    "Growth Funded by Debt",
    "Cash Accumulator",
    "Pre-Revenue",
    "Mixed",
    "Other",
    "Insufficient Data",
]


def extract_year_number(value) -> int | None:
    """Extract a comparable fiscal year from labels like Mar-13 or Mar 2024."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    four_digit = pd.Series([text]).str.extract(r"(\d{4})", expand=False).iloc[0]
    if pd.notna(four_digit):
        return int(four_digit)

    two_digit = pd.Series([text]).str.extract(r"(\d{2})(?!\d)", expand=False).iloc[0]
    if pd.notna(two_digit):
        year = int(two_digit)
        return 2000 + year if year <= 79 else 1900 + year

    return None


def normalize_ticker(value) -> str:
    ticker = str(value).strip().upper()
    return TICKER_ALIASES.get(ticker, ticker)


def sign_of(value) -> str | None:
    if pd.isna(value):
        return None
    return "+" if float(value) >= 0 else "-"


def classify_from_signs(
    cfo_sign: str | None,
    cfi_sign: str | None,
    cff_sign: str | None,
    cfo_pat_ratio: float | None = None,
) -> str:
    """Apply the project's capital-allocation rule set."""
    if None in (cfo_sign, cfi_sign, cff_sign):
        return "Insufficient Data"

    signs = (cfo_sign, cfi_sign, cff_sign)

    if signs == ("+", "-", "-"):
        if (
            cfo_pat_ratio is not None
            and pd.notna(cfo_pat_ratio)
            and float(cfo_pat_ratio) > 1
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

    return "Other"


def load_canonical_companies(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT id AS company_id
        FROM companies
        ORDER BY id
        """,
        conn,
    )


def load_cashflow(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            rowid AS _rowid,
            company_id,
            year,
            operating_activity,
            investing_activity,
            financing_activity
        FROM cashflow
        """,
        conn,
    )


def load_profit_loss(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            rowid AS _rowid,
            company_id,
            year,
            net_profit
        FROM profitandloss
        """,
        conn,
    )


def prepare_source_audit(raw_df: pd.DataFrame) -> dict:
    audited = raw_df.copy()
    audited["company_id"] = audited["company_id"].map(normalize_ticker)
    audited["year_number"] = audited["year"].map(extract_year_number)

    exact_duplicates = int(raw_df.duplicated().sum())
    normalized_duplicate_pairs = int(
        audited.duplicated(["company_id", "year_number"], keep=False).sum()
    )

    return {
        "source_rows": len(raw_df),
        "source_unique_tickers": raw_df["company_id"].nunique(),
        "exact_duplicate_rows": exact_duplicates,
        "rows_in_duplicate_company_year_pairs": normalized_duplicate_pairs,
    }


def rebuild_from_database(
    conn: sqlite3.Connection,
    canonical_ids: set[str],
) -> pd.DataFrame:
    cashflow = load_cashflow(conn)
    profit_loss = load_profit_loss(conn)

    for frame in (cashflow, profit_loss):
        frame["company_id"] = frame["company_id"].map(normalize_ticker)
        frame["year_number"] = frame["year"].map(extract_year_number)

    cashflow = (
        cashflow[cashflow["company_id"].isin(canonical_ids)]
        .dropna(subset=["year_number"])
        .sort_values("_rowid")
        .drop_duplicates(
            subset=["company_id", "year_number"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    profit_loss = (
        profit_loss[profit_loss["company_id"].isin(canonical_ids)]
        .dropna(subset=["year_number"])
        .sort_values("_rowid")
        .drop_duplicates(
            subset=["company_id", "year_number"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    pat_lookup = {
        (row.company_id, int(row.year_number)): row.net_profit
        for row in profit_loss.itertuples()
    }

    rows = []

    for row in cashflow.itertuples():
        cfo_sign = sign_of(row.operating_activity)
        cfi_sign = sign_of(row.investing_activity)
        cff_sign = sign_of(row.financing_activity)

        pat = pat_lookup.get(
            (row.company_id, int(row.year_number))
        )

        cfo_pat_ratio = None
        if (
            pat is not None
            and pd.notna(pat)
            and float(pat) != 0
            and pd.notna(row.operating_activity)
        ):
            cfo_pat_ratio = float(row.operating_activity) / float(pat)

        rows.append(
            {
                "company_id": row.company_id,
                "year": row.year,
                "year_number": int(row.year_number),
                "cfo_sign": cfo_sign,
                "cfi_sign": cfi_sign,
                "cff_sign": cff_sign,
                "pattern_label": classify_from_signs(
                    cfo_sign,
                    cfi_sign,
                    cff_sign,
                    cfo_pat_ratio,
                ),
                "_source": "database",
            }
        )

    return pd.DataFrame(rows)


def supplement_missing_companies_from_raw(
    rebuilt_df: pd.DataFrame,
    raw_df: pd.DataFrame,
    canonical_ids: set[str],
) -> pd.DataFrame:
    raw = raw_df.copy()
    raw["company_id"] = raw["company_id"].map(normalize_ticker)
    raw["year_number"] = raw["year"].map(extract_year_number)

    raw = raw[
        raw["company_id"].isin(canonical_ids)
        & raw["year_number"].notna()
    ].copy()

    present_ids = set(rebuilt_df["company_id"].unique())
    missing_ids = canonical_ids - present_ids

    supplements = raw[
        raw["company_id"].isin(missing_ids)
    ].copy()

    if supplements.empty:
        return rebuilt_df

    supplements = (
        supplements
        .drop_duplicates(
            subset=[
                "company_id",
                "year_number",
                "cfo_sign",
                "cfi_sign",
                "cff_sign",
            ],
            keep="last",
        )
        .drop_duplicates(
            subset=["company_id", "year_number"],
            keep="last",
        )
    )

    supplements["pattern_label"] = supplements.apply(
        lambda row: classify_from_signs(
            row["cfo_sign"],
            row["cfi_sign"],
            row["cff_sign"],
        ),
        axis=1,
    )
    supplements["_source"] = "raw_csv_supplement"

    supplements = supplements[
        [
            "company_id",
            "year",
            "year_number",
            "cfo_sign",
            "cfi_sign",
            "cff_sign",
            "pattern_label",
            "_source",
        ]
    ]

    return pd.concat(
        [rebuilt_df, supplements],
        ignore_index=True,
    )


def build_latest_distribution(
    clean_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    latest = (
        clean_df
        .sort_values(
            ["company_id", "year_number"],
            ascending=[True, False],
        )
        .drop_duplicates(
            subset=["company_id"],
            keep="first",
        )
        .reset_index(drop=True)
    )

    counts = (
        latest["pattern_label"]
        .value_counts()
        .reindex(EXPECTED_PATTERNS, fill_value=0)
        .rename_axis("pattern_label")
        .reset_index(name="company_count")
    )

    total = int(counts["company_count"].sum())
    counts["percentage_pct"] = (
        (counts["company_count"] / total * 100).round(2)
        if total
        else 0.0
    )

    return latest, counts


def build_pattern_changes(
    clean_df: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    for company_id, group in clean_df.groupby("company_id"):
        ordered = (
            group
            .sort_values("year_number")
            .drop_duplicates(
                subset=["year_number"],
                keep="last",
            )
            .reset_index(drop=True)
        )

        for index in range(1, len(ordered)):
            previous = ordered.iloc[index - 1]
            current = ordered.iloc[index]

            if previous["pattern_label"] == current["pattern_label"]:
                continue

            rows.append(
                {
                    "company_id": company_id,
                    "from_year": previous["year"],
                    "to_year": current["year"],
                    "from_pattern": previous["pattern_label"],
                    "to_pattern": current["pattern_label"],
                }
            )

    return pd.DataFrame(
        rows,
        columns=[
            "company_id",
            "from_year",
            "to_year",
            "from_pattern",
            "to_pattern",
        ],
    )


def update_cashflow_intelligence(
    intelligence_path: Path,
    latest_df: pd.DataFrame,
) -> int:
    if not intelligence_path.exists():
        raise FileNotFoundError(
            "cashflow_intelligence.xlsx not found. "
            "Run Day 31 first."
        )

    intelligence = pd.read_excel(intelligence_path)

    latest_lookup = latest_df[
        ["company_id", "pattern_label"]
    ].rename(
        columns={
            "pattern_label": "_day32_pattern_label",
        }
    )

    updated = intelligence.merge(
        latest_lookup,
        on="company_id",
        how="left",
    )

    if "capital_allocation_label" not in updated.columns:
        updated["capital_allocation_label"] = (
            updated["_day32_pattern_label"]
        )
    else:
        updated["capital_allocation_label"] = (
            updated["_day32_pattern_label"]
            .combine_first(
                updated["capital_allocation_label"]
            )
        )

    updated = updated.drop(
        columns=["_day32_pattern_label"]
    )

    updated.to_excel(
        intelligence_path,
        index=False,
    )

    return len(updated)


def run_day32(
    db_path: Path,
    output_dir: Path,
) -> None:
    capital_path = output_dir / "capital_allocation.csv"
    intelligence_path = output_dir / "cashflow_intelligence.xlsx"

    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}"
        )

    if not capital_path.exists():
        raise FileNotFoundError(
            f"Capital allocation file not found: {capital_path}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_df = pd.read_csv(capital_path)
    audit = prepare_source_audit(raw_df)

    backup_path = output_dir / "capital_allocation_raw_backup.csv"
    if not backup_path.exists():
        shutil.copy2(
            capital_path,
            backup_path,
        )

    with sqlite3.connect(db_path) as conn:
        canonical = load_canonical_companies(conn)
        canonical_ids = set(
            canonical["company_id"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        rebuilt = rebuild_from_database(
            conn,
            canonical_ids,
        )

    clean_df = supplement_missing_companies_from_raw(
        rebuilt,
        raw_df,
        canonical_ids,
    )

    clean_df = (
        clean_df
        .sort_values(
            ["company_id", "year_number"],
        )
        .drop_duplicates(
            subset=["company_id", "year_number"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    latest_df, distribution_df = (
        build_latest_distribution(
            clean_df
        )
    )

    pattern_changes_df = (
        build_pattern_changes(
            clean_df
        )
    )

    missing_companies = sorted(
        canonical_ids
        - set(clean_df["company_id"].unique())
    )

    cleaned_export = clean_df[
        [
            "company_id",
            "year",
            "cfo_sign",
            "cfi_sign",
            "cff_sign",
            "pattern_label",
        ]
    ]

    cleaned_export.to_csv(
        capital_path,
        index=False,
    )

    distribution_path = (
        output_dir
        / "capital_allocation_distribution.csv"
    )
    distribution_df.to_csv(
        distribution_path,
        index=False,
    )

    changes_path = (
        output_dir
        / "pattern_changes.csv"
    )
    pattern_changes_df.to_csv(
        changes_path,
        index=False,
    )

    audit_rows = [
        {
            "check": "raw_source_rows",
            "value": audit["source_rows"],
        },
        {
            "check": "raw_unique_tickers",
            "value": audit["source_unique_tickers"],
        },
        {
            "check": "raw_exact_duplicate_rows",
            "value": audit["exact_duplicate_rows"],
        },
        {
            "check": "raw_rows_in_duplicate_company_year_pairs",
            "value": audit[
                "rows_in_duplicate_company_year_pairs"
            ],
        },
        {
            "check": "clean_rows",
            "value": len(clean_df),
        },
        {
            "check": "canonical_companies_covered",
            "value": clean_df["company_id"].nunique(),
        },
        {
            "check": "missing_canonical_companies",
            "value": ", ".join(missing_companies) or "None",
        },
    ]

    audit_path = (
        output_dir
        / "capital_allocation_audit.csv"
    )
    pd.DataFrame(audit_rows).to_csv(
        audit_path,
        index=False,
    )

    intelligence_rows = update_cashflow_intelligence(
        intelligence_path,
        latest_df,
    )

    print("=" * 68)
    print("DAY 32 - CAPITAL ALLOCATION REPORT COMPLETE")
    print("=" * 68)
    print(f"Raw source rows             : {audit['source_rows']}")
    print(f"Clean capital rows          : {len(clean_df)}")
    print(
        "Canonical companies covered : "
        f"{clean_df['company_id'].nunique()}/"
        f"{len(canonical_ids)}"
    )
    print(
        "Missing canonical companies : "
        f"{', '.join(missing_companies) if missing_companies else '0'}"
    )
    print(
        f"Latest pattern companies    : {len(latest_df)}"
    )
    print(
        f"Pattern changes found       : {len(pattern_changes_df)}"
    )
    print(
        f"Cashflow intelligence rows  : {intelligence_rows}"
    )
    print()
    print(f"Updated  : {capital_path}")
    print(f"Generated: {distribution_path}")
    print(f"Generated: {changes_path}")
    print(f"Generated: {audit_path}")
    print(f"Backup   : {backup_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Clean and validate capital-allocation history, "
            "generate latest-year distribution and pattern changes, "
            "and sync Day 31 cash-flow intelligence output."
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

    run_day32(
        args.db,
        args.output_dir,
    )


if __name__ == "__main__":
    main()