from __future__ import annotations

"""Day 43 — End-to-end check: FastAPI (8000) and Streamlit (8501) running
side-by-side without port conflicts, and the API is reachable for the
dashboard to consume.

CAVEAT: this script does not have access to your Streamlit app's source
code, so it cannot literally instrument "the dashboard calls the API and
renders it." What it verifies instead, and prints as separate PASS/FAIL
checks:
  1. FastAPI is listening on port 8000 and /api/v1/health returns 200.
  2. Streamlit is listening on port 8501 and serves its page.
  3. Both ports are up at the same time (no port conflict).
  4. The screener endpoint the dashboard's screener page calls returns a
     well-formed response — proving the API is reachable and functional
     from the same host/network path Streamlit runs on.

If you want a stronger check than #4 (literally confirming Streamlit
rendered the API's data), add a `data-testid` or similar marker to your
Streamlit screener table and extend dashboard_perf.py's selenium mode to
assert on it — that requires your app's actual markup, which wasn't
provided here.

Run directly:
    python tests/performance/e2e_test.py
    python tests/performance/e2e_test.py --api-url http://localhost:8000 --streamlit-url http://localhost:8501
"""

import argparse
import socket
from pathlib import Path
from urllib.parse import urlparse

import requests

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_STREAMLIT_URL = "http://localhost:8501"
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "output" / "perf_notes.md"


def _port_is_open(url: str, timeout: float = 3.0) -> bool:
    """Return whether a TCP connection to the URL's host:port succeeds."""

    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_fastapi_running(api_url: str) -> dict:
    """Check FastAPI is listening and /api/v1/health returns 200."""

    if not _port_is_open(api_url):
        return {"name": "FastAPI port reachable", "passed": False, "detail": "connection refused"}

    try:
        response = requests.get(f"{api_url}/api/v1/health", timeout=5)
        passed = response.status_code == 200 and response.json().get("status") == "ok"
        detail = f"HTTP {response.status_code}"
    except requests.RequestException as exc:
        passed = False
        detail = str(exc)

    return {"name": "FastAPI /api/v1/health returns 200 (status=ok)", "passed": passed, "detail": detail}


def check_streamlit_running(streamlit_url: str) -> dict:
    """Check Streamlit is listening and serves its base page."""

    if not _port_is_open(streamlit_url):
        return {"name": "Streamlit port reachable", "passed": False, "detail": "connection refused"}

    try:
        response = requests.get(streamlit_url, timeout=5)
        passed = response.status_code == 200
        detail = f"HTTP {response.status_code}"
    except requests.RequestException as exc:
        passed = False
        detail = str(exc)

    return {"name": "Streamlit serves its base page", "passed": passed, "detail": detail}


def check_no_port_conflict(api_url: str, streamlit_url: str) -> dict:
    """Check both services are simultaneously reachable on their own ports."""

    api_parsed = urlparse(api_url)
    streamlit_parsed = urlparse(streamlit_url)

    if api_parsed.port == streamlit_parsed.port:
        return {
            "name": "FastAPI and Streamlit run on distinct ports",
            "passed": False,
            "detail": f"both configured for port {api_parsed.port}",
        }

    both_up = _port_is_open(api_url) and _port_is_open(streamlit_url)

    return {
        "name": "FastAPI and Streamlit run on distinct ports",
        "passed": both_up,
        "detail": f"API:{api_parsed.port} Streamlit:{streamlit_parsed.port}",
    }


def check_dashboard_can_reach_api(api_url: str) -> dict:
    """Check the screener endpoint (what the dashboard's screener page calls)
    returns a well-formed response from the same host/network path
    Streamlit runs on."""

    try:
        response = requests.get(f"{api_url}/api/v1/screener", params={"min_roe": 15}, timeout=10)
        body = response.json()
        passed = (
            response.status_code == 200
            and "companies" in body
            and "result_count" in body
        )
        detail = f"HTTP {response.status_code}, result_count={body.get('result_count')}"
    except (requests.RequestException, ValueError) as exc:
        passed = False
        detail = str(exc)

    return {
        "name": "Screener endpoint reachable/well-formed (dashboard data source)",
        "passed": passed,
        "detail": detail,
    }


def run_all_checks(api_url: str, streamlit_url: str) -> list[dict]:
    return [
        check_fastapi_running(api_url),
        check_streamlit_running(streamlit_url),
        check_no_port_conflict(api_url, streamlit_url),
        check_dashboard_can_reach_api(api_url),
    ]


def _print_results(results: list[dict]) -> None:
    for check in results:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"[{status}] {check['name']} — {check['detail']}")

    passed_count = sum(1 for c in results if c["passed"])
    print(f"\n{passed_count}/{len(results)} checks passed")


def _append_to_perf_notes(results: list[dict]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = ["\n## End-to-end integration check (auto-generated)\n"]
    for check in results:
        status = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- [{status}] {check['name']} — {check['detail']}\n")

    passed_count = sum(1 for c in results if c["passed"])
    lines.append(f"- Summary: {passed_count}/{len(results)} checks passed\n")

    with OUTPUT_PATH.open("a", encoding="utf-8") as handle:
        handle.writelines(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--streamlit-url", default=DEFAULT_STREAMLIT_URL)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    results = run_all_checks(args.api_url, args.streamlit_url)
    _print_results(results)

    if not args.no_write:
        _append_to_perf_notes(results)

    if not all(check["passed"] for check in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
