from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Iterable

# Keep numerical libraries conservative on the small 92-company dataset.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .clustering import (
    FEATURES,
    build_feature_frame,
    impute_with_sector_medians,
    load_company_universe,
    load_fcf_cagr,
    load_latest_ratios,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "nifty100.db"
DEFAULT_CASHFLOW_PATH = PROJECT_ROOT / "output" / "cashflow_intelligence.xlsx"
DEFAULT_CLUSTER_LABELS_PATH = PROJECT_ROOT / "output" / "cluster_labels.csv"
DEFAULT_CLUSTER_PROFILES_PATH = PROJECT_ROOT / "output" / "cluster_profiles.csv"
DEFAULT_OUTLIER_PATH = PROJECT_ROOT / "output" / "outlier_report.csv"
DEFAULT_PORTFOLIO_STATS_PATH = PROJECT_ROOT / "output" / "portfolio_stats.csv"
DEFAULT_CORRELATION_MATRIX_PATH = PROJECT_ROOT / "output" / "correlation_matrix.csv"
DEFAULT_CORRELATION_HEATMAP_PATH = PROJECT_ROOT / "reports" / "correlation_heatmap.png"
DEFAULT_IMPUTATION_AUDIT_PATH = PROJECT_ROOT / "output" / "day37_imputation_audit.csv"

CORE_KPIS = [
    "return_on_equity_pct",
    "return_on_capital_employed_pct",
    "net_profit_margin_pct",
    "operating_profit_margin_pct",
    "debt_to_equity",
    "interest_coverage",
    "asset_turnover",
    "free_cash_flow_cr",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
]

KPI_LABELS = {
    "return_on_equity_pct": "ROE",
    "return_on_capital_employed_pct": "ROCE",
    "net_profit_margin_pct": "Net Profit Margin",
    "operating_profit_margin_pct": "Operating Profit Margin",
    "debt_to_equity": "Debt to Equity",
    "interest_coverage": "Interest Coverage",
    "asset_turnover": "Asset Turnover",
    "free_cash_flow_cr": "Free Cash Flow",
    "revenue_cagr_5yr": "Revenue CAGR 5Y",
    "pat_cagr_5yr": "PAT CAGR 5Y",
}

# Optional manual review hook. After reviewing cluster_profiles.csv and member
# companies with the team lead, add overrides such as:
# CLUSTER_NAME_OVERRIDES = {0: "Defensive Quality"}
CLUSTER_NAME_OVERRIDES: dict[int, str] = {}


def extract_year_number(value: object) -> float:
    """Extract a four-digit year from a financial-year label."""
    if value is None or pd.isna(value):
        return np.nan

    match = pd.Series([str(value)]).str.extract(r"(\d{4})", expand=False).iloc[0]
    return float(match) if pd.notna(match) else np.nan


