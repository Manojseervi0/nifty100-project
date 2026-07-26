from __future__ import annotations

import csv
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import median, stdev
from typing import Any

from fastapi import APIRouter

from src.api.database import get_connection


router = APIRouter(
    prefix="/portfolio",
    tags=["Portfolio"],
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PORTFOLIO_STATS_PATH = PROJECT_ROOT / "output" / "portfolio_stats.csv"

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

MONTH_NUMBERS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _safe_number(value: object, digits: int = 4) -> float | int | None:
    """Convert an input into a finite JSON-safe number."""

    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    rounded = round(number, digits)
    return int(rounded) if rounded.is_integer() else rounded


def _period_key(value: object) -> tuple[int, int, int]:
    """Convert a financial-period label into a sortable key."""

    if value is None:
        return (0, 0, 0)

    text = str(value).strip()

    if not text:
        return (0, 0, 0)

    if text.upper() == "TTM":
        return (9999, 12, 1)

    month = 12
    month_match = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b",
        text,
        flags=re.IGNORECASE,
    )

    if month_match:
        month = MONTH_NUMBERS[month_match.group(1).lower()]

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)

    if year_match:
        return (int(year_match.group(1)), month, 0)

    short_year_match = re.search(r"(?:-|\s)(\d{2})$", text)

    if short_year_match:
        short_year = int(short_year_match.group(1))
        full_year = 2000 + short_year if short_year <= 69 else 1900 + short_year
        return (full_year, month, 0)

    return (0, 0, 0)


def _percentile(values: list[float], probability: float) -> float:
    """Calculate a linear-interpolated percentile for sorted numeric values."""

    if not values:
        raise ValueError("Cannot calculate percentile for an empty list.")

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)

    if lower_index == upper_index:
        return ordered[lower_index]

    fraction = position - lower_index

    return (
        ordered[lower_index]
        + (ordered[upper_index] - ordered[lower_index]) * fraction
    )


def _load_precomputed_stats() -> list[dict[str, Any]]:
    """Load and validate the Day 37 portfolio-statistics CSV."""

    if not PORTFOLIO_STATS_PATH.exists():
        return []

    required_columns = {
        "metric",
        "metric_label",
        "company_count",
        "p10",
        "p25",
        "p50",
        "p75",
        "p90",
        "mean",
        "std",
    }

    with PORTFOLIO_STATS_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames is None:
            return []

        if not required_columns.issubset(reader.fieldnames):
            return []

        by_metric: dict[str, dict[str, Any]] = {}

        for row in reader:
            metric = str(row.get("metric", "")).strip()

            if metric not in CORE_KPIS:
                continue

            count_value = _safe_number(row.get("company_count"), 0)

            by_metric[metric] = {
                "metric": metric,
                "metric_label": (
                    str(row.get("metric_label", "")).strip()
                    or KPI_LABELS[metric]
                ),
                "company_count": int(count_value or 0),
                "p10": _safe_number(row.get("p10")),
                "p25": _safe_number(row.get("p25")),
                "p50": _safe_number(row.get("p50")),
                "p75": _safe_number(row.get("p75")),
                "p90": _safe_number(row.get("p90")),
                "mean": _safe_number(row.get("mean")),
                "std": _safe_number(row.get("std")),
            }

    if any(metric not in by_metric for metric in CORE_KPIS):
        return []

    return [by_metric[metric] for metric in CORE_KPIS]


def _load_latest_company_kpis() -> list[dict[str, Any]]:
    """Load one latest KPI record for every canonical company."""

    connection = get_connection()

    try:
        company_rows = connection.execute(
            """
            SELECT
                c.id AS company_id,
                COALESCE(s.broad_sector, 'Unknown') AS broad_sector
            FROM companies AS c
            LEFT JOIN sectors AS s
                ON UPPER(s.company_id) = UPPER(c.id)
            ORDER BY c.id
            """
        ).fetchall()

        ratio_rows = connection.execute(
            """
            SELECT
                company_id,
                year,
                return_on_equity_pct,
                return_on_capital_employed_pct,
                net_profit_margin_pct,
                operating_profit_margin_pct,
                debt_to_equity,
                interest_coverage,
                asset_turnover,
                free_cash_flow_cr,
                revenue_cagr_5yr,
                pat_cagr_5yr
            FROM financial_ratios
            """
        ).fetchall()
    finally:
        connection.close()

    latest_by_company: dict[str, Any] = {}

    for row in ratio_rows:
        company_id = str(row["company_id"]).strip().upper()
        current = latest_by_company.get(company_id)

        if current is None or _period_key(row["year"]) > _period_key(
            current["year"]
        ):
            latest_by_company[company_id] = row

    records: list[dict[str, Any]] = []

    for company in company_rows:
        company_id = str(company["company_id"]).strip().upper()
        ratio = latest_by_company.get(company_id)

        record: dict[str, Any] = {
            "company_id": company_id,
            "broad_sector": str(company["broad_sector"] or "Unknown").strip(),
        }

        for metric in CORE_KPIS:
            record[metric] = (
                _safe_number(ratio[metric], 8) if ratio is not None else None
            )

        records.append(record)

    return records


def _impute_missing_values(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Impute missing KPIs with sector medians and global medians."""

    result = [record.copy() for record in records]

    for metric in CORE_KPIS:
        sector_values: dict[str, list[float]] = defaultdict(list)
        global_values: list[float] = []

        for record in result:
            value = record[metric]

            if value is None:
                continue

            numeric_value = float(value)
            sector_values[record["broad_sector"]].append(numeric_value)
            global_values.append(numeric_value)

        if not global_values:
            raise ValueError(f"No usable values found for KPI: {metric}")

        global_median = median(global_values)
        sector_medians = {
            sector: median(values)
            for sector, values in sector_values.items()
            if values
        }

        for record in result:
            if record[metric] is not None:
                continue

            record[metric] = sector_medians.get(
                record["broad_sector"],
                global_median,
            )

    return result


def _calculate_stats_from_database() -> list[dict[str, Any]]:
    """Calculate portfolio percentile statistics from latest database KPIs."""

    records = _impute_missing_values(_load_latest_company_kpis())
    statistics_rows: list[dict[str, Any]] = []

    for metric in CORE_KPIS:
        values = [float(record[metric]) for record in records]

        mean_value = sum(values) / len(values)
        std_value = stdev(values) if len(values) > 1 else 0.0

        statistics_rows.append(
            {
                "metric": metric,
                "metric_label": KPI_LABELS[metric],
                "company_count": len(values),
                "p10": _safe_number(_percentile(values, 0.10)),
                "p25": _safe_number(_percentile(values, 0.25)),
                "p50": _safe_number(_percentile(values, 0.50)),
                "p75": _safe_number(_percentile(values, 0.75)),
                "p90": _safe_number(_percentile(values, 0.90)),
                "mean": _safe_number(mean_value),
                "std": _safe_number(std_value),
            }
        )

    return statistics_rows


@router.get("/stats")
def get_portfolio_stats() -> dict[str, Any]:
    """Return P10-P90 and summary statistics for ten core portfolio KPIs."""

    statistics_rows = _load_precomputed_stats()
    source = "output/portfolio_stats.csv"

    if not statistics_rows:
        statistics_rows = _calculate_stats_from_database()
        source = "computed_from_database"

    company_count = max(
        (int(row["company_count"]) for row in statistics_rows),
        default=0,
    )

    return {
        "company_universe": company_count,
        "kpi_count": len(statistics_rows),
        "percentile_columns": ["p10", "p25", "p50", "p75", "p90"],
        "source": source,
        "statistics": statistics_rows,
    }