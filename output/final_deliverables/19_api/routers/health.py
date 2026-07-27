from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from src.api.database import fetch_table_counts


router = APIRouter(
    prefix="/health",
    tags=["Health"],
)

APP_START_TIME = time.time()
API_VERSION = "1.0.0"


@router.get("")
def health_check() -> dict:
    """Return API health, database counts, uptime, and version."""

    try:
        table_counts = fetch_table_counts()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Database health check failed: {exc}",
        ) from exc

    return {
        "status": "ok",
        "version": API_VERSION,
        "uptime_seconds": round(
            time.time() - APP_START_TIME,
            2,
        ),
        "db_row_counts": table_counts,
    }