from __future__ import annotations

import math
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.api.database import get_connection


router = APIRouter(
    prefix="/screener",
    tags=["Screener"],
)

FINANCIAL_SECTOR = "Financials"


def _period_key(value: object) -> tuple[int, int, int]:
    """Convert a financial-year value into a sortable key."""

    if value is None:
        return (0, 0, 0)

    text = str(value).strip()

    if not text:
        return (0, 0, 0)

    if text.upper() == "TTM":
        return (9999, 12, 1)

    month_numbers = {
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

    month = 12
    month_match = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b",
        text,
        flags=re.IGNORECASE,
    )

    if month_match:
        month = month_numbers[month_match.group(1).lower()]

    four_digit_year = re.search(r"\b(19\d{2}|20\d{2})\b", text)

    if four_digit_year:
        return (int(four_digit_year.group(1)), month, 0)

    two_digit_year = re.search(r"(?:-|\s)(\d{2})$", text)

    if two_digit_year:
        short_year = int(two_digit_year.group(1))
        full_year = 2000 + short_year if short_year <= 69 else 1900 + short_year
        return (full_year, month, 0)

    return (0, 0, 0)


def _latest_by_company(rows: list[Any]) -> dict[str, dict[str, Any]]:
    """Return the latest available record for every company."""

    latest: dict[str, dict[str, Any]] = {}

    for row in rows:
        record = dict(row)
        company_id = str(record["company_id"]).upper()
        previous = latest.get(company_id)

        if previous is None or _period_key(record.get("year")) > _period_key(
            previous.get("year")
        ):
            latest[company_id] = record

    return latest


def _validate_finite(name: str, value: float | None) -> None:
    """Reject NaN and infinite numeric query parameters."""

    if value is not None and not math.isfinite(value):
        raise HTTPException(
            status_code=400,
            detail=f"{name} must be a finite number.",
        )


def _validate_filters(
    min_roe: float | None,
    max_de: float | None,
    min_fcf: float | None,
    min_rev_cagr_5yr: float | None,
    min_pat_cagr_5yr: float | None,
    max_pe: float | None,
) -> None:
    """Validate screener query parameters and raise HTTP 400 when invalid."""

    values = {
        "min_roe": min_roe,
        "max_de": max_de,
        "min_fcf": min_fcf,
        "min_rev_cagr_5yr": min_rev_cagr_5yr,
        "min_pat_cagr_5yr": min_pat_cagr_5yr,
        "max_pe": max_pe,
    }

    for name, value in values.items():
        _validate_finite(name, value)

    if max_de is not None and max_de < 0:
        raise HTTPException(
            status_code=400,
            detail="max_de cannot be negative.",
        )

    if max_pe is not None and max_pe <= 0:
        raise HTTPException(
            status_code=400,
            detail="max_pe must be greater than zero.",
        )


def _passes_minimum(value: Any, threshold: float | None) -> bool:
    """Return whether a numeric value meets an optional minimum threshold."""

    if threshold is None:
        return True

    return value is not None and float(value) >= threshold


def _passes_maximum(value: Any, threshold: float | None) -> bool:
    """Return whether a numeric value meets an optional maximum threshold."""

    if threshold is None:
        return True

    return value is not None and float(value) <= threshold


