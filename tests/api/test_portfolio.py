from __future__ import annotations

API = "/api/v1"


def test_portfolio_stats_returns_200(client):
    response = client.get(f"{API}/portfolio/stats")

    assert response.status_code == 200


def test_portfolio_stats_covers_92_companies(client):
    body = client.get(f"{API}/portfolio/stats").json()

    assert body["company_universe"] == 92


def test_portfolio_stats_kpi_count_matches_available_columns(client):
    # Regression test: this endpoint used to crash with
    # sqlite3.OperationalError because CORE_KPIS included
    # return_on_capital_employed_pct, revenue_cagr_5yr, and pat_cagr_5yr,
    # none of which exist on financial_ratios. CORE_KPIS is now limited to
    # the 7 columns that are actually present on the table.
    body = client.get(f"{API}/portfolio/stats").json()

    assert body["kpi_count"] == 7
    metrics = {row["metric"] for row in body["statistics"]}
    assert metrics == {
        "return_on_equity_pct",
        "net_profit_margin_pct",
        "operating_profit_margin_pct",
        "debt_to_equity",
        "interest_coverage",
        "asset_turnover",
        "free_cash_flow_cr",
    }


def test_portfolio_stats_percentiles_are_ordered(client):
    body = client.get(f"{API}/portfolio/stats").json()

    for row in body["statistics"]:
        assert row["p10"] <= row["p25"] <= row["p50"] <= row["p75"] <= row["p90"]
