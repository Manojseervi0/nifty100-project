from __future__ import annotations

import csv
import hashlib
import math
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "nifty100.db"
OUTPUT_DIR = ROOT / "output"
DOCS_DIR = ROOT / "docs"
FINAL_DIR = OUTPUT_DIR / "final_deliverables"
RESULTS_CSV = OUTPUT_DIR / "acceptance_results.csv"
CHECKLIST_PDF = DOCS_DIR / "acceptance_checklist.pdf"
MANIFEST_CSV = FINAL_DIR / "deliverables_manifest.csv"
PASS = "PASS"
FAIL = "FAIL"

# Exactly 23 deliverables. Alternative paths are supported where projects differ.
DELIVERABLES: list[tuple[str, list[str]]] = [
    ("01 Working SQLite database", ["nifty100.db"]),
    ("02 Project README", ["README.md"]),
    ("03 ETL load audit", ["output/load_audit.csv", "load_audit.csv"]),
    ("04 Validation failures", ["output/validation_failures.csv"]),
    ("05 Valuation summary", ["output/valuation_summary.xlsx"]),
    ("06 Valuation flags", ["output/valuation_flags.csv"]),
    ("07 Generated pros and cons", ["output/pros_cons_generated.csv", "output/pros_and_cons_generated.csv"]),
    ("08 Cash-flow intelligence", ["output/cashflow_intelligence.csv", "output/cash_flow_intelligence.csv"]),
    ("09 Capital allocation output", ["output/capital_allocation.csv", "output/capital_allocation_report.csv", "output/capital_allocation_summary.csv"]),
    ("10 Cluster labels", ["output/cluster_labels.csv"]),
    ("11 Cluster profiles", ["output/cluster_profiles.csv"]),
    ("12 Outlier report", ["output/outlier_report.csv"]),
    ("13 Portfolio statistics", ["output/portfolio_stats.csv"]),
    ("14 KMeans elbow plot", ["reports/elbow_plot.png"]),
    ("15 Correlation heatmap", ["reports/correlation_heatmap.png"]),
    ("16 Company tearsheets", ["reports/tearsheets"]),
    ("17 Sector PDF reports", ["reports/sectors", "reports/sector_reports"]),
    ("18 Portfolio summary PDF", ["reports/portfolio/portfolio_summary.pdf", "reports/portfolio_summary.pdf"]),
    ("19 FastAPI source", ["src/api"]),
    ("20 OpenAPI specification", ["docs/openapi.json"]),
    ("21 Postman collection", ["docs/nifty100_api.postman_collection.json", "docs/postman_collection.json"]),
    ("22 Pytest HTML report", ["reports/pytest_report.html"]),
    ("23 Analyst guide", ["docs/analyst_guide.pdf"]),
]


