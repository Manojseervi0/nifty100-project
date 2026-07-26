from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

# Keep KMeans deterministic and avoid excessive BLAS/OpenMP threading
# on small datasets such as this 92-company universe.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "nifty100.db"
DEFAULT_CASHFLOW_PATH = PROJECT_ROOT / "output" / "cashflow_intelligence.xlsx"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output" / "cluster_labels.csv"
DEFAULT_ELBOW_PATH = PROJECT_ROOT / "reports" / "elbow_plot.png"

FEATURES = [
    "return_on_equity_pct",
    "debt_to_equity",
    "revenue_cagr_5yr",
    "fcf_cagr_5yr",
    "operating_profit_margin_pct",
]


def extract_year_number(value: object) -> float:
    """Extract a four-digit year from a financial-year label."""
    if value is None or pd.isna(value):
        return np.nan

    match = pd.Series([str(value)]).str.extract(r"(\d{4})", expand=False).iloc[0]
    return float(match) if pd.notna(match) else np.nan


def load_company_universe(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load the canonical company universe with sector information."""
    query = """
        SELECT
            c.id AS company_id,
            c.company_name,
            s.broad_sector
        FROM companies AS c
        LEFT JOIN sectors AS s
            ON s.company_id = c.id
        ORDER BY c.id
    """
    return pd.read_sql_query(query, conn)


def load_latest_ratios(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load one latest financial-ratio row per company."""
    query = """
        SELECT
            company_id,
            year,
            return_on_equity_pct,
            debt_to_equity,
            revenue_cagr_5yr,
            operating_profit_margin_pct
        FROM financial_ratios
    """
    ratios = pd.read_sql_query(query, conn)

    if ratios.empty:
        return ratios

    ratios["year_number"] = ratios["year"].map(extract_year_number)
    ratios = (
        ratios.sort_values(
            ["company_id", "year_number"],
            ascending=[True, False],
            na_position="last",
        )
        .drop_duplicates(subset=["company_id"], keep="first")
        .drop(columns=["year_number"])
        .reset_index(drop=True)
    )
    return ratios


def load_fcf_cagr(cashflow_path: Path) -> pd.DataFrame:
    """Load 5-year FCF CAGR from the Sprint 5 cash-flow intelligence output."""
    if not cashflow_path.exists():
        raise FileNotFoundError(
            "Cash-flow intelligence file not found: "
            f"{cashflow_path}\n"
            "Run `python -m src.analytics.cashflow_kpis` first."
        )

    df = pd.read_excel(
        cashflow_path,
        usecols=["company_id", "fcf_cagr_5yr"],
    )

    return (
        df.drop_duplicates(subset=["company_id"], keep="last")
        .reset_index(drop=True)
    )


def build_feature_frame(
    companies: pd.DataFrame,
    ratios: pd.DataFrame,
    fcf_data: pd.DataFrame,
) -> pd.DataFrame:
    """Merge all five clustering features onto the canonical company universe."""
    frame = companies.merge(
        ratios,
        on="company_id",
        how="left",
    ).merge(
        fcf_data,
        on="company_id",
        how="left",
    )

    for feature in FEATURES:
        frame[feature] = pd.to_numeric(frame[feature], errors="coerce")

    return frame


def impute_with_sector_medians(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Impute missing feature values using sector medians, then global medians."""
    result = frame.copy()
    audit_rows: list[dict[str, object]] = []

    for feature in FEATURES:
        missing_before = result[feature].isna()

        sector_median = result.groupby("broad_sector")[feature].transform("median")
        result.loc[missing_before, feature] = sector_median[missing_before]

        still_missing = result[feature].isna()
        global_median = result[feature].median()

        if pd.isna(global_median):
            raise ValueError(
                f"Feature '{feature}' contains no usable numeric values."
            )

        result.loc[still_missing, feature] = global_median

        for idx in result.index[missing_before]:
            method = (
                "sector_median"
                if not pd.isna(sector_median.loc[idx])
                else "global_median"
            )
            audit_rows.append(
                {
                    "company_id": result.loc[idx, "company_id"],
                    "feature": feature,
                    "imputation_method": method,
                    "imputed_value": result.loc[idx, feature],
                }
            )

    audit = pd.DataFrame(
        audit_rows,
        columns=[
            "company_id",
            "feature",
            "imputation_method",
            "imputed_value",
        ],
    )
    return result, audit


def generate_elbow_plot(
    scaled_features: np.ndarray,
    output_path: Path,
) -> pd.DataFrame:
    """Generate KMeans inertia values for k=2 through k=10 and save the elbow plot."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, float]] = []

    for k in range(2, 11):
        model = KMeans(
            n_clusters=k,
            random_state=42,
            n_init=10,
        )
        model.fit(scaled_features)
        rows.append({"k": k, "inertia": float(model.inertia_)})

    elbow_df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(
        elbow_df["k"],
        elbow_df["inertia"],
        marker="o",
    )
    ax.axvline(
        5,
        linestyle="--",
        linewidth=1,
        label="Selected k = 5",
    )
    ax.set_title("KMeans Elbow Plot")
    ax.set_xlabel("Number of clusters (k)")
    ax.set_ylabel("Inertia")
    ax.set_xticks(range(2, 11))
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

    return elbow_df


def assign_cluster_names(
    clustered: pd.DataFrame,
    scaled_features: np.ndarray,
) -> dict[int, str]:
    """Assign provisional descriptive names from each cluster's financial profile."""
    profile = pd.DataFrame(
        scaled_features,
        columns=FEATURES,
        index=clustered.index,
    )
    profile["cluster_id"] = clustered["cluster_id"].to_numpy()

    means = profile.groupby("cluster_id")[FEATURES].mean()

    quality_score = (
        0.30 * means["return_on_equity_pct"]
        + 0.25 * means["operating_profit_margin_pct"]
        + 0.20 * means["revenue_cagr_5yr"]
        + 0.15 * means["fcf_cagr_5yr"]
        - 0.10 * means["debt_to_equity"]
    )

    names: dict[int, str] = {}

    high_quality = int(quality_score.idxmax())
    distressed = int(quality_score.idxmin())

    names[high_quality] = "High-Quality Compounders"
    names[distressed] = "Distressed or Turnaround"

    remaining = [
        int(cluster_id)
        for cluster_id in means.index
        if int(cluster_id) not in names
    ]

    growth_score = (
        means.loc[remaining, "revenue_cagr_5yr"]
        + means.loc[remaining, "fcf_cagr_5yr"]
    )
    emerging = int(growth_score.idxmax())
    names[emerging] = "Emerging Growth"

    remaining = [
        cluster_id
        for cluster_id in remaining
        if cluster_id != emerging
    ]

    defensive_score = (
        means.loc[remaining, "return_on_equity_pct"]
        + means.loc[remaining, "operating_profit_margin_pct"]
        - means.loc[remaining, "debt_to_equity"]
    )
    defensive = int(defensive_score.idxmax())
    names[defensive] = "Defensive Quality"

    remaining = [
        cluster_id
        for cluster_id in remaining
        if cluster_id != defensive
    ]

    if remaining:
        names[int(remaining[0])] = "Value Cyclicals"

    return names


def run_clustering(
    db_path: Path,
    cashflow_path: Path,
    output_path: Path,
    elbow_path: Path,
) -> None:
    """Run the complete Day 36 clustering pipeline and generate its outputs."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    elbow_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        companies = load_company_universe(conn)
        ratios = load_latest_ratios(conn)

    fcf_data = load_fcf_cagr(cashflow_path)

    features = build_feature_frame(
        companies=companies,
        ratios=ratios,
        fcf_data=fcf_data,
    )

    if len(features) != 92:
        raise ValueError(
            "Expected 92 canonical companies, "
            f"but found {len(features)}."
        )

    imputed, imputation_audit = impute_with_sector_medians(features)

    scaler = StandardScaler()
    scaled = scaler.fit_transform(imputed[FEATURES])

    elbow_df = generate_elbow_plot(
        scaled_features=scaled,
        output_path=elbow_path,
    )

    model = KMeans(
        n_clusters=5,
        random_state=42,
        n_init=10,
    )

    cluster_ids = model.fit_predict(scaled)

    distances = np.linalg.norm(
        scaled - model.cluster_centers_[cluster_ids],
        axis=1,
    )

    clustered = imputed.copy()
    clustered["cluster_id"] = cluster_ids.astype(int)

    cluster_names = assign_cluster_names(
        clustered=clustered,
        scaled_features=scaled,
    )

    clustered["cluster_name"] = clustered["cluster_id"].map(cluster_names)
    clustered["distance_from_centroid"] = np.round(distances, 6)

    output = clustered[
        [
            "company_id",
            "cluster_id",
            "cluster_name",
            "distance_from_centroid",
        ]
    ].sort_values(
        ["cluster_id", "distance_from_centroid", "company_id"]
    )

    output.to_csv(output_path, index=False)

    audit_path = output_path.parent / "cluster_imputation_audit.csv"
    elbow_data_path = output_path.parent / "elbow_inertia.csv"

    imputation_audit.to_csv(audit_path, index=False)
    elbow_df.to_csv(elbow_data_path, index=False)

    cluster_counts = (
        output.groupby(
            ["cluster_id", "cluster_name"]
        )
        .size()
        .reset_index(name="company_count")
    )

    missing_after = int(imputed[FEATURES].isna().sum().sum())

    print("=" * 72)
    print("DAY 36 - KMEANS CLUSTERING COMPLETE")
    print("=" * 72)
    print(f"Canonical companies        : {len(companies)}")
    print(f"Companies clustered        : {len(output)}")
    print(f"Clusters generated         : {output['cluster_id'].nunique()}")
    print(f"Missing values after impute: {missing_after}")
    print(f"Imputed feature values     : {len(imputation_audit)}")
    print()
    print("Cluster distribution:")
    for row in cluster_counts.itertuples(index=False):
        print(
            f"  Cluster {row.cluster_id}: "
            f"{row.cluster_name} = {row.company_count}"
        )
    print()
    print(f"Generated: {output_path}")
    print(f"Generated: {elbow_path}")
    print(f"Audit    : {audit_path}")
    print(f"Elbow CSV: {elbow_data_path}")


def main() -> None:
    """Parse CLI arguments and execute the clustering pipeline."""
    parser = argparse.ArgumentParser(
        description="Run Day 36 KMeans clustering for the Nifty100 project."
    )

    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to nifty100.db",
    )

    parser.add_argument(
        "--cashflow",
        type=Path,
        default=DEFAULT_CASHFLOW_PATH,
        help="Path to cashflow_intelligence.xlsx",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path for cluster_labels.csv",
    )

    parser.add_argument(
        "--elbow",
        type=Path,
        default=DEFAULT_ELBOW_PATH,
        help="Path for elbow_plot.png",
    )

    args = parser.parse_args()

    run_clustering(
        db_path=args.db,
        cashflow_path=args.cashflow,
        output_path=args.output,
        elbow_path=args.elbow,
    )


if __name__ == "__main__":
    main()