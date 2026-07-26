from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from src.api.database import get_connection


router = APIRouter(
    prefix="/companies",
    tags=["Companies"],
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEARSHEET_DIR = PROJECT_ROOT / "reports" / "tearsheets"

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

HISTORY_TABLES = {
    "pl": "profitandloss",
    "bs": "balancesheet",
    "cashflow": "cashflow",
}


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a SQLite row into a regular dictionary."""

    return dict(row)


def _normalise_ticker(ticker: str) -> str:
    """Normalise and validate a company ticker supplied in a URL."""

    cleaned = ticker.strip().upper()

    if not cleaned or not re.fullmatch(r"[A-Z0-9&.-]+", cleaned):
        raise HTTPException(
            status_code=400,
            detail="Invalid ticker format.",
        )

    return cleaned


def _source_period_key(value: object) -> tuple[int, int, int]:
    """Convert source financial-year text into a sortable period key."""

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

    decimal_year = re.fullmatch(r"(19\d{2}|20\d{2})\.5", text)

    if decimal_year:
        return (int(decimal_year.group(1)), 6, 0)

    four_digit_year = re.search(r"\b(19\d{2}|20\d{2})\b", text)

    if four_digit_year:
        return (int(four_digit_year.group(1)), month, 0)

    two_digit_year = re.search(r"(?:-|\s)(\d{2})$", text)

    if two_digit_year:
        year_value = int(two_digit_year.group(1))
        full_year = 2000 + year_value if year_value <= 69 else 1900 + year_value
        return (full_year, month, 0)

    plain_year = re.fullmatch(r"(19\d{2}|20\d{2})", text)

    if plain_year:
        return (int(plain_year.group(1)), 12, 0)

    return (0, 0, 0)


def _parse_query_period(value: str | None, parameter_name: str) -> tuple[int, int] | None:
    """Validate a YYYY-MM query parameter and return its year-month tuple."""

    if value is None:
        return None

    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{parameter_name} must use YYYY-MM format.",
        ) from exc

    return (parsed.year, parsed.month)


def _company_exists(ticker: str) -> bool:
    """Return whether a ticker exists in the canonical company table."""

    connection = get_connection()

    try:
        row = connection.execute(
            "SELECT 1 FROM companies WHERE UPPER(id) = ? LIMIT 1",
            (ticker,),
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def _require_company(ticker: str) -> str:
    """Return a normalised ticker or raise HTTP 404 when it is unknown."""

    normalised = _normalise_ticker(ticker)

    if not _company_exists(normalised):
        raise HTTPException(
            status_code=404,
            detail=f"Company ticker '{normalised}' was not found.",
        )

    return normalised


def _latest_rows_by_company(
    table_name: str,
    selected_columns: list[str],
) -> dict[str, dict[str, Any]]:
    """Return the latest available row from a company-year table."""

    safe_tables = {
        "financial_ratios",
        "market_cap",
    }

    if table_name not in safe_tables:
        raise ValueError(f"Unsupported latest-row table: {table_name}")

    columns_sql = ", ".join(selected_columns)
    connection = get_connection()

    try:
        rows = connection.execute(
            f"SELECT {columns_sql} FROM {table_name}"
        ).fetchall()
    finally:
        connection.close()

    latest: dict[str, dict[str, Any]] = {}

    for row in rows:
        record = _row_to_dict(row)
        company_id = str(record["company_id"]).upper()
        current_key = _source_period_key(record.get("year"))
        previous = latest.get(company_id)

        if previous is None or current_key > _source_period_key(previous.get("year")):
            latest[company_id] = record

    return latest


def _get_company_history(
    ticker: str,
    table_name: str,
    from_year: str | None,
    to_year: str | None,
) -> list[dict[str, Any]]:
    """Return sorted company history with optional inclusive year filters."""

    normalised = _require_company(ticker)
    from_period = _parse_query_period(from_year, "from_year")
    to_period = _parse_query_period(to_year, "to_year")

    if from_period and to_period and from_period > to_period:
        raise HTTPException(
            status_code=400,
            detail="from_year cannot be later than to_year.",
        )

    if table_name not in set(HISTORY_TABLES.values()):
        raise ValueError(f"Unsupported history table: {table_name}")

    connection = get_connection()

    try:
        rows = connection.execute(
            f"SELECT * FROM {table_name} WHERE UPPER(company_id) = ?",
            (normalised,),
        ).fetchall()
    finally:
        connection.close()

    records = [_row_to_dict(row) for row in rows]
    filtered: list[dict[str, Any]] = []

    for record in records:
        year, month, is_ttm = _source_period_key(record.get("year"))

        if is_ttm and (from_period or to_period):
            continue

        comparable = (year, month)

        if from_period and comparable < from_period:
            continue

        if to_period and comparable > to_period:
            continue

        filtered.append(record)

    filtered.sort(key=lambda item: _source_period_key(item.get("year")))
    return filtered


@router.get("")
def list_companies(
    sector: str | None = Query(default=None),
    market_cap_category: str | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1),
) -> list[dict[str, Any]]:
    """Return all companies with optional sector, category, and search filters."""

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                c.id,
                c.company_name,
                s.broad_sector,
                s.sub_sector,
                s.market_cap_category
            FROM companies AS c
            LEFT JOIN sectors AS s
                ON s.company_id = c.id
            ORDER BY c.company_name, c.id
            """
        ).fetchall()
    finally:
        connection.close()

    latest_ratios = _latest_rows_by_company(
        "financial_ratios",
        [
            "company_id",
            "year",
            "return_on_equity_pct",
            "return_on_capital_employed_pct",
        ],
    )

    sector_filter = sector.strip().casefold() if sector else None
    category_filter = (
        market_cap_category.strip().casefold()
        if market_cap_category
        else None
    )
    search_filter = search.strip().casefold() if search else None

    results: list[dict[str, Any]] = []

    for row in rows:
        company = _row_to_dict(row)
        ticker = str(company["id"]).upper()

        if sector_filter and str(company.get("broad_sector") or "").casefold() != sector_filter:
            continue

        if category_filter and str(company.get("market_cap_category") or "").casefold() != category_filter:
            continue

        if search_filter:
            searchable = f"{ticker} {company.get('company_name') or ''}".casefold()
            if search_filter not in searchable:
                continue

        ratio = latest_ratios.get(ticker, {})

        results.append(
            {
                "id": ticker,
                "company_name": company.get("company_name"),
                "broad_sector": company.get("broad_sector"),
                "sub_sector": company.get("sub_sector"),
                "market_cap_category": company.get("market_cap_category"),
                "roe_pct": ratio.get("return_on_equity_pct"),
                "roce_pct": ratio.get("return_on_capital_employed_pct"),
            }
        )

    return results


