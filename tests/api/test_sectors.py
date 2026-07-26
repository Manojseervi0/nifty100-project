from __future__ import annotations

API = "/api/v1"


def test_list_sectors_returns_exactly_11_sectors(client):
    response = client.get(f"{API}/sectors")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 11
    sector_names = {row["sector"] for row in body}
    assert "Utilities" in sector_names  # split out of Energy sub-sectors


def test_list_sectors_company_counts_sum_to_92(client):
    body = client.get(f"{API}/sectors").json()

    assert sum(row["company_count"] for row in body) == 92


def test_sector_companies_returns_only_that_sector(client):
    response = client.get(f"{API}/sectors/Information Technology/companies")

    assert response.status_code == 200
    body = response.json()
    assert body["company_count"] == 5
    assert all(c["reporting_sector"] == "Information Technology" for c in body["companies"])


def test_sector_alias_it_resolves_to_information_technology(client):
    response = client.get(f"{API}/sectors/IT/companies")

    assert response.status_code == 200
    assert response.json()["sector"] == "Information Technology"


def test_sector_companies_does_not_reference_missing_composite_score(client):
    # Regression test: this endpoint used to crash with
    # sqlite3.OperationalError ("no such column: return_on_capital_employed_pct")
    # because RATIO_COLUMNS selected columns that don't exist on
    # financial_ratios. It must now return 200 and rank by ROE.
    body = client.get(f"{API}/sectors/Information Technology/companies").json()
    companies = body["companies"]

    assert "composite_quality_score" not in companies[0]
    roe_values = [
        c["return_on_equity_pct"] for c in companies if c["return_on_equity_pct"] is not None
    ]
    assert roe_values == sorted(roe_values, reverse=True)


def test_unknown_sector_returns_404(client):
    response = client.get(f"{API}/sectors/NotASector/companies")

    assert response.status_code == 404
