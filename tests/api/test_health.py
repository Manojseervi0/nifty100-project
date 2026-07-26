from __future__ import annotations

API = "/api/v1"

# Verified directly against nifty100.db: 13 tables exist (analysis,
# balancesheet, cashflow, companies, documents, financial_ratios,
# market_cap, peer_groups, peer_percentiles, profitandloss, prosandcons,
# sectors, stock_prices). The Day-42 test plan assumed 10 tables — that
# assumption predates the real schema and is corrected here.
EXPECTED_TABLES = {
    "analysis",
    "balancesheet",
    "cashflow",
    "companies",
    "documents",
    "financial_ratios",
    "market_cap",
    "peer_groups",
    "peer_percentiles",
    "profitandloss",
    "prosandcons",
    "sectors",
    "stock_prices",
}


def test_health_returns_200_with_ok_status(client):
    response = client.get(f"{API}/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_health_reports_all_known_tables(client):
    body = client.get(f"{API}/health").json()

    assert set(body["db_row_counts"].keys()) == EXPECTED_TABLES
    # Every table should have a non-negative row count and companies
    # specifically must be non-empty for the rest of the API to work.
    assert body["db_row_counts"]["companies"] == 92
    for count in body["db_row_counts"].values():
        assert count >= 0


def test_health_includes_version_and_uptime(client):
    body = client.get(f"{API}/health").json()

    assert "version" in body
    assert body["uptime_seconds"] >= 0
