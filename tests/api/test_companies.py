from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_list_companies():
    response = client.get("/api/v1/companies")

    assert response.status_code == 200

    data = response.json()

    assert isinstance(data, list)
    assert len(data) > 0


def test_company_list_schema():
    response = client.get("/api/v1/companies")

    company = response.json()[0]

    expected = {
        "id",
        "company_name",
        "broad_sector",
        "sub_sector",
        "market_cap_category",
        "roe_pct",
        "roce_pct",
    }

    assert expected.issubset(company.keys())


def test_search_company():
    response = client.get(
        "/api/v1/companies",
        params={"search": "TCS"},
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_invalid_search():
    response = client.get(
        "/api/v1/companies",
        params={"search": ""},
    )

    assert response.status_code == 422


def test_company_profile():
    companies = client.get("/api/v1/companies").json()

    ticker = companies[0]["id"]

    response = client.get(f"/api/v1/companies/{ticker}")

    assert response.status_code == 200

    body = response.json()

    assert "company" in body
    assert "latest_kpis" in body
    assert "latest_valuation" in body


def test_invalid_company():
    response = client.get("/api/v1/companies/INVALID123")

    assert response.status_code == 404


def test_profit_loss_history():
    ticker = client.get("/api/v1/companies").json()[0]["id"]

    response = client.get(
        f"/api/v1/companies/{ticker}/pl"
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_balance_sheet_history():
    ticker = client.get("/api/v1/companies").json()[0]["id"]

    response = client.get(
        f"/api/v1/companies/{ticker}/bs"
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_cashflow_history():
    ticker = client.get("/api/v1/companies").json()[0]["id"]

    response = client.get(
        f"/api/v1/companies/{ticker}/cashflow"
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_ratio_history():
    ticker = client.get("/api/v1/companies").json()[0]["id"]

    response = client.get(
        f"/api/v1/companies/{ticker}/ratios"
    )

    assert response.status_code == 200

    assert isinstance(response.json(), list)


def test_ratio_single_year():
    ticker = client.get("/api/v1/companies").json()[0]["id"]

    response = client.get(
        f"/api/v1/companies/{ticker}/ratios",
        params={"year": "2024"},
    )

    assert response.status_code in (200, 404)


def test_invalid_year_format():
    ticker = client.get("/api/v1/companies").json()[0]["id"]

    response = client.get(
        f"/api/v1/companies/{ticker}/pl",
        params={"from_year": "abcd"},
    )

    assert response.status_code == 400


def test_invalid_period_range():
    ticker = client.get("/api/v1/companies").json()[0]["id"]

    response = client.get(
        f"/api/v1/companies/{ticker}/pl",
        params={
            "from_year": "2024-03",
            "to_year": "2020-03",
        },
    )

    assert response.status_code == 400


def test_tearsheet_endpoint():
    ticker = client.get("/api/v1/companies").json()[0]["id"]

    response = client.get(
        f"/api/v1/companies/{ticker}/tearsheet"
    )

    assert response.status_code in (200, 404)