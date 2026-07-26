from __future__ import annotations

import math
import re
from collections import defaultdict
from statistics import mean
from typing import Any

from fastapi import APIRouter, HTTPException

from src.api.database import get_connection


router = APIRouter(
    tags=["Peers"],
)

PEER_METRICS = [
    "return_on_equity_pct",
    "return_on_capital_employed_pct",
    "net_profit_margin_pct",
    "debt_to_equity",
    "free_cash_flow_cr",
    "pat_cagr_5yr",
    "revenue_cagr_5yr",
    "eps_cagr_5yr",
    "interest_coverage",
    "asset_turnover",
]

RADAR_METRICS = [
    "return_on_equity_pct",
    "return_on_capital_employed_pct",
    "net_profit_margin_pct",
    "debt_to_equity",
    "free_cash_flow_cr",
    "pat_cagr_5yr",
    "revenue_cagr_5yr",
    "asset_turnover",
]

METRIC_LABELS = {
    "return_on_equity_pct": "ROE",
    "return_on_capital_employed_pct": "ROCE",
    "net_profit_margin_pct": "Net Profit Margin",
    "debt_to_equity": "Debt-to-Equity",
    "free_cash_flow_cr": "Free Cash Flow",
    "pat_cagr_5yr": "PAT CAGR 5Y",
    "revenue_cagr_5yr": "Revenue CAGR 5Y",
    "eps_cagr_5yr": "EPS CAGR 5Y",
    "interest_coverage": "Interest Coverage",
    "asset_turnover": "Asset Turnover",
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


def _clean_text(value: object, fallback: str = "") -> str:
    """Return a trimmed single-line string for API output."""

    if value is None:
        return fallback

    cleaned = " ".join(str(value).split())
    return cleaned or fallback


def _safe_number(value: object, digits: int = 4) -> float | int | None:
    """Convert a value into a finite JSON-safe number."""

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
    """Convert a source financial period into a sortable key."""

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
        year_2d = int(short_year_match.group(1))
        full_year = 2000 + year_2d if year_2d <= 69 else 1900 + year_2d
        return (full_year, month, 0)

    return (0, 0, 0)


def _normalise_group_key(value: str) -> str:
    """Normalise a peer-group path value for case-insensitive matching."""

    cleaned = value.strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(cleaned.split())


def _resolve_peer_group(group_name: str) -> str:
    """Resolve a peer-group name case-insensitively or raise HTTP 404."""

    requested_key = _normalise_group_key(group_name)

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT DISTINCT peer_group_name
            FROM peer_groups
            ORDER BY peer_group_name
            """
        ).fetchall()
    finally:
        connection.close()

    for row in rows:
        actual_name = _clean_text(row["peer_group_name"])

        if _normalise_group_key(actual_name) == requested_key:
            return actual_name

    raise HTTPException(
        status_code=404,
        detail=f"Peer group not found: {group_name}",
    )


def _load_group_members(group_name: str) -> list[dict[str, Any]]:
    """Load companies and benchmark metadata for one peer group."""

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                pg.company_id,
                c.company_name,
                pg.is_benchmark
            FROM peer_groups AS pg
            LEFT JOIN companies AS c
                ON UPPER(c.id) = UPPER(pg.company_id)
            WHERE LOWER(pg.peer_group_name) = LOWER(?)
            ORDER BY pg.is_benchmark DESC, c.company_name, pg.company_id
            """,
            (group_name,),
        ).fetchall()
    finally:
        connection.close()

    return [
        {
            "company_id": _clean_text(row["company_id"]).upper(),
            "company_name": _clean_text(
                row["company_name"],
                fallback=_clean_text(row["company_id"]).upper(),
            ),
            "is_benchmark": bool(row["is_benchmark"]),
        }
        for row in rows
    ]


