from __future__ import annotations

import math
import re
from statistics import median
from typing import Any

from fastapi import APIRouter, HTTPException

from src.api.database import get_connection


router = APIRouter(
    prefix="/sectors",
    tags=["Sectors"],
)

UTILITY_SUBSECTORS = {
    "power & utilities",
    "power transmission",
    "renewable energy",
}

SECTOR_ALIASES = {
    "it": "Information Technology",
    "information tech": "Information Technology",
    "technology": "Information Technology",
    "fmcg": "Consumer Staples",
    "consumer staples": "Consumer Staples",
    "consumer discretionary": "Consumer Discretionary",
    "financial": "Financials",
    "finance": "Financials",
    "health": "Healthcare",
    "health care": "Healthcare",
    "realty": "Real Estate",
    "telecom": "Communication Services",
    "communication": "Communication Services",
    "utility": "Utilities",
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

RATIO_COLUMNS = [
    "company_id",
    "year",
    "return_on_equity_pct",
    "net_profit_margin_pct",
    "debt_to_equity",
    "free_cash_flow_cr",
    "operating_profit_margin_pct",
]

MARKET_CAP_COLUMNS = [
    "company_id",
    "year",
    "market_cap_crore",
    "pe_ratio",
    "pb_ratio",
    "ev_ebitda",
    "dividend_yield_pct",
]


def _clean_text(value: object, fallback: str = "Unknown") -> str:
    """Return a trimmed single-line string for API output."""

    if value is None:
        return fallback

    cleaned = " ".join(str(value).split())
    return cleaned or fallback


def _safe_number(value: object, digits: int = 2) -> float | int | None:
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
    """Convert source year text into a sortable key."""

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

    short_year = re.search(r"(?:-|\s)(\d{2})$", text)

    if short_year:
        value_2d = int(short_year.group(1))
        full_year = 2000 + value_2d if value_2d <= 69 else 1900 + value_2d
        return (full_year, month, 0)

    return (0, 0, 0)


def _reporting_sector(broad_sector: object, sub_sector: object) -> str:
    """Map source sectors into the 11 reporting sectors."""

    broad = _clean_text(broad_sector)
    sub = _clean_text(sub_sector, fallback="").lower()

    if broad.lower() == "energy" and sub in UTILITY_SUBSECTORS:
        return "Utilities"

    return broad


def _normalise_sector_key(value: str) -> str:
    """Normalise a sector path parameter for matching and aliases."""

    cleaned = value.strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(cleaned.split())


def _latest_rows(
    table_name: str,
    selected_columns: list[str],
) -> dict[str, dict[str, Any]]:
    """Return the latest row per company from a supported table."""

    if table_name not in {"financial_ratios", "market_cap"}:
        raise ValueError(f"Unsupported table: {table_name}")

    connection = get_connection()

    try:
        rows = connection.execute(
            f"SELECT {', '.join(selected_columns)} FROM {table_name}"
        ).fetchall()
    finally:
        connection.close()

    latest: dict[str, dict[str, Any]] = {}

    for row in rows:
        record = dict(row)
        company_id = _clean_text(record.get("company_id"), fallback="").upper()

        if not company_id:
            continue

        current_key = _period_key(record.get("year"))
        previous = latest.get(company_id)

        if previous is None or current_key > _period_key(previous.get("year")):
            latest[company_id] = record

    return latest


def _load_company_universe() -> list[dict[str, Any]]:
    """Load all canonical companies with their reporting-sector metadata."""

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                c.id AS company_id,
                c.company_name,
                s.broad_sector,
                s.sub_sector,
                s.market_cap_category,
                s.index_weight_pct
            FROM companies c
            LEFT JOIN sectors s
                ON UPPER(s.company_id) = UPPER(c.id)
            ORDER BY UPPER(c.id)
            """
        ).fetchall()
    finally:
        connection.close()

    companies: list[dict[str, Any]] = []

    for row in rows:
        record = dict(row)
        broad_sector = _clean_text(record.get("broad_sector"))
        sub_sector = _clean_text(record.get("sub_sector"))

        companies.append(
            {
                "company_id": _clean_text(record.get("company_id"), fallback="").upper(),
                "company_name": _clean_text(record.get("company_name")),
                "broad_sector": broad_sector,
                "reporting_sector": _reporting_sector(broad_sector, sub_sector),
                "sub_sector": sub_sector,
                "market_cap_category": _clean_text(
                    record.get("market_cap_category"),
                    fallback="N/A",
                ),
                "index_weight_pct": _safe_number(record.get("index_weight_pct"), 4),
            }
        )

    return companies


def _median_value(values: list[object]) -> float | int | None:
    """Return a rounded median after excluding null and non-finite values."""

    valid: list[float] = []

    for value in values:
        safe = _safe_number(value, digits=8)

        if safe is not None:
            valid.append(float(safe))

    if not valid:
        return None

    return _safe_number(median(valid), digits=2)


def _build_company_records() -> list[dict[str, Any]]:
    """Merge the company universe with latest ratio and valuation data."""

    companies = _load_company_universe()
    latest_ratios = _latest_rows("financial_ratios", RATIO_COLUMNS)
    latest_market_cap = _latest_rows("market_cap", MARKET_CAP_COLUMNS)
    records: list[dict[str, Any]] = []

    for company in companies:
        ticker = company["company_id"]
        ratios = latest_ratios.get(ticker, {})
        valuation = latest_market_cap.get(ticker, {})

        records.append(
            {
                **company,
                "ratio_year": ratios.get("year"),
                "market_cap_year": valuation.get("year"),
                "return_on_equity_pct": _safe_number(
                    ratios.get("return_on_equity_pct")
                ),
                "net_profit_margin_pct": _safe_number(
                    ratios.get("net_profit_margin_pct")
                ),
                "operating_profit_margin_pct": _safe_number(
                    ratios.get("operating_profit_margin_pct")
                ),
                "debt_to_equity": _safe_number(ratios.get("debt_to_equity"), 4),
                "free_cash_flow_cr": _safe_number(ratios.get("free_cash_flow_cr")),
                "market_cap_crore": _safe_number(
                    valuation.get("market_cap_crore")
                ),
                "pe_ratio": _safe_number(valuation.get("pe_ratio")),
                "pb_ratio": _safe_number(valuation.get("pb_ratio")),
                "ev_ebitda": _safe_number(valuation.get("ev_ebitda")),
                "dividend_yield_pct": _safe_number(
                    valuation.get("dividend_yield_pct")
                ),
            }
        )

    return records


def _resolve_sector_name(
    requested_sector: str,
    available_sectors: list[str],
) -> str:
    """Resolve a path value to a canonical reporting-sector name."""

    requested_key = _normalise_sector_key(requested_sector)
    alias_target = SECTOR_ALIASES.get(requested_key)

    if alias_target and alias_target in available_sectors:
        return alias_target

    lookup = {
        _normalise_sector_key(sector_name): sector_name
        for sector_name in available_sectors
    }

    resolved = lookup.get(requested_key)

    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown sector: {requested_sector}",
        )

    return resolved


@router.get("")
def list_sectors() -> list[dict[str, Any]]:
    """Return all 11 reporting sectors with company counts and median KPIs."""

    records = _build_company_records()
    grouped: dict[str, list[dict[str, Any]]] = {}

    for record in records:
        grouped.setdefault(record["reporting_sector"], []).append(record)

    result: list[dict[str, Any]] = []

    for sector_name in sorted(grouped):
        sector_rows = grouped[sector_name]
        result.append(
            {
                "sector": sector_name,
                "company_count": len(sector_rows),
                "median_roe": _median_value(
                    [row["return_on_equity_pct"] for row in sector_rows]
                ),
                "median_pe": _median_value(
                    [row["pe_ratio"] for row in sector_rows]
                ),
                "median_de": _median_value(
                    [row["debt_to_equity"] for row in sector_rows]
                ),
            }
        )

    return result


@router.get("/{sector}/companies")
def list_sector_companies(sector: str) -> dict[str, Any]:
    """Return all companies and latest KPIs for a reporting sector."""

    records = _build_company_records()
    available_sectors = sorted(
        {record["reporting_sector"] for record in records}
    )
    resolved_sector = _resolve_sector_name(sector, available_sectors)
    companies = [
        record
        for record in records
        if record["reporting_sector"] == resolved_sector
    ]

    # NOTE: there is no composite_quality_score column on financial_ratios
    # (confirmed against schema); ranking uses return_on_equity_pct, which
    # is populated for every company, as the interim ranking signal.
    companies.sort(
        key=lambda row: (
            row["return_on_equity_pct"] is None,
            -(row["return_on_equity_pct"] or 0),
            row["company_id"],
        )
    )

    for rank, company in enumerate(companies, start=1):
        company["rank"] = rank

    return {
        "sector": resolved_sector,
        "company_count": len(companies),
        "companies": companies,
    }