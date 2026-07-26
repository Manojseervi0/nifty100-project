from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from src.api.database import get_connection


router = APIRouter(
    tags=["Documents"],
)


def _clean_text(value: object) -> str | None:
    """Return stripped single-line text or None."""

    if value is None:
        return None

    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _is_valid_document_url(value: object) -> bool:
    """Validate the basic structure of an annual-report URL."""

    if value is None:
        return False

    url = str(value).strip()

    if not url or any(character.isspace() for character in url):
        return False

    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    return (
        parsed.scheme.lower() in {"http", "https"}
        and bool(parsed.netloc)
        and bool(parsed.path)
    )


def _get_company(ticker: str) -> dict[str, Any]:
    """Return the canonical company row for a ticker."""

    normalized_ticker = ticker.strip().upper()

    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT
                id AS company_id,
                company_name
            FROM companies
            WHERE UPPER(id) = ?
            LIMIT 1
            """,
            (normalized_ticker,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Company not found: {normalized_ticker}",
        )

    return {
        "company_id": str(row["company_id"]).strip().upper(),
        "company_name": _clean_text(row["company_name"]),
    }


@router.get("/companies/{ticker}/documents")
def get_company_documents(ticker: str) -> dict[str, Any]:
    """Return annual-report links and URL-validity flags for a company."""

    company = _get_company(ticker)

    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                id,
                Year AS report_year,
                Annual_Report AS annual_report_url
            FROM documents
            WHERE UPPER(company_id) = ?
            ORDER BY
                CASE
                    WHEN Year IS NULL THEN 1
                    ELSE 0
                END,
                Year DESC,
                id DESC
            """,
            (company["company_id"],),
        ).fetchall()
    finally:
        connection.close()

    documents: list[dict[str, Any]] = []

    for row in rows:
        raw_url = row["annual_report_url"]
        clean_url = str(raw_url).strip() if raw_url is not None else None
        valid_url = _is_valid_document_url(clean_url)

        documents.append(
            {
                "document_id": str(row["id"]).strip() if row["id"] is not None else None,
                "year": int(row["report_year"]) if row["report_year"] is not None else None,
                "annual_report_url": clean_url,
                "is_url_valid": valid_url,
                "status": "available" if valid_url else "unavailable",
            }
        )

    valid_count = sum(
        1 for document in documents if document["is_url_valid"]
    )

    return {
        **company,
        "document_count": len(documents),
        "valid_url_count": valid_count,
        "invalid_url_count": len(documents) - valid_count,
        "url_validation_method": "format_check",
        "documents": documents,
    }