@router.get("/{ticker}")
def get_company_profile(ticker: str) -> dict[str, Any]:
    """Return a full company profile with sector, KPI, and valuation data."""

    normalised = _require_company(ticker)
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT
                c.*,
                s.broad_sector,
                s.sub_sector,
                s.index_weight_pct,
                s.market_cap_category
            FROM companies AS c
            LEFT JOIN sectors AS s
                ON s.company_id = c.id
            WHERE UPPER(c.id) = ?
            LIMIT 1
            """,
            (normalised,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    company = _row_to_dict(row)
    latest_ratios = _latest_rows_by_company(
        "financial_ratios",
        ["*"],
    ).get(normalised)
    latest_market_cap = _latest_rows_by_company(
        "market_cap",
        ["*"],
    ).get(normalised)

    return {
        "company": company,
        "latest_kpis": latest_ratios,
        "latest_valuation": latest_market_cap,
    }


@router.get("/{ticker}/pl")
def get_profit_and_loss_history(
    ticker: str,
    from_year: str | None = Query(default=None, examples=["2019-03"]),
    to_year: str | None = Query(default=None, examples=["2024-03"]),
) -> list[dict[str, Any]]:
    """Return Profit and Loss history for a company."""

    return _get_company_history(
        ticker,
        HISTORY_TABLES["pl"],
        from_year,
        to_year,
    )


@router.get("/{ticker}/bs")
def get_balance_sheet_history(
    ticker: str,
    from_year: str | None = Query(default=None, examples=["2019-03"]),
    to_year: str | None = Query(default=None, examples=["2024-03"]),
) -> list[dict[str, Any]]:
    """Return Balance Sheet history for a company."""

    return _get_company_history(
        ticker,
        HISTORY_TABLES["bs"],
        from_year,
        to_year,
    )


@router.get("/{ticker}/cashflow")
def get_cash_flow_history(
    ticker: str,
    from_year: str | None = Query(default=None, examples=["2019-03"]),
    to_year: str | None = Query(default=None, examples=["2024-03"]),
) -> list[dict[str, Any]]:
    """Return Cash Flow history for a company."""

    return _get_company_history(
        ticker,
        HISTORY_TABLES["cashflow"],
        from_year,
        to_year,
    )


@router.get("/{ticker}/ratios")
def get_financial_ratios(
    ticker: str,
    year: str | None = Query(
        default=None,
        description="Source year, calendar year, or YYYY-MM period.",
        examples=["2024"],
    ),
) -> dict[str, Any] | list[dict[str, Any]]:
    """Return all ratio history or one requested financial year."""

    normalised = _require_company(ticker)
    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM financial_ratios
            WHERE UPPER(company_id) = ?
            """,
            (normalised,),
        ).fetchall()
    finally:
        connection.close()

    records = [_row_to_dict(row) for row in rows]
    records.sort(key=lambda item: _source_period_key(item.get("year")))

    if year is None:
        return records

    requested = year.strip()

    if not requested:
        raise HTTPException(status_code=400, detail="year cannot be empty.")

    exact_matches = [
        record
        for record in records
        if str(record.get("year", "")).casefold() == requested.casefold()
    ]

    if exact_matches:
        return exact_matches[-1]

    if re.fullmatch(r"\d{4}", requested):
        requested_year = int(requested)
        calendar_matches = [
            record
            for record in records
            if _source_period_key(record.get("year"))[0] == requested_year
        ]

        if calendar_matches:
            calendar_matches.sort(
                key=lambda item: _source_period_key(item.get("year"))
            )
            return calendar_matches[-1]

    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", requested):
        requested_period = _parse_query_period(requested, "year")
        period_matches = [
            record
            for record in records
            if _source_period_key(record.get("year"))[:2] == requested_period
        ]

        if period_matches:
            return period_matches[-1]

    raise HTTPException(
        status_code=404,
        detail=f"No ratio data found for {normalised} in year '{requested}'.",
    )


@router.get("/{ticker}/tearsheet")
def download_tearsheet(ticker: str) -> FileResponse:
    """Download a pre-generated company tearsheet PDF."""

    normalised = _require_company(ticker)
    pdf_path = TEARSHEET_DIR / f"{normalised}_tearsheet.pdf"

    if not pdf_path.exists() or not pdf_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Tearsheet PDF is not available for {normalised}.",
        )

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=pdf_path.name,
    )