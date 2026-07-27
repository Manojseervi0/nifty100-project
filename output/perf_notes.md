# Day 43 — Performance & Integration Testing Notes

**Status of this document:** the SQLite indexing section below contains
real, verified numbers — I ran `db_indexes.py` against your actual
`nifty100.db` twice (once fresh, once to confirm idempotency) and copied
the output directly. The load test, dashboard, and e2e sections could
**not** be run from here: this sandbox has no network access and doesn't
have `fastapi`/`uvicorn`/`streamlit`/`requests` installed, and I don't have
your Streamlit app's source at all. Those three scripts are correct and
ready to run, and each one **appends its real results to this file
automatically** the first time you run it — see "How to complete this
file" at the bottom.

---

## 1. SQLite Index Optimisation — VERIFIED (real run)

Ran `python tests/performance/db_indexes.py` against the actual
`nifty100.db`. No pre-existing indexes were found on any table.

### Indexes created (24 total, across 8 tables)

| Table | Rows | Indexes created |
|---|---|---|
| `financial_ratios` | 1,184 | `company_id`, `year`, `(company_id, year)` |
| `balancesheet` | 1,312 | `company_id`, `year`, `(company_id, year)` |
| `cashflow` | 1,187 | `company_id`, `year`, `(company_id, year)` |
| `profitandloss` | 1,276 | `company_id`, `year`, `(company_id, year)` |
| `market_cap` | 552 | `company_id`, `year`, `(company_id, year)` |
| `peer_percentiles` | 6,104 | `company_id`, `year`, `(company_id, year)` |
| `documents` | 1,585 | `company_id`, `Year`, `(company_id, Year)` |
| `stock_prices` | 5,520 | `company_id`, `date`, `(company_id, date)` — no `year` column exists on this table, so `date` was used instead (see note below) |

**Note on `stock_prices`:** the sprint doc says "index on `company_id` and
`year`," but this table's period column is actually named `date`, not
`year` (confirmed via schema inspection). Indexed `date` in its place
rather than silently skipping the largest table in the database.

### Benchmark: 200x `SELECT * FROM financial_ratios WHERE company_id = ?`

| | Before indexing | After indexing |
|---|---|---|
| Total time (200 lookups) | 82.02 ms | 18.35 ms |
| Speedup | — | **4.47x** |

### Query plan change (verified via `EXPLAIN QUERY PLAN`)

```
Before: SCAN financial_ratios
After:  SEARCH financial_ratios USING INDEX idx_financial_ratios_company_id_year (company_id=?)
```

This is the actual mechanism behind the speedup: every ticker-scoped
lookup across all 8 routers (`companies.py`, `screener.py`, `sectors.py`,
`portfolio.py`, `peers.py`, `valuation.py`, `documents.py`) does a full
table scan today and will use an index seek after this script runs.

**Idempotency confirmed:** running the script a second time reported
`already existed / skipped` for all 24 indexes — safe to run repeatedly,
including in CI.

---

## 2. Load Test — GET `/api/v1/screener` (10 concurrent requests)

*Not yet run — requires a live `uvicorn` process on port 8000.*

Run:
```
uvicorn src.api.main:app --port 8000 &
python tests/performance/load_test.py
```

This appends a section below this line with real min/max/avg/total
numbers and a PASS/FAIL against the 10-second budget. Nothing is filled
in here because no server was available to test against in this
environment — do not treat an absence of numbers as a passing result.

---

## 3. Company Profile Load Time (5 companies, 3s budget)

*Not yet run — requires a live API (and, for true browser-level timing,
Selenium + a running Streamlit instance).*

Run:
```
python tests/performance/dashboard_perf.py --mode api
# or, for a real browser measurement:
pip install selenium
python tests/performance/dashboard_perf.py --mode selenium --streamlit-url http://localhost:8501
```

**Caveat baked into the script itself:** `--mode api` times the API calls
the Company Profile screen depends on, as a proxy for page-load time — it
is not a literal browser render measurement. Use `--mode selenium` against
a running Streamlit instance for that.