def safe_float(value: Any) -> float | None:
    """Convert a value into a finite float."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def extract_year(value: Any) -> int | None:
    """Extract a four-digit year from a period label."""
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group()) if match else None


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    """Return whether a SQLite table exists."""
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def columns(connection: sqlite3.Connection, table: str) -> list[str]:
    """Return column names for a table."""
    if not table_exists(connection, table):
        return []
    return [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()]


def first_existing_column(available: list[str], candidates: list[str]) -> str | None:
    """Return the first candidate column that exists."""
    lowered = {column.lower(): column for column in available}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def make_result(gate_id: str, title: str, passed: bool, evidence: str) -> dict[str, str]:
    """Create a normalized gate result."""
    return {"gate_id": gate_id, "title": title, "status": PASS if passed else FAIL, "evidence": evidence}


def history_coverage(connection: sqlite3.Connection, table: str) -> dict[str, int]:
    """Count unique years for every company in a table."""
    available = columns(connection, table)
    company_col = first_existing_column(available, ["company_id", "ticker", "id"])
    year_col = first_existing_column(available, ["year", "Year", "period"])
    if not company_col or not year_col:
        return {}
    rows = connection.execute(f'SELECT "{company_col}", "{year_col}" FROM "{table}"').fetchall()
    history: dict[str, set[int]] = {}
    for company_id, period in rows:
        company = str(company_id or "").strip().upper()
        year = extract_year(period)
        if company and year:
            history.setdefault(company, set()).add(year)
    return {company: len(years) for company, years in history.items()}


def api_client():
    """Create a local FastAPI test client."""
    from fastapi.testclient import TestClient
    from src.api.main import app
    return TestClient(app)


def check_ac01(connection: sqlite3.Connection) -> dict[str, str]:
    count = connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    return make_result("AC-01", "Companies table contains exactly 92 rows", count == 92, f"companies={count}")


def check_ac02(connection: sqlite3.Connection) -> dict[str, str]:
    pl = history_coverage(connection, "profitandloss")
    bs = history_coverage(connection, "balancesheet")
    cf = history_coverage(connection, "cashflow")
    companies = {str(row[0]).strip().upper() for row in connection.execute("SELECT id FROM companies")}
    passing = [c for c in companies if pl.get(c, 0) >= 10 and bs.get(c, 0) >= 10 and cf.get(c, 0) >= 10]
    percentage = len(passing) / len(companies) * 100 if companies else 0
    return make_result("AC-02", "At least 90% have 10+ years of P&L, BS and CF", percentage >= 90, f"{len(passing)}/{len(companies)} = {percentage:.2f}%")


def check_ac03(connection: sqlite3.Connection) -> dict[str, str]:
    issues = connection.execute("PRAGMA foreign_key_check").fetchall()
    return make_result("AC-03", "Foreign-key check returns zero rows", len(issues) == 0, f"issues={len(issues)}")


def check_ac04(connection: sqlite3.Connection) -> dict[str, str]:
    count = connection.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0]
    return make_result("AC-04", "Financial ratios contain at least 1,100 rows", count >= 1100, f"rows={count}")


def check_ac05(connection: sqlite3.Connection) -> dict[str, str]:
    """Spot-check TCS five-year revenue CAGR."""
    pl_cols = columns(connection, "profitandloss")
    ratio_cols = columns(connection, "financial_ratios")
    revenue_col = first_existing_column(pl_cols, ["sales", "revenue", "total_revenue", "revenue_from_operations"])
    pl_company = first_existing_column(pl_cols, ["company_id", "ticker"])
    pl_year = first_existing_column(pl_cols, ["year", "Year"])
    ratio_company = first_existing_column(ratio_cols, ["company_id", "ticker"])
    ratio_year = first_existing_column(ratio_cols, ["year", "Year"])
    cagr_col = first_existing_column(ratio_cols, ["revenue_cagr_5yr"])
    if not all([revenue_col, pl_company, pl_year, ratio_company, ratio_year, cagr_col]):
        return make_result("AC-05", "Revenue CAGR spot-check is within 0.1%", False, "Required columns not found")

    rows = connection.execute(
        f'SELECT "{pl_year}", "{revenue_col}" FROM profitandloss WHERE UPPER("{pl_company}")=\'TCS\''
    ).fetchall()
    values: dict[int, float] = {}
    for period, revenue in rows:
        year = extract_year(period)
        number = safe_float(revenue)
        if year and number is not None and number > 0:
            values[year] = number
    if len(values) < 6:
        return make_result("AC-05", "Revenue CAGR spot-check is within 0.1%", False, f"usable TCS years={len(values)}")
    end_year = max(values)
    start_year = end_year - 5
    if start_year not in values:
        return make_result("AC-05", "Revenue CAGR spot-check is within 0.1%", False, f"missing start year {start_year}")
    manual = ((values[end_year] / values[start_year]) ** (1 / 5) - 1) * 100

    ratio_rows = connection.execute(
        f'SELECT "{ratio_year}", "{cagr_col}" FROM financial_ratios WHERE UPPER("{ratio_company}")=\'TCS\' AND "{cagr_col}" IS NOT NULL'
    ).fetchall()
    reported_candidates = [(extract_year(period), safe_float(value)) for period, value in ratio_rows]
    reported_candidates = [item for item in reported_candidates if item[0] and item[1] is not None]
    if not reported_candidates:
        return make_result("AC-05", "Revenue CAGR spot-check is within 0.1%", False, "No reported TCS CAGR")
    _, reported = max(reported_candidates, key=lambda item: item[0])
    difference = abs(manual - reported)
    return make_result("AC-05", "Revenue CAGR spot-check is within 0.1%", difference <= 0.1, f"manual={manual:.4f}%, reported={reported:.4f}%, diff={difference:.4f}%")


def check_ac06(connection: sqlite3.Connection) -> dict[str, str]:
    """Compare latest ROE with master ROE for five companies."""
    company_cols = columns(connection, "companies")
    ratio_cols = columns(connection, "financial_ratios")
    master_roe = first_existing_column(company_cols, ["roe_percentage", "return_on_equity_pct", "roe"])
    ratio_roe = first_existing_column(ratio_cols, ["return_on_equity_pct", "roe_percentage", "roe"])
    ratio_year = first_existing_column(ratio_cols, ["year", "Year"])
    if not master_roe or not ratio_roe or not ratio_year:
        return make_result("AC-06", "ROE matches master within 5% for five companies", False, "Required ROE columns not found")
    candidates = ["TCS", "INFY", "ITC", "RELIANCE", "HDFCBANK"]
    comparisons = []
    for ticker in candidates:
        master_row = connection.execute(f'SELECT "{master_roe}" FROM companies WHERE UPPER(id)=?', (ticker,)).fetchone()
        ratio_rows = connection.execute(
            f'SELECT "{ratio_year}", "{ratio_roe}" FROM financial_ratios WHERE UPPER(company_id)=? AND "{ratio_roe}" IS NOT NULL',
            (ticker,),
        ).fetchall()
        if not master_row or not ratio_rows:
            continue
        master = safe_float(master_row[0])
        latest = [(extract_year(period), safe_float(value)) for period, value in ratio_rows]
        latest = [item for item in latest if item[0] and item[1] is not None]
        if master is None or not latest:
            continue
        _, calculated = max(latest, key=lambda item: item[0])
        comparisons.append((ticker, master, calculated, abs(calculated - master)))
    passed = len(comparisons) == 5 and all(item[3] <= 5 for item in comparisons)
    evidence = "; ".join(f"{t}: diff={d:.2f}" for t, _, _, d in comparisons) or "No complete comparisons"
    return make_result("AC-06", "ROE matches master within 5% for five companies", passed, evidence)


def check_ac07() -> dict[str, str]:
    try:
        response = api_client().get("/api/v1/screener", params={"min_roe": 15, "max_de": 1, "min_fcf": 0})
        payload = response.json()
        count = int(payload.get("result_count", 0))
        return make_result("AC-07", "Quality screener returns 10-50 companies", response.status_code == 200 and 10 <= count <= 50, f"HTTP {response.status_code}, count={count}")
    except Exception as exc:
        return make_result("AC-07", "Quality screener returns 10-50 companies", False, str(exc))


def check_ac08() -> dict[str, str]:
    script = ROOT / "tests/performance/dashboard_perf.py"
    if not script.exists():
        return make_result("AC-08", "Company Profile loads under 3 seconds", False, "dashboard_perf.py missing")
    try:
        run = subprocess.run([sys.executable, str(script)], cwd=ROOT, capture_output=True, text=True, timeout=120)
        output = (run.stdout or "") + "\n" + (run.stderr or "")
        match = re.search(r"(\d+)/5 companies loaded within 3s", output)
        passed = bool(match and int(match.group(1)) == 5)
        evidence = match.group(0) if match else output.strip()[-400:]
    except Exception as exc:
        passed = False
        evidence = str(exc)
    return make_result("AC-08", "Company Profile loads under 3 seconds", passed, evidence)


def check_ac09() -> dict[str, str]:
    export_path = OUTPUT_DIR / "acceptance_screener_export.csv"
    try:
        from src.screener.engine import get_latest_year_data, load_screener_data
        frame = get_latest_year_data(load_screener_data())
        frame.to_csv(export_path, index=False)
        with export_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        passed = export_path.stat().st_size > 0 and len(rows) > 1 and len(rows[0]) >= 5 and all(len(row) == len(rows[0]) for row in rows[:100])
        evidence = f"rows={len(rows)-1}, columns={len(rows[0])}"
    except Exception as exc:
        passed = False
        evidence = str(exc)
    return make_result("AC-09", "Screener CSV is valid and well formed", passed, evidence)


def check_pdf_blocks(path: Path) -> tuple[bool, str]:
    try:
        import fitz
    except ImportError:
        return False, "PyMuPDF not installed"
    document = fitz.open(path)
    issues = []
    for page_index, page in enumerate(document):
        rect = page.rect
        for block in page.get_text("blocks"):
            x0, y0, x1, y1 = block[:4]
            if x0 < -1 or y0 < -1 or x1 > rect.width + 1 or y1 > rect.height + 1:
                issues.append(f"page {page_index+1} block outside page")
    return not issues, "; ".join(issues) or "No out-of-page text blocks"


def check_ac10() -> dict[str, str]:
    directory = ROOT / "reports/tearsheets"
    pdfs = sorted(directory.glob("*.pdf")) if directory.exists() else []
    if len(pdfs) < 5:
        return make_result("AC-10", "No overflow in five sampled tearsheets", False, f"PDFs available={len(pdfs)}")
    sample = pdfs[:5]
    checks = [(path, *check_pdf_blocks(path)) for path in sample]
    passed = all(item[1] for item in checks)
    evidence = "; ".join(f"{path.name}: {'OK' if ok else note}" for path, ok, note in checks)
    return make_result("AC-10", "No overflow in five sampled tearsheets", passed, evidence)


def check_ac11() -> dict[str, str]:
    try:
        response = api_client().get("/api/v1/health")
        payload = response.json()
        passed = response.status_code == 200 and payload.get("status") == "ok"
        return make_result("AC-11", "Health endpoint returns HTTP 200", passed, f"HTTP {response.status_code}, status={payload.get('status')}")
    except Exception as exc:
        return make_result("AC-11", "Health endpoint returns HTTP 200", False, str(exc))


def check_ac12() -> dict[str, str]:
    try:
        response = api_client().get("/api/v1/companies/TCS/ratios")
        payload = response.json()
        if isinstance(payload, dict):
            records = payload.get("ratios") or payload.get("history") or payload.get("data") or []
        elif isinstance(payload, list):
            records = payload
        else:
            records = []
        return make_result("AC-12", "TCS ratios endpoint returns 10+ years", response.status_code == 200 and len(records) >= 10, f"HTTP {response.status_code}, records={len(records)}")
    except Exception as exc:
        return make_result("AC-12", "TCS ratios endpoint returns 10+ years", False, str(exc))


def check_ac13() -> dict[str, str]:
    xlsx_path = OUTPUT_DIR / "screener_output.xlsx"
    try:
        import pandas as pd
        from src.screener.engine import get_latest_year_data, load_screener_data
        dashboard = get_latest_year_data(load_screener_data())
        dashboard = dashboard[pd.to_numeric(dashboard["return_on_equity_pct"], errors="coerce") >= 15].copy()
        ticker_col = "company_id" if "company_id" in dashboard.columns else "ticker"
        dashboard.to_excel(xlsx_path, index=False)
        response = api_client().get("/api/v1/screener", params={"min_roe": 15})
        api_companies = response.json().get("companies", [])
        dashboard_tickers = {str(value).strip().upper() for value in dashboard[ticker_col].tolist()}
        api_tickers = {str(item.get("company_id", "")).strip().upper() for item in api_companies}
        passed = response.status_code == 200 and dashboard_tickers == api_tickers
        evidence = f"dashboard={len(dashboard_tickers)}, api={len(api_tickers)}, only_dashboard={sorted(dashboard_tickers-api_tickers)[:5]}, only_api={sorted(api_tickers-dashboard_tickers)[:5]}"
    except Exception as exc:
        passed = False
        evidence = str(exc)
    return make_result("AC-13", "API screener matches screener_output.xlsx", passed, evidence)


def check_ac14(connection: sqlite3.Connection) -> dict[str, str]:
    available = columns(connection, "peer_percentiles")
    group_col = first_existing_column(available, ["peer_group_name", "group_name", "peer_group"])
    if not group_col:
        return make_result("AC-14", "Peer percentiles cover 11 peer groups", False, "Peer-group column missing")
    count = connection.execute(f'SELECT COUNT(DISTINCT "{group_col}") FROM peer_percentiles WHERE "{group_col}" IS NOT NULL').fetchone()[0]
    return make_result("AC-14", "Peer percentiles cover 11 peer groups", count >= 11, f"groups={count}")


def read_csv_frame(path: Path):
    import pandas as pd
    return pd.read_csv(path)


def check_ac15() -> dict[str, str]:
    path = OUTPUT_DIR / "cluster_labels.csv"
    if not path.exists():
        return make_result("AC-15", "All 92 companies have a cluster ID", False, "cluster_labels.csv missing")
    try:
        frame = read_csv_frame(path)
        company_col = first_existing_column(list(frame.columns), ["company_id", "ticker"])
        cluster_col = first_existing_column(list(frame.columns), ["cluster_id"])
        unique = frame[company_col].astype(str).str.strip().nunique() if company_col else 0
        missing = int(frame[cluster_col].isna().sum()) if cluster_col else len(frame)
        return make_result("AC-15", "All 92 companies have a cluster ID", unique == 92 and missing == 0, f"unique={unique}, missing_cluster={missing}")
    except Exception as exc:
        return make_result("AC-15", "All 92 companies have a cluster ID", False, str(exc))


def locate_pros_cons() -> Path | None:
    for path in [OUTPUT_DIR / "pros_cons_generated.csv", OUTPUT_DIR / "pros_and_cons_generated.csv"]:
        if path.exists():
            return path
    return None


def check_ac16(connection: sqlite3.Connection) -> dict[str, str]:
    path = locate_pros_cons()
    if path is None:
        return make_result("AC-16", "All 92 companies have at least one pro and one con", False, "Pros/cons CSV missing")
    try:
        frame = read_csv_frame(path)
        company_col = first_existing_column(list(frame.columns), ["company_id", "ticker"])
        if not company_col:
            raise ValueError("company_id/ticker column missing")
        all_companies = {str(row[0]).strip().upper() for row in connection.execute("SELECT id FROM companies")}
        pro_col = first_existing_column(list(frame.columns), ["pro", "pros"])
        con_col = first_existing_column(list(frame.columns), ["con", "cons"])
        type_col = first_existing_column(list(frame.columns), ["type", "category", "sentiment"])
        coverage: dict[str, set[str]] = {}
        if pro_col and con_col:
            for _, row in frame.iterrows():
                company = str(row[company_col]).strip().upper()
                kinds = coverage.setdefault(company, set())
                if str(row.get(pro_col, "")).strip():
                    kinds.add("pro")
                if str(row.get(con_col, "")).strip():
                    kinds.add("con")
        elif type_col:
            for _, row in frame.iterrows():
                company = str(row[company_col]).strip().upper()
                kind = str(row[type_col]).strip().lower()
                if "pro" in kind or "strength" in kind:
                    coverage.setdefault(company, set()).add("pro")
                if "con" in kind or "weak" in kind or "risk" in kind:
                    coverage.setdefault(company, set()).add("con")
        else:
            raise ValueError("Could not identify pro/con layout")
        complete = {company for company in all_companies if coverage.get(company, set()) >= {"pro", "con"}}
        missing = sorted(all_companies - complete)
        return make_result("AC-16", "All 92 companies have at least one pro and one con", len(complete) == 92, f"complete={len(complete)}/92, missing={missing[:10]}")
    except Exception as exc:
        return make_result("AC-16", "All 92 companies have at least one pro and one con", False, str(exc))


def check_ac17() -> dict[str, str]:
    directory = ROOT / "reports/tearsheets"
    pdfs = list(directory.glob("*.pdf")) if directory.exists() else []
    large = [path for path in pdfs if path.stat().st_size >= 30 * 1024]
    return make_result("AC-17", "92 tearsheets exist and each is at least 30 KB", len(pdfs) == 92 and len(large) == 92, f"PDFs={len(pdfs)}, >=30KB={len(large)}")


def check_ac18() -> dict[str, str]:
    path = ROOT / "reports/pytest_report.html"
    if not path.exists():
        return make_result("AC-18", "Pytest has 60+ tests and zero failures", False, "pytest_report.html missing")
    text = path.read_text(encoding="utf-8", errors="ignore")
    passed_values = [int(value) for value in re.findall(r"(\d+)\s+passed", text)]
    failed_values = [int(value) for value in re.findall(r"(\d+)\s+failed", text)]
    passed_count = max(passed_values, default=0)
    failed_count = max(failed_values, default=0)
    return make_result("AC-18", "Pytest has 60+ tests and zero failures", passed_count >= 60 and failed_count == 0, f"passed={passed_count}, failed={failed_count}")


def check_ac19() -> dict[str, str]:
    path = OUTPUT_DIR / "validation_failures.csv"
    required = {"company_id", "field", "issue", "severity"}
    if not path.exists():
        return make_result("AC-19", "validation_failures.csv has required columns", False, "File missing")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = set(csv.DictReader(handle).fieldnames or [])
    return make_result("AC-19", "validation_failures.csv has required columns", required.issubset(header), f"columns={sorted(header)}")


def check_ac20() -> dict[str, str]:
    path = DOCS_DIR / "analyst_guide.pdf"
    if not path.exists():
        return make_result("AC-20", "Analyst guide has at least 10 pages", False, "analyst_guide.pdf missing")
    try:
        from pypdf import PdfReader
        pages = len(PdfReader(str(path)).pages)
        return make_result("AC-20", "Analyst guide has at least 10 pages", pages >= 10, f"pages={pages}")
    except Exception as exc:
        return make_result("AC-20", "Analyst guide has at least 10 pages", False, str(exc))


def run_acceptance_checks() -> list[dict[str, str]]:
    """Run all twenty acceptance gates without changing the database."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database missing: {DB_PATH}")
    with sqlite3.connect(DB_PATH) as connection:
        return [
            check_ac01(connection), check_ac02(connection), check_ac03(connection), check_ac04(connection),
            check_ac05(connection), check_ac06(connection), check_ac07(), check_ac08(), check_ac09(), check_ac10(),
            check_ac11(), check_ac12(), check_ac13(), check_ac14(connection), check_ac15(), check_ac16(connection),
            check_ac17(), check_ac18(), check_ac19(), check_ac20(),
        ]


