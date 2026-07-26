from __future__ import annotations

API = "/api/v1"


def test_market_cap_history_tcs(client):
    response = client.get(f"{API}/market-cap/TCS")

    assert response.status_code == 200
    body = response.json()
    assert body["from_year"] == 2019
    assert body["to_year"] == 2024
    assert body["record_count"] == 6  # verified directly against market_cap
    assert body["summary"]["latest_pe_ratio"] == 78.69


def test_market_cap_history_unknown_ticker_returns_404(client):
    response = client.get(f"{API}/market-cap/INVALID")

    assert response.status_code == 404


def test_market_cap_history_is_sorted_by_year(client):
    body = client.get(f"{API}/market-cap/TCS").json()
    years = [row["year"] for row in body["history"]]

    assert years == sorted(years)