@router.get("")
def run_screener(
    min_roe: float | None = Query(default=None),
    max_de: float | None = Query(default=None),
    min_fcf: float | None = Query(default=None),
    sector: str | None = Query(default=None, min_length=1),
    min_rev_cagr_5yr: float | None = Query(default=None),
    min_pat_cagr_5yr: float | None = Query(default=None),
    max_pe: float | None = Query(default=None),
) -> dict[str, Any]:
    """Return a ranked company list matching the supplied financial filters."""

    _validate_filters(
        min_roe=min_roe,
        max_de=max_de,
        min_fcf=min_fcf,
        min_rev_cagr_5yr=min_rev_cagr_5yr,
        min_pat_cagr_5yr=min_pat_cagr_5yr,
        max_pe=max_pe,
    )

    connection = get_connection()

    try:
        company_rows = connection.execute(
            """
            SELECT
                c.id AS company_id,
                c.company_name,
                s.broad_sector AS sector,
                s.sub_sector,
                s.market_cap_category
            FROM companies AS c
            LEFT JOIN sectors AS s
                ON UPPER(s.company_id) = UPPER(c.id)
            ORDER BY c.company_name, c.id
            """
        ).fetchall()

        ratio_rows = connection.execute(
            """
            SELECT
                company_id,
                year,
                return_on_equity_pct,
                debt_to_equity,
                free_cash_flow_cr
            FROM financial_ratios
            """
        ).fetchall()

        market_rows = connection.execute(
            """
            SELECT
                company_id,
                year,
                pe_ratio
            FROM market_cap
            """
        ).fetchall()
    finally:
        connection.close()

    available_sectors = sorted(
        {
            str(row["sector"]).strip()
            for row in company_rows
            if row["sector"] is not None and str(row["sector"]).strip()
        }
    )

    selected_sector: str | None = None

    if sector is not None:
        requested = sector.strip()
        selected_sector = next(
            (
                candidate
                for candidate in available_sectors
                if candidate.casefold() == requested.casefold()
            ),
            None,
        )

        if selected_sector is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"Unknown sector: {requested}",
                    "available_sectors": available_sectors,
                },
            )

    latest_ratios = _latest_by_company(ratio_rows)
    latest_market = _latest_by_company(market_rows)
    results: list[dict[str, Any]] = []

    for company_row in company_rows:
        company = dict(company_row)
        company_id = str(company["company_id"]).upper()
        company_sector = company.get("sector")

        if selected_sector is not None and company_sector != selected_sector:
            continue

        ratio = latest_ratios.get(company_id, {})
        market = latest_market.get(company_id, {})

        roe = ratio.get("return_on_equity_pct")
        de = ratio.get("debt_to_equity")
        fcf = ratio.get("free_cash_flow_cr")
        revenue_cagr = ratio.get("revenue_cagr_5yr")
        pat_cagr = ratio.get("pat_cagr_5yr")
        pe = market.get("pe_ratio")

        if not _passes_minimum(roe, min_roe):
            continue

        # High leverage is structurally normal for Financials, so the D/E
        # maximum is not applied to companies in that sector.
        if (
            max_de is not None
            and company_sector != FINANCIAL_SECTOR
            and not _passes_maximum(de, max_de)
        ):
            continue

        if not _passes_minimum(fcf, min_fcf):
            continue

        if not _passes_minimum(revenue_cagr, min_rev_cagr_5yr):
            continue

        if not _passes_minimum(pat_cagr, min_pat_cagr_5yr):
            continue

        if not _passes_maximum(pe, max_pe):
            continue

        results.append(
            {
                "company_id": company_id,
                "company_name": company.get("company_name"),
                "sector": company_sector,
                "sub_sector": company.get("sub_sector"),
                "market_cap_category": company.get("market_cap_category"),
                "ratio_year": ratio.get("year"),
                "market_cap_year": market.get("year"),
                "return_on_equity_pct": roe,
                "debt_to_equity": de,
                "free_cash_flow_cr": fcf,
                "revenue_cagr_5yr": revenue_cagr,
                "pat_cagr_5yr": pat_cagr,
                "pe_ratio": pe,
                "composite_quality_score": ratio.get("composite_quality_score"),
            }
        )

    results.sort(
        key=lambda item: (
            item["composite_quality_score"] is None,
            -float(item["composite_quality_score"] or 0),
            str(item["company_name"] or item["company_id"]),
        )
    )

    ranked_results: list[dict[str, Any]] = []

    for rank, item in enumerate(results, start=1):
        ranked_results.append({"rank": rank, **item})

    return {
        "result_count": len(ranked_results),
        "filters": {
            "min_roe": min_roe,
            "max_de": max_de,
            "min_fcf": min_fcf,
            "sector": selected_sector,
            "min_rev_cagr_5yr": min_rev_cagr_5yr,
            "min_pat_cagr_5yr": min_pat_cagr_5yr,
            "max_pe": max_pe,
        },
        "companies": ranked_results,
    }