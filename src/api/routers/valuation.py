from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException

from src.api.database import get_connection


router = APIRouter(
    prefix="/market-cap",
    tags=["Valuation"],
)

START_YEAR = 2019
END_YEAR = 2024


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


def _load_company(ticker: str) -> dict[str, Any]:
    """Load canonical company metadata or raise HTTP 404."""

    cleaned_ticker = ticker.strip().upper()

    if not cleaned_ticker:
        raise HTTPException(
            status_code=400,
            detail="Ticker cannot be empty.",
        )

    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT
                c.id AS company_id,
                c.company_name,
                s.broad_sector,
                s.sub_sector,
                s.market_cap_category
            FROM companies AS c
            LEFT JOIN sectors AS s
                ON UPPER(s.company_id) = UPPER(c.id)
            WHERE UPPER(c.id) = ?
            LIMIT 1
            """,
            (cleaned_ticker,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Company not found: {cleaned_ticker}",
        )

    return {
        "company_id": _clean_text(row["company_id"]).upper(),
        "company_name": _clean_text(
            row["company_name"],
            fallback=cleaned_ticker,
        ),
        "sector": _clean_text(row["broad_sector"], fallback="Unknown"),
        "sub_sector": _clean_text(row["sub_sector"], fallback="Unknown"),
        "market_cap_category": _clean_text(
            row["market_cap_category"],
            fallback="Unknown",
        ),
    }


def _load_market_cap_history(ticker: str) -> list[dict[str, Any]]:
    """Load valuation history for the configured 2019-2024 window."""

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                year,
                market_cap_crore,
                enterprise_value_crore,
                pe_ratio,
                pb_ratio,
                ev_ebitda,
                dividend_yield_pct
            FROM market_cap
            WHERE UPPER(company_id) = ?
              AND year BETWEEN ? AND ?
            ORDER BY year ASC
            """,
            (ticker.upper(), START_YEAR, END_YEAR),
        ).fetchall()
    finally:
        connection.close()

    return [
        {
            "year": int(row["year"]),
            "market_cap_crore": _safe_number(row["market_cap_crore"], 2),
            "enterprise_value_crore": _safe_number(
                row["enterprise_value_crore"],
                2,
            ),
            "pe_ratio": _safe_number(row["pe_ratio"], 2),
            "pb_ratio": _safe_number(row["pb_ratio"], 2),
            "ev_ebitda": _safe_number(row["ev_ebitda"], 2),
            "dividend_yield_pct": _safe_number(
                row["dividend_yield_pct"],
                2,
            ),
        }
        for row in rows
    ]


def _build_summary(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Build latest and period-summary valuation statistics."""

    latest = history[-1] if history else None

    pe_values = [
        float(row["pe_ratio"])
        for row in history
        if row["pe_ratio"] is not None
    ]
    pb_values = [
        float(row["pb_ratio"])
        for row in history
        if row["pb_ratio"] is not None
    ]
    ev_ebitda_values = [
        float(row["ev_ebitda"])
        for row in history
        if row["ev_ebitda"] is not None
    ]
    dividend_values = [
        float(row["dividend_yield_pct"])
        for row in history
        if row["dividend_yield_pct"] is not None
    ]

    def average(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    return {
        "latest_year": latest["year"] if latest else None,
        "latest_pe_ratio": latest["pe_ratio"] if latest else None,
        "latest_pb_ratio": latest["pb_ratio"] if latest else None,
        "latest_ev_ebitda": latest["ev_ebitda"] if latest else None,
        "latest_dividend_yield_pct": (
            latest["dividend_yield_pct"] if latest else None
        ),
        "period_average_pe_ratio": average(pe_values),
        "period_average_pb_ratio": average(pb_values),
        "period_average_ev_ebitda": average(ev_ebitda_values),
        "period_average_dividend_yield_pct": average(dividend_values),
    }


@router.get("/{ticker}")
def get_market_cap_history(ticker: str) -> dict[str, Any]:
    """Return 2019-2024 valuation history for one company."""

    company = _load_company(ticker)
    history = _load_market_cap_history(company["company_id"])

    if not history:
        raise HTTPException(
            status_code=404,
            detail=(
                "Market-cap history not found for "
                f"{company['company_id']} between {START_YEAR} and {END_YEAR}."
            ),
        )

    return {
        **company,
        "from_year": START_YEAR,
        "to_year": END_YEAR,
        "record_count": len(history),
        "summary": _build_summary(history),
        "history": history,
    }