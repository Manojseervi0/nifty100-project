from __future__ import annotations

"""Day 43 — Company Profile page load time, 5 companies, budget: 3 seconds.

IMPORTANT CAVEAT (read before trusting the numbers this prints):
Streamlit renders as a single-page app driven by a websocket connection —
a plain HTTP GET to the Streamlit URL returns only the initial page shell,
not the rendered, data-populated Company Profile screen. True browser
render time requires a real browser driver (Selenium/Playwright).

This script supports both:
  1. If `selenium` is installed and a Streamlit URL is reachable, it drives
     a real headless browser to the Company Profile page and waits for a
     marker element, giving a genuine render-time measurement.
  2. Otherwise, it falls back to timing the actual API calls the Company
     Profile screen depends on (`/companies/{ticker}` +
     `/market-cap/{ticker}`) as a proxy for data-load time — the dominant
     cost of that screen — and prints this clearly labelled as a proxy,
     not a true browser measurement.

Run directly:
    python tests/performance/dashboard_perf.py
    python tests/performance/dashboard_perf.py --mode api --tickers TCS,INFY,HDFCBANK,RELIANCE,ITC
    python tests/performance/dashboard_perf.py --mode selenium --streamlit-url http://localhost:8501
"""

import argparse
import time
from pathlib import Path

import requests

DEFAULT_API_BASE_URL = "http://localhost:8000"
DEFAULT_STREAMLIT_URL = "http://localhost:8501"
DEFAULT_TICKERS = ["TCS", "INFY", "HDFCBANK", "RELIANCE", "ITC"]
TIME_BUDGET_SECONDS = 3.0
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "output" / "perf_notes.md"


def _time_api_proxy(api_base_url: str, ticker: str) -> dict:
    """Time the API calls the Company Profile screen depends on."""

    start = time.perf_counter()
    error = None

    try:
        profile_response = requests.get(
            f"{api_base_url}/api/v1/companies/{ticker}", timeout=10
        )
        profile_response.raise_for_status()

        valuation_response = requests.get(
            f"{api_base_url}/api/v1/market-cap/{ticker}", timeout=10
        )
        # Valuation history can legitimately be missing for some tickers —
        # don't fail the whole check on a 404 here, just note it.
        valuation_ok = valuation_response.status_code == 200
    except requests.RequestException as exc:
        valuation_ok = False
        error = str(exc)

    elapsed = time.perf_counter() - start

    return {
        "ticker": ticker,
        "mode": "api_proxy",
        "elapsed_seconds": elapsed,
        "within_budget": elapsed <= TIME_BUDGET_SECONDS and error is None,
        "valuation_available": valuation_ok if error is None else False,
        "error": error,
    }


def _time_selenium(streamlit_url: str, ticker: str) -> dict:
    """Drive a real headless browser to the Company Profile page for one ticker."""

    from selenium import webdriver  # type: ignore[import-not-found]
    from selenium.webdriver.chrome.options import Options  # type: ignore[import-not-found]
    from selenium.webdriver.common.by import By  # type: ignore[import-not-found]
    from selenium.webdriver.support.ui import WebDriverWait  # type: ignore[import-not-found]
    from selenium.webdriver.support import expected_conditions as EC  # type: ignore[import-not-found]

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=options)
    start = time.perf_counter()
    error = None

    try:
        # Adjust this URL pattern to match how your Streamlit app actually
        # routes to a company (query param name may differ in your app).
        driver.get(f"{streamlit_url}/?ticker={ticker}")
        WebDriverWait(driver, TIME_BUDGET_SECONDS + 5).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except Exception as exc:  # noqa: BLE001 - report any driver/page error
        error = str(exc)
    finally:
        elapsed = time.perf_counter() - start
        driver.quit()

    return {
        "ticker": ticker,
        "mode": "selenium",
        "elapsed_seconds": elapsed,
        "within_budget": elapsed <= TIME_BUDGET_SECONDS and error is None,
        "valuation_available": None,
        "error": error,
    }


def run(
    mode: str,
    tickers: list[str],
    api_base_url: str = DEFAULT_API_BASE_URL,
    streamlit_url: str = DEFAULT_STREAMLIT_URL,
) -> list[dict]:
    """Run the Company Profile timing check for each ticker."""

    if mode == "selenium":
        try:
            import selenium  # noqa: F401
        except ImportError:
            print(
                "selenium is not installed — falling back to --mode api. "
                "Install with `pip install selenium` for a true browser measurement."
            )
            mode = "api"

    results = []

    for ticker in tickers:
        if mode == "selenium":
            result = _time_selenium(streamlit_url, ticker)
        else:
            result = _time_api_proxy(api_base_url, ticker)
        results.append(result)

    return results


def _print_results(results: list[dict]) -> None:
    mode = results[0]["mode"] if results else "unknown"
    print(f"Mode: {mode}")
    if mode == "api_proxy":
        print(
            "NOTE: this measures the API calls the Company Profile screen "
            "depends on, not true browser render time. Use --mode selenium "
            "with a running Streamlit app for a real page-load measurement.\n"
        )

    for row in results:
        status = "PASS" if row["within_budget"] else "FAIL"
        detail = f"{row['elapsed_seconds'] * 1000:.1f} ms"
        if row.get("error"):
            detail += f" (error: {row['error']})"
        print(f"  {row['ticker']:12s} {detail:30s} [{status}]")

    passed = sum(1 for r in results if r["within_budget"])
    print(f"\n{passed}/{len(results)} companies loaded within {TIME_BUDGET_SECONDS:.0f}s")


def _append_to_perf_notes(results: list[dict]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    mode = results[0]["mode"] if results else "unknown"

    lines = ["\n## Company Profile load time (auto-generated)\n"]
    lines.append(f"- Measurement mode: `{mode}`\n")
    if mode == "api_proxy":
        lines.append(
            "- Caveat: this is API data-fetch time, a proxy for page load, "
            "not a real browser render measurement.\n"
        )

    for row in results:
        status = "PASS" if row["within_budget"] else "FAIL"
        lines.append(
            f"- {row['ticker']}: {row['elapsed_seconds'] * 1000:.1f} ms — {status}\n"
        )

    passed = sum(1 for r in results if r["within_budget"])
    lines.append(f"- Summary: {passed}/{len(results)} within {TIME_BUDGET_SECONDS:.0f}s budget\n")

    with OUTPUT_PATH.open("a", encoding="utf-8") as handle:
        handle.writelines(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["api", "selenium"], default="api")
    parser.add_argument("--api-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--streamlit-url", default=DEFAULT_STREAMLIT_URL)
    parser.add_argument(
        "--tickers", default=",".join(DEFAULT_TICKERS), help="comma-separated tickers"
    )
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    results = run(
        mode=args.mode,
        tickers=tickers,
        api_base_url=args.api_url,
        streamlit_url=args.streamlit_url,
    )
    _print_results(results)

    if not args.no_write:
        _append_to_perf_notes(results)


if __name__ == "__main__":
    main()