def write_results_csv(checks: list[dict[str, str]]) -> None:
    """Write acceptance results to CSV."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with RESULTS_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["gate_id", "title", "status", "evidence"])
        writer.writeheader()
        writer.writerows(checks)


def resolve_deliverable(paths: list[str]) -> Path | None:
    """Resolve the first existing path from alternatives."""
    for relative in paths:
        path = ROOT / relative
        if path.exists():
            return path
    return None


def copy_deliverables() -> list[dict[str, str]]:
    """Copy all available deliverables into the final archive."""
    if FINAL_DIR.exists():
        shutil.rmtree(FINAL_DIR)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []
    for number, (name, alternatives) in enumerate(DELIVERABLES, start=1):
        source = resolve_deliverable(alternatives)
        if source is None:
            records.append({"number": str(number), "deliverable": name, "status": FAIL, "source_path": " | ".join(alternatives), "archive_path": "", "sha256": ""})
            continue
        target = FINAL_DIR / f"{number:02d}_{source.name}"
        if source.is_dir():
            shutil.copytree(source, target)
            digest = "DIRECTORY"
        else:
            shutil.copy2(source, target)
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
        records.append({"number": str(number), "deliverable": name, "status": PASS, "source_path": str(source.relative_to(ROOT)), "archive_path": str(target.relative_to(ROOT)), "sha256": digest})
    with MANIFEST_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["number", "deliverable", "status", "source_path", "archive_path", "sha256"])
        writer.writeheader()
        writer.writerows(records)
    return records


def create_checklist_pdf(checks: list[dict[str, str]], deliverables: list[dict[str, str]]) -> None:
    """Generate a landscape PDF with gates, deliverables and signature fields."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ChecklistTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=22, leading=26, textColor=colors.HexColor("#1C3F6E"), spaceAfter=12)
    subtitle_style = ParagraphStyle("ChecklistSubtitle", parent=styles["Normal"], alignment=TA_CENTER, fontSize=10, textColor=colors.HexColor("#4A5568"), spaceAfter=12)
    body = ParagraphStyle("ChecklistBody", parent=styles["BodyText"], fontSize=7.4, leading=9.2)
    small = ParagraphStyle("ChecklistSmall", parent=styles["BodyText"], fontSize=6.6, leading=8.0)
    document = SimpleDocTemplate(str(CHECKLIST_PDF), pagesize=landscape(A4), rightMargin=10*mm, leftMargin=10*mm, topMargin=10*mm, bottomMargin=12*mm, title="Nifty100 Sprint 6 Acceptance Checklist", author="Manoj Seervi")

    pass_count = sum(item["status"] == PASS for item in checks)
    deliverable_count = sum(item["status"] == PASS for item in deliverables)
    overall = "READY FOR SIGN-OFF" if pass_count == 20 and deliverable_count == 23 else "ACTION REQUIRED"

    story = [
        Paragraph("Nifty100 Analytics - Sprint 6 Acceptance Checklist", title_style),
        Paragraph(f"Day 45 Final Sign-Off | Generated {datetime.now().strftime('%d %B %Y, %I:%M %p')}", subtitle_style),
    ]
    summary = Table([["Acceptance Gates", "Deliverables", "Overall Status"], [f"{pass_count}/20 PASS", f"{deliverable_count}/23 PRESENT", overall]], colWidths=[70*mm, 70*mm, 70*mm])
    summary.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1C3F6E")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("BACKGROUND", (0,1), (-1,1), colors.HexColor("#EAF2FB")), ("ALIGN", (0,0), (-1,-1), "CENTER"), ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 10), ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#AAB4C3")), ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7)]))
    story.extend([summary, Spacer(1, 8*mm), Paragraph("20 Acceptance Gates", styles["Heading2"])])

    gate_rows = [[Paragraph("Gate", body), Paragraph("Requirement", body), Paragraph("Status", body), Paragraph("Evidence", body)]]
    for item in checks:
        gate_rows.append([Paragraph(item["gate_id"], body), Paragraph(item["title"], body), Paragraph(item["status"], body), Paragraph(item["evidence"].replace("&", "&amp;"), small)])
    gate_table = LongTable(gate_rows, repeatRows=1, colWidths=[18*mm, 73*mm, 20*mm, 155*mm])
    gate_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1C3F6E")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#AAB4C3")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4)]))
    for row_index, item in enumerate(checks, start=1):
        color = colors.HexColor("#DFF3E4") if item["status"] == PASS else colors.HexColor("#FBE4E4")
        gate_table.setStyle(TableStyle([("BACKGROUND", (2,row_index), (2,row_index), color), ("FONTNAME", (2,row_index), (2,row_index), "Helvetica-Bold")]))
    story.extend([gate_table, PageBreak(), Paragraph("23 Deliverables Checklist", title_style)])

    deliverable_rows = [[Paragraph("#", body), Paragraph("Deliverable", body), Paragraph("Status", body), Paragraph("Source path", body), Paragraph("Archived path", body)]]
    for item in deliverables:
        deliverable_rows.append([Paragraph(item["number"], body), Paragraph(item["deliverable"], body), Paragraph(item["status"], body), Paragraph(item["source_path"], small), Paragraph(item["archive_path"], small)])
    deliverable_table = LongTable(deliverable_rows, repeatRows=1, colWidths=[10*mm, 70*mm, 20*mm, 80*mm, 85*mm])
    deliverable_table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1C3F6E")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#AAB4C3")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4)]))
    for row_index, item in enumerate(deliverables, start=1):
        color = colors.HexColor("#DFF3E4") if item["status"] == PASS else colors.HexColor("#FBE4E4")
        deliverable_table.setStyle(TableStyle([("BACKGROUND", (2,row_index), (2,row_index), color), ("FONTNAME", (2,row_index), (2,row_index), "Helvetica-Bold")]))
    story.extend([deliverable_table, Spacer(1, 10*mm), Paragraph("Team Lead Sign-Off", styles["Heading2"]), Spacer(1, 5*mm)])
    signoff = Table([["Reviewed by:", "____________________________"], ["Signature:", "____________________________"], ["Date:", "____________________________"], ["Final decision:", "ACCEPTED / ACTION REQUIRED"]], colWidths=[45*mm, 120*mm])
    signoff.setStyle(TableStyle([("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 10), ("BOTTOMPADDING", (0,0), (-1,-1), 8)]))
    story.append(signoff)
    document.build(story)


def main() -> None:
    """Run gates, create checklist and archive deliverables."""
    checks = run_acceptance_checks()
    write_results_csv(checks)
    deliverables = copy_deliverables()
    create_checklist_pdf(checks, deliverables)
    pass_count = sum(item["status"] == PASS for item in checks)
    deliverable_count = sum(item["status"] == PASS for item in deliverables)
    print("=" * 72)
    print("NIFTY100 SPRINT 6 FINAL SIGN-OFF")
    print("=" * 72)
    for item in checks:
        print(f"{item['status']:<4} | {item['gate_id']} | {item['evidence']}")
    print("-" * 72)
    print(f"Acceptance gates : {pass_count}/20 PASS")
    print(f"Deliverables     : {deliverable_count}/23 PRESENT")
    print(f"Results CSV      : {RESULTS_CSV.relative_to(ROOT)}")
    print(f"Checklist PDF    : {CHECKLIST_PDF.relative_to(ROOT)}")
    print(f"Final archive    : {FINAL_DIR.relative_to(ROOT)}")
    print("=" * 72)
    if pass_count < 20 or deliverable_count < 23:
        print("STATUS: ACTION REQUIRED")
        raise SystemExit(1)
    print("STATUS: READY FOR TEAM LEAD SIGN-OFF")


if __name__ == "__main__":
    main()