def _load_latest_percentiles(group_name: str) -> dict[str, dict[str, dict[str, Any]]]:
    """Return latest peer-percentile records by company and metric."""

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                company_id,
                peer_group_name,
                metric,
                value,
                percentile_rank,
                year,
                is_benchmark
            FROM peer_percentiles
            WHERE LOWER(peer_group_name) = LOWER(?)
            """,
            (group_name,),
        ).fetchall()
    finally:
        connection.close()

    latest: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    for row in rows:
        company_id = _clean_text(row["company_id"]).upper()
        metric = _clean_text(row["metric"])

        if not company_id or metric not in PEER_METRICS:
            continue

        record = dict(row)
        existing = latest[company_id].get(metric)

        if existing is None or _period_key(record.get("year")) > _period_key(
            existing.get("year")
        ):
            latest[company_id][metric] = record

    return dict(latest)


def _metric_payload(record: dict[str, Any] | None) -> dict[str, Any]:
    """Build one JSON-safe peer metric payload."""

    if record is None:
        return {
            "value": None,
            "percentile_rank": None,
            "percentile_pct": None,
            "year": None,
        }

    percentile_rank = _safe_number(record.get("percentile_rank"), digits=6)

    return {
        "value": _safe_number(record.get("value")),
        "percentile_rank": percentile_rank,
        "percentile_pct": (
            _safe_number(float(percentile_rank) * 100, digits=2)
            if percentile_rank is not None
            else None
        ),
        "year": _clean_text(record.get("year"), fallback="Unknown"),
    }


def _company_group(ticker: str) -> tuple[str, str, bool]:
    """Return the company name, assigned peer group, and benchmark flag."""

    cleaned_ticker = ticker.strip().upper()

    connection = get_connection()

    try:
        company_row = connection.execute(
            """
            SELECT id, company_name
            FROM companies
            WHERE UPPER(id) = ?
            """,
            (cleaned_ticker,),
        ).fetchone()

        if company_row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Company not found: {cleaned_ticker}",
            )

        group_row = connection.execute(
            """
            SELECT peer_group_name, is_benchmark
            FROM peer_groups
            WHERE UPPER(company_id) = ?
            """,
            (cleaned_ticker,),
        ).fetchone()
    finally:
        connection.close()

    if group_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No peer group assigned to company: {cleaned_ticker}",
        )

    return (
        _clean_text(company_row["company_name"], fallback=cleaned_ticker),
        _clean_text(group_row["peer_group_name"]),
        bool(group_row["is_benchmark"]),
    )


@router.get("/peers/{group_name}")
def get_peer_group(group_name: str) -> dict[str, Any]:
    """Return latest percentile ranks for all companies in a peer group."""

    resolved_group = _resolve_peer_group(group_name)
    members = _load_group_members(resolved_group)
    percentile_data = _load_latest_percentiles(resolved_group)

    if not members:
        raise HTTPException(
            status_code=404,
            detail=f"Peer group contains no companies: {resolved_group}",
        )

    benchmark = next(
        (member for member in members if member["is_benchmark"]),
        None,
    )

    company_payloads = []

    for member in members:
        company_id = member["company_id"]
        metric_records = percentile_data.get(company_id, {})
        metrics = {
            metric: _metric_payload(metric_records.get(metric))
            for metric in PEER_METRICS
        }

        available_percentiles = [
            payload["percentile_pct"]
            for payload in metrics.values()
            if payload["percentile_pct"] is not None
        ]

        company_payloads.append(
            {
                **member,
                "average_percentile_pct": (
                    _safe_number(mean(available_percentiles), digits=2)
                    if available_percentiles
                    else None
                ),
                "metrics": metrics,
            }
        )

    company_payloads.sort(
        key=lambda item: (
            item["average_percentile_pct"] is None,
            -float(item["average_percentile_pct"] or 0),
            item["company_id"],
        )
    )

    return {
        "peer_group_name": resolved_group,
        "company_count": len(company_payloads),
        "benchmark_company": benchmark,
        "metric_count": len(PEER_METRICS),
        "metrics": [
            {
                "metric": metric,
                "label": METRIC_LABELS[metric],
            }
            for metric in PEER_METRICS
        ],
        "companies": company_payloads,
    }


@router.get("/companies/{ticker}/peers/compare")
def compare_company_with_peers(ticker: str) -> dict[str, Any]:
    """Return eight-axis radar data for a company, its peers, and benchmark."""

    cleaned_ticker = ticker.strip().upper()
    company_name, peer_group_name, is_benchmark = _company_group(cleaned_ticker)
    members = _load_group_members(peer_group_name)
    percentile_data = _load_latest_percentiles(peer_group_name)

    benchmark = next(
        (member for member in members if member["is_benchmark"]),
        None,
    )

    if benchmark is None:
        raise HTTPException(
            status_code=404,
            detail=f"Benchmark company not configured for peer group: {peer_group_name}",
        )

    benchmark_id = benchmark["company_id"]

    axes = []

    for metric in RADAR_METRICS:
        company_record = percentile_data.get(cleaned_ticker, {}).get(metric)
        benchmark_record = percentile_data.get(benchmark_id, {}).get(metric)

        group_records = [
            metric_map[metric]
            for metric_map in percentile_data.values()
            if metric in metric_map
        ]

        group_values = [
            float(record["value"])
            for record in group_records
            if _safe_number(record.get("value")) is not None
        ]
        group_percentiles = [
            float(record["percentile_rank"]) * 100
            for record in group_records
            if _safe_number(record.get("percentile_rank")) is not None
        ]

        company_metric = _metric_payload(company_record)
        benchmark_metric = _metric_payload(benchmark_record)

        axes.append(
            {
                "metric": metric,
                "label": METRIC_LABELS[metric],
                "company_value": company_metric["value"],
                "company_percentile_pct": company_metric["percentile_pct"],
                "peer_average_value": (
                    _safe_number(mean(group_values)) if group_values else None
                ),
                "peer_average_percentile_pct": (
                    _safe_number(mean(group_percentiles), digits=2)
                    if group_percentiles
                    else None
                ),
                "benchmark_value": benchmark_metric["value"],
                "benchmark_percentile_pct": benchmark_metric["percentile_pct"],
                "year": company_metric["year"],
            }
        )

    return {
        "company": {
            "company_id": cleaned_ticker,
            "company_name": company_name,
            "is_benchmark": is_benchmark,
        },
        "peer_group_name": peer_group_name,
        "peer_company_count": len(members),
        "benchmark_company": benchmark,
        "radar_scale": "percentile_0_to_100",
        "axes": axes,
    }