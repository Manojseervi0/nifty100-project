from __future__ import annotations

API = "/api/v1"


def test_get_peer_group_it_services(client):
    response = client.get(f"{API}/peers/IT Services")

    assert response.status_code == 200
    body = response.json()
    assert body["company_count"] == 5
    assert body["benchmark_company"]["company_id"] == "TCS"


def test_get_peer_group_is_case_insensitive(client):
    response = client.get(f"{API}/peers/it services")

    assert response.status_code == 200


def test_get_peer_group_unknown_returns_404(client):
    response = client.get(f"{API}/peers/Not A Group")

    assert response.status_code == 404


def test_compare_company_with_peers_tcs(client):
    response = client.get(f"{API}/companies/TCS/peers/compare")

    assert response.status_code == 200
    body = response.json()
    assert body["peer_group_name"] == "IT Services"
    assert len(body["axes"]) == 8  # 8-axis radar per the API contract
    assert body["benchmark_company"]["company_id"] == "TCS"


def test_compare_company_without_peer_group_returns_404(client):
    # A company with no row in peer_groups has no comparison available.
    response = client.get(f"{API}/companies/DOESNOTEXIST/peers/compare")

    assert response.status_code == 404
