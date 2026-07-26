from __future__ import annotations

API = "/api/v1"


def test_get_company_documents_tcs(client):
    response = client.get(f"{API}/companies/TCS/documents")

    assert response.status_code == 200
    body = response.json()
    assert body["document_count"] == 16  # verified directly against documents


def test_get_company_documents_unknown_ticker_returns_404(client):
    response = client.get(f"{API}/companies/INVALID/documents")

    assert response.status_code == 404


def test_document_counts_are_consistent(client):
    body = client.get(f"{API}/companies/TCS/documents").json()

    assert body["valid_url_count"] + body["invalid_url_count"] == body["document_count"]
