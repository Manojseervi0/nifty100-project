from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import (
    companies,
    documents,
    health,
    peers,
    portfolio,
    screener,
    sectors,
    valuation,
)


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | %(levelname)s | "
        "%(name)s | %(message)s"
    ),
)

logger = logging.getLogger("nifty100-api")

API_PREFIX = "/api/v1"


app = FastAPI(
    title="Nifty100 Analytics API",
    description=(
        "REST API for company analytics, financial ratios, "
        "screening, peer comparison, sectors, valuation, "
        "documents, and portfolio statistics."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(
    request: Request,
    call_next,
):
    """Log request method, path, status code, and response time."""

    start_time = time.perf_counter()

    response = await call_next(request)

    elapsed_ms = (
        time.perf_counter() - start_time
    ) * 1000

    logger.info(
        "%s %s | status=%s | %.2f ms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )

    response.headers["X-Process-Time-Ms"] = (
        f"{elapsed_ms:.2f}"
    )

    return response


@app.get("/", tags=["Root"])
def root() -> dict[str, str]:
    """Return API status and documentation links."""

    return {
        "message": "Nifty100 Analytics API",
        "status": "running",
        "docs": "/docs",
        "health": f"{API_PREFIX}/health",
    }


# Health
app.include_router(
    health.router,
    prefix=API_PREFIX,
)

# Company data endpoints
app.include_router(
    companies.router,
    prefix=API_PREFIX,
)

# Screener
app.include_router(
    screener.router,
    prefix=API_PREFIX,
)

# Sectors
app.include_router(
    sectors.router,
    prefix=API_PREFIX,
)

# Peer comparison
app.include_router(
    peers.router,
    prefix=API_PREFIX,
)

# Valuation
app.include_router(
    valuation.router,
    prefix=API_PREFIX,
)

# Portfolio statistics
app.include_router(
    portfolio.router,
    prefix=API_PREFIX,
)

# Annual reports and documents
app.include_router(
    documents.router,
    prefix=API_PREFIX,
)