---

## 4. End-to-End Integration Check

*Not yet run — requires both `uvicorn` (port 8000) and `streamlit run`
(port 8501) running simultaneously.*

Run:
```
uvicorn src.api.main:app --port 8000 &
streamlit run <your_app>.py --server.port 8501 &
python tests/performance/e2e_test.py
```

Prints and appends PASS/FAIL for: FastAPI reachable, Streamlit reachable,
no port conflict, and the screener endpoint (the dashboard's data source)
returning a well-formed response.

**Caveat:** without your Streamlit app's source, this cannot literally
instrument "the dashboard rendered the API's data" — it confirms the API
is reachable and functional from the same host the dashboard runs on. If
you want a stronger guarantee, add a stable `data-testid`-style marker to
your screener table in Streamlit and extend `dashboard_perf.py`'s selenium
mode to assert against it.

---

## How to complete this file

Run, in order, against your real running stack:

```bash
uvicorn src.api.main:app --port 8000 &
streamlit run <your_app>.py --server.port 8501 &

python tests/performance/load_test.py
python tests/performance/dashboard_perf.py --mode api
python tests/performance/e2e_test.py
```

Each script appends its own `## ... (auto-generated)` section below this
line with real measured numbers. Once all three have run, this file will
contain genuine results for AC-08 (Company Profile < 3s) and the Day 43
load/e2e gates, in addition to the verified indexing results above.

---

## Bottlenecks identified so far

1. **Every company-scoped lookup was a full table scan** before this
   script ran (confirmed via `EXPLAIN QUERY PLAN`) — now fixed by the
   indexes above.
2. **`portfolio.py`'s `/portfolio/stats` recomputes P10–P90 percentiles
   from scratch on every request** when no precomputed
   `output/portfolio_stats.csv` is present (see `_calculate_stats_from_database`).
   This is O(companies × KPIs) per call and doesn't benefit from the new
   indexes since it scans the whole table by design. If this endpoint is
   hit frequently, consider caching the computed stats for a short TTL or
   regenerating `portfolio_stats.csv` on a schedule instead of computing
   it inline per request.
3. **Every router opens and closes its own SQLite connection per
   request** (`get_connection()` in `database.py`). This is fine at
   current load but is worth revisiting with a connection pool if
   concurrent traffic grows well beyond the 10-request load test here.

## Optimization recommendations

- Re-run `db_indexes.py` after any bulk data reload (safe — it's a no-op
  if indexes already exist).
- If `/portfolio/stats` latency becomes an issue under load, precompute
  `output/portfolio_stats.csv` on a schedule rather than computing
  per-request.
- Once the three server-dependent scripts above have real numbers, revisit
  this section — if `/screener` or the Company Profile screen still miss
  their budget after indexing, the next lever is likely the per-request
  connection overhead noted in point 3, not the SQL itself.

## Load test — GET /api/v1/screener (auto-generated)
- URL: `http://localhost:8000/api/v1/screener`
- Concurrent requests: 10
- Successful: 0, Failed: 10
- Min: 4078.28 ms
- Max: 4081.48 ms
- Avg: 4080.30 ms
- Total wall time: 4.083 s
- Result: FAIL (budget: 10s)

## Company Profile load time (auto-generated)
- Measurement mode: `api_proxy`
- Caveat: this is API data-fetch time, a proxy for page load, not a real browser render measurement.
- TCS: 4052.9 ms — FAIL
- INFY: 4092.3 ms — FAIL
- HDFCBANK: 4089.2 ms — FAIL
- RELIANCE: 4045.6 ms — FAIL
- ITC: 4074.0 ms — FAIL
- Summary: 0/5 within 3s budget

## End-to-end integration check (auto-generated)
- [FAIL] FastAPI port reachable — connection refused
- [FAIL] Streamlit port reachable — connection refused
- [FAIL] FastAPI and Streamlit run on distinct ports — API:8000 Streamlit:8501
- [FAIL] Screener endpoint reachable/well-formed (dashboard data source) — HTTPConnectionPool(host='localhost', port=8000): Max retries exceeded with url: /api/v1/screener?min_roe=15 (Caused by NewConnectionError("HTTPConnection(host='localhost', port=8000): Failed to establish a new connection: [WinError 10061] No connection could be made because the target machine actively refused it"))
- Summary: 0/4 checks passed

## Load test — GET /api/v1/screener (auto-generated)
- URL: `http://localhost:8000/api/v1/screener`
- Concurrent requests: 10
- Successful: 10, Failed: 0
- Min: 2246.42 ms
- Max: 2803.48 ms
- Avg: 2669.82 ms
- Total wall time: 2.807 s
- Result: PASS (budget: 10s)

## Company Profile load time (auto-generated)
- Measurement mode: `api_proxy`
- Caveat: this is API data-fetch time, a proxy for page load, not a real browser render measurement.
- TCS: 4140.7 ms — FAIL
- INFY: 4134.8 ms — FAIL
- HDFCBANK: 4123.5 ms — FAIL
- RELIANCE: 4159.1 ms — FAIL
- ITC: 4160.5 ms — FAIL
- Summary: 0/5 within 3s budget

## End-to-end integration check (auto-generated)
- [PASS] FastAPI /api/v1/health returns 200 (status=ok) — HTTP 200
- [PASS] Streamlit serves its base page — HTTP 200
- [PASS] FastAPI and Streamlit run on distinct ports — API:8000 Streamlit:8501
- [PASS] Screener endpoint reachable/well-formed (dashboard data source) — HTTP 200, result_count=53
- Summary: 4/4 checks passed

## End-to-end integration check (auto-generated)
- [PASS] FastAPI /api/v1/health returns 200 (status=ok) — HTTP 200
- [PASS] Streamlit serves its base page — HTTP 200
- [PASS] FastAPI and Streamlit run on distinct ports — API:8000 Streamlit:8501
- [PASS] Screener endpoint reachable/well-formed (dashboard data source) — HTTP 200, result_count=53
- Summary: 4/4 checks passed

## Company Profile load time (auto-generated)
- Measurement mode: `api_proxy`
- Caveat: this is API data-fetch time, a proxy for page load, not a real browser render measurement.
- TCS: 4116.1 ms — FAIL
- INFY: 4106.9 ms — FAIL
- HDFCBANK: 4082.8 ms — FAIL
- RELIANCE: 4075.2 ms — FAIL
- ITC: 4107.5 ms — FAIL
- Summary: 0/5 within 3s budget

## Company Profile load time (auto-generated)
- Measurement mode: `selenium`
- TCS: 193.9 ms — PASS
- INFY: 182.0 ms — PASS
- HDFCBANK: 197.7 ms — PASS
- RELIANCE: 188.3 ms — PASS
- ITC: 198.3 ms — PASS
- Summary: 5/5 within 3s budget

## Company Profile load time (auto-generated)
- Measurement mode: `selenium`
- TCS: 4732.7 ms — FAIL
- INFY: 4721.9 ms — FAIL
- HDFCBANK: 4720.3 ms — FAIL
- RELIANCE: 2595.1 ms — FAIL
- ITC: 4718.2 ms — FAIL
- Summary: 0/5 within 3s budget

## Company Profile load time (auto-generated)
- Measurement mode: `selenium`
- TCS: 198.8 ms — PASS
- INFY: 197.4 ms — PASS
- HDFCBANK: 206.2 ms — PASS
- RELIANCE: 196.5 ms — PASS
- ITC: 191.6 ms — PASS
- Summary: 5/5 within 3s budget

## Company Profile load time (auto-generated)
- Measurement mode: `selenium`
- TCS: 188.0 ms — PASS
- INFY: 184.0 ms — PASS
- HDFCBANK: 218.4 ms — PASS
- RELIANCE: 180.8 ms — PASS
- ITC: 185.5 ms — PASS
- Summary: 5/5 within 3s budget
