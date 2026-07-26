from __future__ import annotations

API = "/api/v1"


def test_screener_min_roe_returns_only_qualifying_companies(client):
    response = client.get(f"{API}/screener", params={"min_roe": 15})

    assert response.status_code == 200
    body = response.json()
    # Verified directly against financial_ratios: 53 of 92 companies have
    # a latest reported ROE >= 15.
    assert body["result_count"] == 53
    assert all(
        company["return_on_equity_pct"] is not None
        and company["return_on_equity_pct"] >= 15
        for company in body["companies"]
    )


def test_screener_no_filters_returns_all_companies(client):
    response = client.get(f"{API}/screener")

    assert response.status_code == 200
    assert response.json()["result_count"] == 92


def test_screener_invalid_numeric_parameter_returns_400(client):
    response = client.get(f"{API}/screener", params={"max_de": -1})

    assert response.status_code == 400


def test_screener_max_pe_zero_returns_400(client):
    response = client.get(f"{API}/screener", params={"max_pe": 0})

    assert response.status_code == 400


def test_screener_unknown_sector_returns_400_with_available_sectors(client):
    response = client.get(f"{API}/screener", params={"sector": "Not A Real Sector"})

    assert response.status_code == 400
    assert "available_sectors" in response.json()["detail"]


def test_screener_max_de_skips_financials_sector(client):
    # High leverage is structurally normal for Financials, so max_de should
    # not exclude them even when their D/E exceeds the threshold.
    response = client.get(f"{API}/screener", params={"max_de": 0.5})

    body = response.json()
    financials = [c for c in body["companies"] if c["sector"] == "Financials"]
    assert len(financials) > 0


def test_screener_results_are_ranked_by_roe_descending(client):
    # Regression test: ranking previously sorted by composite_quality_score,
    # a column financial_ratios does not have, so every row landed in the
    # same "missing score" bucket and results fell back to alphabetical
    # order. Ranking now uses return_on_equity_pct, which is populated.
    body = client.get(f"{API}/screener").json()
    roe_values = [
        c["return_on_equity_pct"]
        for c in body["companies"]
        if c["return_on_equity_pct"] is not None
    ]

    assert roe_values == sorted(roe_values, reverse=True)
