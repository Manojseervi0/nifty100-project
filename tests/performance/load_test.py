from __future__ import annotations

"""Day 43 — Load test: 10 concurrent requests against GET /api/v1/screener.

Requires the FastAPI server to already be running (e.g. `uvicorn
src.api.main:app --port 8000`) — this script does not start it.

Run directly:
    python tests/performance/load_test.py
    python tests/performance/load_test.py --url http://localhost:8000 --requests 10
"""

import argparse
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_ENDPOINT = "/api/v1/screener"
DEFAULT_REQUEST_COUNT = 10
TIME_BUDGET_SECONDS = 10.0
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "output" / "perf_notes.md"


def _single_request(url: str, params: dict) -> dict:
    """Issue one GET request and return timing + outcome details."""

    start = time.perf_counter()

    try:
        response = requests.get(url, params=params, timeout=TIME_BUDGET_SECONDS)
        elapsed = time.perf_counter() - start
        return {
            "elapsed_seconds": elapsed,
            "status_code": response.status_code,
            "ok": response.status_code == 200,
            "error": None,
        }
    except requests.RequestException as exc:
        elapsed = time.perf_counter() - start
        return {
            "elapsed_seconds": elapsed,
            "status_code": None,
            "ok": False,
            "error": str(exc),
        }


def run_load_test(
    base_url: str = DEFAULT_BASE_URL,
    endpoint: str = DEFAULT_ENDPOINT,
    request_count: int = DEFAULT_REQUEST_COUNT,
    params: dict | None = None,
) -> dict:
    """Fire `request_count` concurrent requests and return a results summary."""

    url = f"{base_url.rstrip('/')}{endpoint}"
    params = params or {"min_roe": 15}

    overall_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=request_count) as executor:
        futures = [
            executor.submit(_single_request, url, params) for _ in range(request_count)
        ]
        results = [future.result() for future in as_completed(futures)]

    total_wall_seconds = time.perf_counter() - overall_start

    successful = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    elapsed_values = [r["elapsed_seconds"] for r in results]

    summary = {
        "url": url,
        "request_count": request_count,
        "successful_count": len(successful),
        "failed_count": len(failed),
        "min_seconds": min(elapsed_values) if elapsed_values else None,
        "max_seconds": max(elapsed_values) if elapsed_values else None,
        "avg_seconds": statistics.mean(elapsed_values) if elapsed_values else None,
        "total_wall_seconds": total_wall_seconds,
        "within_budget": total_wall_seconds <= TIME_BUDGET_SECONDS and not failed,
        "failures": failed,
    }

    return summary


def _print_summary(summary: dict) -> None:
    print(f"URL:              {summary['url']}")
    print(f"Requests:         {summary['request_count']}")
    print(f"Successful:       {summary['successful_count']}")
    print(f"Failed:           {summary['failed_count']}")
    if summary["min_seconds"] is not None:
        print(f"Min response:     {summary['min_seconds'] * 1000:.2f} ms")
        print(f"Max response:     {summary['max_seconds'] * 1000:.2f} ms")
        print(f"Avg response:     {summary['avg_seconds'] * 1000:.2f} ms")
    print(f"Total wall time:  {summary['total_wall_seconds']:.3f} s")
    print(
        f"Within {TIME_BUDGET_SECONDS:.0f}s budget: "
        f"{'PASS' if summary['within_budget'] else 'FAIL'}"
    )
    for failure in summary["failures"]:
        print(f"  FAILED REQUEST: {failure['error'] or failure['status_code']}")


def _append_to_perf_notes(summary: dict) -> None:
    """Append this run's results to output/perf_notes.md under a marker."""

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "\n## Load test — GET /api/v1/screener (auto-generated)\n",
        f"- URL: `{summary['url']}`\n",
        f"- Concurrent requests: {summary['request_count']}\n",
        f"- Successful: {summary['successful_count']}, Failed: {summary['failed_count']}\n",
    ]

    if summary["min_seconds"] is not None:
        lines.append(f"- Min: {summary['min_seconds'] * 1000:.2f} ms\n")
        lines.append(f"- Max: {summary['max_seconds'] * 1000:.2f} ms\n")
        lines.append(f"- Avg: {summary['avg_seconds'] * 1000:.2f} ms\n")

    lines.append(f"- Total wall time: {summary['total_wall_seconds']:.3f} s\n")
    lines.append(
        f"- Result: {'PASS' if summary['within_budget'] else 'FAIL'} "
        f"(budget: {TIME_BUDGET_SECONDS:.0f}s)\n"
    )

    with OUTPUT_PATH.open("a", encoding="utf-8") as handle:
        handle.writelines(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_BASE_URL)
    parser.add_argument("--requests", type=int, default=DEFAULT_REQUEST_COUNT)
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Don't append results to output/perf_notes.md",
    )
    args = parser.parse_args()

    summary = run_load_test(base_url=args.url, request_count=args.requests)
    _print_summary(summary)

    if not args.no_write:
        _append_to_perf_notes(summary)

    if not summary["within_budget"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