def load_latest_core_kpis(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load one latest financial-ratio record per company for ten core KPIs."""
    columns = ",\n            ".join(CORE_KPIS)
    query = f"""
        SELECT
            company_id,
            year,
            {columns}
        FROM financial_ratios
    """
    ratios = pd.read_sql_query(query, conn)

    if ratios.empty:
        return ratios

    ratios["year_number"] = ratios["year"].map(extract_year_number)
    return (
        ratios.sort_values(
            ["company_id", "year_number"],
            ascending=[True, False],
            na_position="last",
        )
        .drop_duplicates(subset=["company_id"], keep="first")
        .drop(columns=["year_number"])
        .reset_index(drop=True)
    )


def load_cluster_labels(path: Path) -> pd.DataFrame:
    """Load and validate Day 36 cluster assignments."""
    if not path.exists():
        raise FileNotFoundError(
            f"Cluster labels not found: {path}\n"
            "Run `python -m src.analytics.clustering` first."
        )

    labels = pd.read_csv(path)
    required = {
        "company_id",
        "cluster_id",
        "cluster_name",
        "distance_from_centroid",
    }
    missing = required.difference(labels.columns)
    if missing:
        raise ValueError(
            "cluster_labels.csv is missing columns: "
            + ", ".join(sorted(missing))
        )

    labels["cluster_id"] = pd.to_numeric(
        labels["cluster_id"], errors="raise"
    ).astype(int)
    labels["distance_from_centroid"] = pd.to_numeric(
        labels["distance_from_centroid"], errors="coerce"
    )

    if labels["company_id"].duplicated().any():
        duplicates = labels.loc[
            labels["company_id"].duplicated(keep=False), "company_id"
        ].tolist()
        raise ValueError(f"Duplicate cluster assignments found: {duplicates}")

    if len(labels) != 92:
        raise ValueError(f"Expected 92 cluster assignments, found {len(labels)}.")

    if labels["cluster_id"].nunique() != 5:
        raise ValueError(
            "Expected exactly 5 clusters, found "
            f"{labels['cluster_id'].nunique()}."
        )

    return labels


def impute_kpis_with_sector_medians(
    frame: pd.DataFrame,
    metrics: Iterable[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Impute missing KPI values using sector medians and global medians."""
    result = frame.copy()
    audit_rows: list[dict[str, object]] = []

    for metric in metrics:
        result[metric] = pd.to_numeric(result[metric], errors="coerce")
        missing_before = result[metric].isna()

        sector_median = result.groupby("broad_sector")[metric].transform("median")
        result.loc[missing_before, metric] = sector_median[missing_before]

        still_missing = result[metric].isna()
        global_median = result[metric].median()
        if pd.isna(global_median):
            raise ValueError(f"KPI '{metric}' contains no usable numeric values.")

        result.loc[still_missing, metric] = global_median

        for idx in result.index[missing_before]:
            method = (
                "sector_median"
                if pd.notna(sector_median.loc[idx])
                else "global_median"
            )
            audit_rows.append(
                {
                    "company_id": result.loc[idx, "company_id"],
                    "metric": metric,
                    "imputation_method": method,
                    "imputed_value": result.loc[idx, metric],
                }
            )

    audit = pd.DataFrame(
        audit_rows,
        columns=[
            "company_id",
            "metric",
            "imputation_method",
            "imputed_value",
        ],
    )
    return result, audit


def standardize_cluster_means(cluster_means: pd.DataFrame) -> pd.DataFrame:
    """Convert cluster-level feature means to comparable z-scores."""
    standardized = cluster_means.copy().astype(float)
    for feature in FEATURES:
        series = standardized[feature]
        std = series.std(ddof=0)
        if pd.isna(std) or np.isclose(std, 0.0):
            standardized[feature] = 0.0
        else:
            standardized[feature] = (series - series.mean()) / std
    return standardized


def assign_final_cluster_names(cluster_means: pd.DataFrame) -> dict[int, str]:
    """Assign one descriptive financial archetype to each of the five clusters."""
    z = standardize_cluster_means(cluster_means)
    remaining = set(int(value) for value in z.index)
    names: dict[int, str] = {}

    quality_score = (
        0.30 * z["return_on_equity_pct"]
        + 0.25 * z["operating_profit_margin_pct"]
        + 0.20 * z["revenue_cagr_5yr"]
        + 0.15 * z["fcf_cagr_5yr"]
        - 0.10 * z["debt_to_equity"]
    )
    quality_id = int(quality_score.loc[list(remaining)].idxmax())
    names[quality_id] = "High-Quality Compounders"
    remaining.remove(quality_id)

    distress_score = (
        -0.25 * z["return_on_equity_pct"]
        - 0.20 * z["operating_profit_margin_pct"]
        - 0.15 * z["revenue_cagr_5yr"]
        - 0.15 * z["fcf_cagr_5yr"]
        + 0.25 * z["debt_to_equity"]
    )
    distress_id = int(distress_score.loc[list(remaining)].idxmax())
    names[distress_id] = "Distressed or Turnaround"
    remaining.remove(distress_id)

    growth_score = (
        0.45 * z["revenue_cagr_5yr"]
        + 0.40 * z["fcf_cagr_5yr"]
        + 0.15 * z["return_on_equity_pct"]
    )
    growth_id = int(growth_score.loc[list(remaining)].idxmax())
    names[growth_id] = "Emerging Growth"
    remaining.remove(growth_id)

    defensive_score = (
        0.40 * z["return_on_equity_pct"]
        + 0.35 * z["operating_profit_margin_pct"]
        - 0.25 * z["debt_to_equity"]
    )
    defensive_id = int(defensive_score.loc[list(remaining)].idxmax())
    names[defensive_id] = "Defensive Quality"
    remaining.remove(defensive_id)

    if len(remaining) != 1:
        raise ValueError("Unable to assign a unique name to every cluster.")
    names[remaining.pop()] = "Value Cyclicals"

    return names


def resolve_final_cluster_names(
    labels: pd.DataFrame,
    cluster_means: pd.DataFrame,
) -> dict[int, str]:
    """Preserve reviewed Day 36 names and apply optional team-lead overrides."""
    existing: dict[int, str] = {}

    for cluster_id, group in labels.groupby("cluster_id"):
        names = [
            str(value).strip()
            for value in group["cluster_name"].dropna().unique()
            if str(value).strip()
        ]
        if len(names) == 1:
            existing[int(cluster_id)] = names[0]

    expected_ids = set(int(value) for value in cluster_means.index)
    existing.update(
        {
            int(cluster_id): str(name).strip()
            for cluster_id, name in CLUSTER_NAME_OVERRIDES.items()
            if int(cluster_id) in expected_ids and str(name).strip()
        }
    )

    if set(existing) != expected_ids or len(set(existing.values())) != 5:
        return assign_final_cluster_names(cluster_means)

    return existing


def build_cluster_profiles(
    feature_frame: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[int, str]]:
    """Create cluster mean/median profiles and representative company lists."""
    merged = feature_frame.merge(
        labels[
            [
                "company_id",
                "cluster_id",
                "distance_from_centroid",
            ]
        ],
        on="company_id",
        how="inner",
        validate="one_to_one",
    )

    if len(merged) != 92:
        raise ValueError(
            f"Expected 92 companies after profile merge, found {len(merged)}."
        )

    cluster_means = merged.groupby("cluster_id")[FEATURES].mean()
    cluster_medians = merged.groupby("cluster_id")[FEATURES].median()
    final_names = resolve_final_cluster_names(labels, cluster_means)

    rows: list[dict[str, object]] = []
    for cluster_id in sorted(cluster_means.index.astype(int)):
        members = merged.loc[merged["cluster_id"] == cluster_id].copy()
        representatives = (
            members.sort_values(
                ["distance_from_centroid", "company_id"],
                na_position="last",
            )["company_id"]
            .head(5)
            .tolist()
        )

        row: dict[str, object] = {
            "cluster_id": cluster_id,
            "cluster_name": final_names[cluster_id],
            "company_count": len(members),
            "representative_companies": ", ".join(representatives),
        }

        for feature in FEATURES:
            row[f"{feature}_mean"] = round(
                float(cluster_means.loc[cluster_id, feature]), 4
            )
            row[f"{feature}_median"] = round(
                float(cluster_medians.loc[cluster_id, feature]), 4
            )

        rows.append(row)

    return pd.DataFrame(rows), final_names


def update_cluster_labels(
    labels: pd.DataFrame,
    final_names: dict[int, str],
    output_path: Path,
) -> pd.DataFrame:
    """Update Day 36 cluster labels with the final Day 37 archetype names."""
    updated = labels.copy()
    updated["cluster_name"] = updated["cluster_id"].map(final_names)

    if updated["cluster_name"].isna().any():
        raise ValueError("At least one cluster did not receive a final name.")

    updated = updated.sort_values(
        ["cluster_id", "distance_from_centroid", "company_id"],
        na_position="last",
    )
    updated.to_csv(output_path, index=False)
    return updated


def generate_correlation_heatmap(
    frame: pd.DataFrame,
    output_path: Path,
    matrix_path: Path,
) -> pd.DataFrame:
    """Generate and save a Pearson correlation heatmap for ten core KPIs."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    matrix_path.parent.mkdir(parents=True, exist_ok=True)

    correlation = frame[CORE_KPIS].corr(method="pearson")
    correlation.to_csv(matrix_path)

    display_correlation = correlation.rename(
        index=KPI_LABELS,
        columns=KPI_LABELS,
    )

    fig, ax = plt.subplots(figsize=(14, 11))
    sns.heatmap(
        display_correlation,
        annot=True,
        fmt=".2f",
        cmap="coolwarm",
        center=0,
        vmin=-1,
        vmax=1,
        linewidths=0.5,
        square=True,
        cbar_kws={"label": "Pearson correlation"},
        ax=ax,
    )
    ax.set_title("Nifty100 Latest-Year KPI Correlation Matrix", pad=18)
    ax.tick_params(axis="x", rotation=45)
    ax.tick_params(axis="y", rotation=0)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

    return correlation


def detect_sector_outliers(frame: pd.DataFrame) -> pd.DataFrame:
    """Flag sector-relative KPI observations with an absolute Z-score above 3."""
    rows: list[dict[str, object]] = []

    for sector, sector_frame in frame.groupby("broad_sector", dropna=False):
        sector_name = "Unknown" if pd.isna(sector) else str(sector)

        for metric in CORE_KPIS:
            values = pd.to_numeric(sector_frame[metric], errors="coerce")
            valid = values.dropna()

            if len(valid) < 3:
                continue

            sector_mean = float(valid.mean())
            sector_std = float(valid.std(ddof=0))

            if np.isclose(sector_std, 0.0):
                continue

            z_scores = (values - sector_mean) / sector_std
            flagged = sector_frame.loc[z_scores.abs() > 3].copy()

            for idx, company in flagged.iterrows():
                z_score = float(z_scores.loc[idx])
                rows.append(
                    {
                        "company_id": company["company_id"],
                        "company_name": company["company_name"],
                        "broad_sector": sector_name,
                        "metric": metric,
                        "metric_label": KPI_LABELS[metric],
                        "metric_value": round(float(company[metric]), 6),
                        "sector_mean": round(sector_mean, 6),
                        "sector_std": round(sector_std, 6),
                        "z_score": round(z_score, 6),
                        "absolute_z_score": round(abs(z_score), 6),
                    }
                )

    columns = [
        "company_id",
        "company_name",
        "broad_sector",
        "metric",
        "metric_label",
        "metric_value",
        "sector_mean",
        "sector_std",
        "z_score",
        "absolute_z_score",
    ]

    if not rows:
        return pd.DataFrame(columns=columns)

    return pd.DataFrame(rows, columns=columns).sort_values(
        ["absolute_z_score", "company_id", "metric"],
        ascending=[False, True, True],
    )


def calculate_portfolio_stats(frame: pd.DataFrame) -> pd.DataFrame:
    """Calculate P10 through P90, mean, and standard deviation for core KPIs."""
    rows: list[dict[str, object]] = []

    for metric in CORE_KPIS:
        values = pd.to_numeric(frame[metric], errors="coerce").dropna()
        rows.append(
            {
                "metric": metric,
                "metric_label": KPI_LABELS[metric],
                "company_count": int(values.count()),
                "p10": round(float(values.quantile(0.10)), 6),
                "p25": round(float(values.quantile(0.25)), 6),
                "p50": round(float(values.quantile(0.50)), 6),
                "p75": round(float(values.quantile(0.75)), 6),
                "p90": round(float(values.quantile(0.90)), 6),
                "mean": round(float(values.mean()), 6),
                "std": round(float(values.std(ddof=1)), 6),
            }
        )

    return pd.DataFrame(rows)


def run_cluster_profiling(
    db_path: Path,
    cashflow_path: Path,
    cluster_labels_path: Path,
    cluster_profiles_path: Path,
    outlier_path: Path,
    portfolio_stats_path: Path,
    correlation_matrix_path: Path,
    correlation_heatmap_path: Path,
    imputation_audit_path: Path,
) -> None:
    """Run the complete Day 37 cluster profiling and portfolio statistics pipeline."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    for path in [
        cluster_labels_path,
        cluster_profiles_path,
        outlier_path,
        portfolio_stats_path,
        correlation_matrix_path,
        imputation_audit_path,
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
    correlation_heatmap_path.parent.mkdir(parents=True, exist_ok=True)

    labels = load_cluster_labels(cluster_labels_path)

    with sqlite3.connect(db_path) as conn:
        companies = load_company_universe(conn)
        latest_cluster_ratios = load_latest_ratios(conn)
        latest_core_kpis = load_latest_core_kpis(conn)

    if len(companies) != 92:
        raise ValueError(
            f"Expected 92 canonical companies, found {len(companies)}."
        )

    fcf_data = load_fcf_cagr(cashflow_path)
    raw_feature_frame = build_feature_frame(
        companies=companies,
        ratios=latest_cluster_ratios,
        fcf_data=fcf_data,
    )
    feature_frame, feature_imputation_audit = impute_with_sector_medians(
        raw_feature_frame
    )

    cluster_profiles, final_names = build_cluster_profiles(
        feature_frame=feature_frame,
        labels=labels,
    )
    updated_labels = update_cluster_labels(
        labels=labels,
        final_names=final_names,
        output_path=cluster_labels_path,
    )
    cluster_profiles.to_csv(cluster_profiles_path, index=False)

    kpi_frame = companies.merge(
        latest_core_kpis,
        on="company_id",
        how="left",
        validate="one_to_one",
    )
    kpi_frame, kpi_imputation_audit = impute_kpis_with_sector_medians(
        kpi_frame,
        CORE_KPIS,
    )

    feature_audit = feature_imputation_audit.rename(
        columns={"feature": "metric"}
    ).copy()
    feature_audit["pipeline_section"] = "cluster_features"
    kpi_imputation_audit["pipeline_section"] = "core_kpis"

    combined_audit = pd.concat(
        [
            feature_audit[
                [
                    "company_id",
                    "metric",
                    "imputation_method",
                    "imputed_value",
                    "pipeline_section",
                ]
            ],
            kpi_imputation_audit[
                [
                    "company_id",
                    "metric",
                    "imputation_method",
                    "imputed_value",
                    "pipeline_section",
                ]
            ],
        ],
        ignore_index=True,
    )
    combined_audit.to_csv(imputation_audit_path, index=False)

    correlation = generate_correlation_heatmap(
        frame=kpi_frame,
        output_path=correlation_heatmap_path,
        matrix_path=correlation_matrix_path,
    )

    outliers = detect_sector_outliers(kpi_frame)
    outliers.to_csv(outlier_path, index=False)

    portfolio_stats = calculate_portfolio_stats(kpi_frame)
    portfolio_stats.to_csv(portfolio_stats_path, index=False)

    missing_after = int(
        feature_frame[FEATURES].isna().sum().sum()
        + kpi_frame[CORE_KPIS].isna().sum().sum()
    )

    print("=" * 72)
    print("DAY 37 - CLUSTER PROFILING & STATISTICS COMPLETE")
    print("=" * 72)
    print(f"Canonical companies        : {len(companies)}")
    print(f"Cluster labels updated     : {len(updated_labels)}")
    print(f"Cluster profiles generated : {len(cluster_profiles)}")
    print(f"Core KPIs analysed         : {len(CORE_KPIS)}")
    print(f"Correlation matrix size    : {correlation.shape[0]}x{correlation.shape[1]}")
    print(f"Outlier observations       : {len(outliers)}")
    print(f"Outlier companies          : {outliers['company_id'].nunique() if not outliers.empty else 0}")
    print(f"Portfolio statistic rows   : {len(portfolio_stats)}")
    print(f"Imputed values audited     : {len(combined_audit)}")
    print(f"Missing values after impute: {missing_after}")
    print()
    print("Final cluster profiles:")
    for row in cluster_profiles.itertuples(index=False):
        print(
            f"  Cluster {row.cluster_id}: {row.cluster_name} "
            f"= {row.company_count} companies"
        )
    print()
    print(f"Updated  : {cluster_labels_path}")
    print(f"Generated: {cluster_profiles_path}")
    print(f"Generated: {correlation_heatmap_path}")
    print(f"Generated: {correlation_matrix_path}")
    print(f"Generated: {outlier_path}")
    print(f"Generated: {portfolio_stats_path}")
    print(f"Audit    : {imputation_audit_path}")


def main() -> None:
    """Parse command-line arguments and execute the Day 37 pipeline."""
    parser = argparse.ArgumentParser(
        description=(
            "Profile KMeans clusters and generate Day 37 portfolio analytics."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--cashflow", type=Path, default=DEFAULT_CASHFLOW_PATH
    )
    parser.add_argument(
        "--cluster-labels",
        type=Path,
        default=DEFAULT_CLUSTER_LABELS_PATH,
    )
    parser.add_argument(
        "--cluster-profiles",
        type=Path,
        default=DEFAULT_CLUSTER_PROFILES_PATH,
    )
    parser.add_argument("--outliers", type=Path, default=DEFAULT_OUTLIER_PATH)
    parser.add_argument(
        "--portfolio-stats",
        type=Path,
        default=DEFAULT_PORTFOLIO_STATS_PATH,
    )
    parser.add_argument(
        "--correlation-matrix",
        type=Path,
        default=DEFAULT_CORRELATION_MATRIX_PATH,
    )
    parser.add_argument(
        "--correlation-heatmap",
        type=Path,
        default=DEFAULT_CORRELATION_HEATMAP_PATH,
    )
    parser.add_argument(
        "--imputation-audit",
        type=Path,
        default=DEFAULT_IMPUTATION_AUDIT_PATH,
    )

    args = parser.parse_args()
    run_cluster_profiling(
        db_path=args.db,
        cashflow_path=args.cashflow,
        cluster_labels_path=args.cluster_labels,
        cluster_profiles_path=args.cluster_profiles,
        outlier_path=args.outliers,
        portfolio_stats_path=args.portfolio_stats,
        correlation_matrix_path=args.correlation_matrix,
        correlation_heatmap_path=args.correlation_heatmap,
        imputation_audit_path=args.imputation_audit,
    )


if __name__ == "__main__":
    main()