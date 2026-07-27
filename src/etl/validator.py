from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import pandas as pd


DEFAULT_OUTPUT_PATH = Path("output/validation_failures.csv")


@dataclass(frozen=True)
class DQFinding:
    """Represent one data-quality rule violation."""

    rule_id: str
    severity: str
    table_name: str
    company_id: str
    field: str
    issue: str

    def to_dict(self) -> dict[str, str]:
        """Return the finding as a CSV-ready dictionary."""

        return asdict(self)


def _text(value: object) -> str:
    """Convert a value to trimmed text without exposing pandas nulls."""

    if pd.isna(value):
        return ""
    return str(value).strip()


def _company_id(row: pd.Series) -> str:
    """Extract a company identifier from a row."""

    for column in ("company_id", "id", "ticker"):
        if column in row.index and _text(row[column]):
            return _text(row[column])
    return "UNKNOWN"


def _finding(rule_id: str, severity: str, table_name: str, company_id: object,
             field: str, issue: str) -> DQFinding:
    """Build a normalized finding."""

    return DQFinding(rule_id, severity, table_name, _text(company_id) or "UNKNOWN", field, issue)


def write_validation_failures(findings: Iterable[DQFinding],
                              output_path: str | Path = DEFAULT_OUTPUT_PATH,
                              append: bool = False) -> Path:
    """Write findings using the AC-19-compatible CSV schema."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    write_header = not append or not path.exists() or path.stat().st_size == 0
    fields = ["rule_id", "table_name", "company_id", "field", "issue", "severity"]
    with path.open(mode, encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if write_header:
            writer.writeheader()
        for finding in findings:
            writer.writerow(finding.to_dict())
    return path


def log_failure(rule_id, table_name, record_id, severity, message, field="record"):
    """Append one legacy-style failure using the new CSV schema."""

    write_validation_failures([
        _finding(rule_id, severity, table_name, record_id, field, message)
    ], append=True)


def rule_dq01_company_id_unique(df: pd.DataFrame, table_name="companies") -> list[DQFinding]:
    """Flag duplicate company IDs."""

    duplicates = df[df["id"].duplicated(keep=False)]
    return [_finding("DQ-01", "CRITICAL", table_name, row["id"], "id", "Duplicate company ID")
            for _, row in duplicates.iterrows()]


def rule_dq02_annual_key_unique(df: pd.DataFrame, table_name="financial_ratios") -> list[DQFinding]:
    """Flag duplicate company/year keys."""

    duplicates = df[df.duplicated(["company_id", "year"], keep=False)]
    return [_finding("DQ-02", "CRITICAL", table_name, row["company_id"],
                     "company_id,year", f"Duplicate annual key for {_text(row['year'])}")
            for _, row in duplicates.iterrows()]


def rule_dq03_company_id_not_null(df: pd.DataFrame, table_name="unknown") -> list[DQFinding]:
    """Flag null or blank company IDs."""

    column = "company_id" if "company_id" in df.columns else "id"
    invalid = df[column].isna() | df[column].astype(str).str.strip().eq("")
    return [_finding("DQ-03", "CRITICAL", table_name, f"ROW-{index}", column,
                     "Company identifier is null or blank") for index in df.index[invalid]]


def rule_dq04_year_format_valid(df: pd.DataFrame, table_name="unknown") -> list[DQFinding]:
    """Flag values without a valid four-digit year."""

    findings = []
    for _, row in df.iterrows():
        value = _text(row["year"])
        if not re.search(r"(?:19|20)\d{2}", value):
            findings.append(_finding("DQ-04", "HIGH", table_name, _company_id(row),
                                     "year", f"Invalid year value: {value or 'NULL'}"))
    return findings


def rule_dq05_company_fk_valid(df: pd.DataFrame, valid_company_ids: Iterable[str],
                               table_name="unknown") -> list[DQFinding]:
    """Flag company IDs absent from the canonical company set."""

    valid = {_text(value).upper() for value in valid_company_ids}
    return [_finding("DQ-05", "CRITICAL", table_name, row["company_id"],
                     "company_id", "Orphan company ID")
            for _, row in df.iterrows()
            if _text(row["company_id"]) and _text(row["company_id"]).upper() not in valid]


def rule_dq06_revenue_non_negative(df: pd.DataFrame, revenue_column="sales",
                                   table_name="profitandloss") -> list[DQFinding]:
    """Flag negative revenue."""

    numeric = pd.to_numeric(df[revenue_column], errors="coerce")
    return [_finding("DQ-06", "HIGH", table_name, _company_id(row), revenue_column,
                     "Revenue cannot be negative") for _, row in df[numeric < 0].iterrows()]


def rule_dq07_margin_range_valid(df: pd.DataFrame,
                                 margin_columns=("net_profit_margin_pct", "operating_profit_margin_pct"),
                                 table_name="financial_ratios") -> list[DQFinding]:
    """Flag margins outside -100% to 100%."""

    findings = []
    for column in margin_columns:
        if column not in df.columns:
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        invalid = numeric.notna() & ((numeric < -100) | (numeric > 100))
        for _, row in df[invalid].iterrows():
            findings.append(_finding("DQ-07", "HIGH", table_name, _company_id(row),
                                     column, f"Margin outside valid range: {row[column]}"))
    return findings


def rule_dq08_assets_non_negative(df: pd.DataFrame, asset_column="total_assets",
                                  table_name="balancesheet") -> list[DQFinding]:
    """Flag negative total assets."""

    numeric = pd.to_numeric(df[asset_column], errors="coerce")
    return [_finding("DQ-08", "HIGH", table_name, _company_id(row), asset_column,
                     "Total assets cannot be negative") for _, row in df[numeric < 0].iterrows()]


def rule_dq09_balance_sheet_balances(df: pd.DataFrame, assets_column="total_assets",
                                     liabilities_column="total_liabilities",
                                     equity_column="shareholders_equity",
                                     tolerance_pct=1.0,
                                     table_name="balancesheet") -> list[DQFinding]:
    """Flag material balance-sheet equation mismatches."""

    findings = []
    for _, row in df.iterrows():
        values = pd.to_numeric(pd.Series([
            row[assets_column], row[liabilities_column], row[equity_column]
        ]), errors="coerce")
        if values.isna().any():
            continue
        assets, liabilities, equity = map(float, values)
        difference = abs(assets - (liabilities + equity))
        tolerance = max(abs(assets) * tolerance_pct / 100.0, 1.0)
        if difference > tolerance:
            findings.append(_finding("DQ-09", "CRITICAL", table_name, _company_id(row),
                                     "balance_equation",
                                     f"Assets differ from liabilities + equity by {difference:.2f}"))
    return findings


def rule_dq10_cashflow_reconciles(df: pd.DataFrame,
                                  cfo_column="cash_from_operations",
                                  cfi_column="cash_from_investing",
                                  cff_column="cash_from_financing",
                                  net_change_column="net_change_in_cash",
                                  tolerance=1.0,
                                  table_name="cashflow") -> list[DQFinding]:
    """Flag cash-flow component reconciliation mismatches."""

    findings = []
    for _, row in df.iterrows():
        values = pd.to_numeric(pd.Series([
            row[cfo_column], row[cfi_column], row[cff_column], row[net_change_column]
        ]), errors="coerce")
        if values.isna().any():
            continue
        cfo, cfi, cff, actual = map(float, values)
        expected = cfo + cfi + cff
        if abs(expected - actual) > tolerance:
            findings.append(_finding("DQ-10", "HIGH", table_name, _company_id(row),
                                     "cashflow_reconciliation",
                                     f"Expected {expected:.2f}, found {actual:.2f}"))
    return findings


def rule_dq11_document_url_valid(df: pd.DataFrame, url_column="Annual_Report",
                                 table_name="documents") -> list[DQFinding]:
    """Flag malformed annual-report URLs."""

    findings = []
    for _, row in df.iterrows():
        url = _text(row[url_column])
        parsed = urlparse(url)
        valid = parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc) and bool(parsed.path) and " " not in url
        if not valid:
            findings.append(_finding("DQ-11", "MEDIUM", table_name, _company_id(row),
                                     url_column, "Invalid annual-report URL"))
    return findings


def rule_dq12_required_fields_present(df: pd.DataFrame, required_fields: Iterable[str],
                                      table_name="unknown") -> list[DQFinding]:
    """Flag missing required columns or values."""

    findings = []
    for field in required_fields:
        if field not in df.columns:
            findings.append(_finding("DQ-12", "HIGH", table_name, "ALL", field,
                                     "Required column is missing"))
            continue
        invalid = df[field].isna() | df[field].astype(str).str.strip().eq("")
        for _, row in df[invalid].iterrows():
            findings.append(_finding("DQ-12", "HIGH", table_name, _company_id(row),
                                     field, "Required value is missing"))
    return findings


def rule_dq13_debt_to_equity_outlier(df: pd.DataFrame, threshold=5.0,
                                     table_name="financial_ratios") -> list[DQFinding]:
    """Flag D/E above five for non-financial companies."""

    findings = []
    for _, row in df.iterrows():
        ratio = pd.to_numeric(pd.Series([row["debt_to_equity"]]), errors="coerce").iloc[0]
        sector = _text(row["broad_sector"]).lower()
        financial = sector in {"financials", "financial services", "banking"}
        if not pd.isna(ratio) and float(ratio) > threshold and not financial:
            findings.append(_finding("DQ-13", "HIGH", table_name, _company_id(row),
                                     "debt_to_equity", f"Non-financial D/E exceeds {threshold}"))
    return findings


def rule_dq14_minimum_history(df: pd.DataFrame, minimum_years=10,
                              table_name="unknown") -> list[DQFinding]:
    """Flag companies with fewer than ten unique annual observations."""

    counts = (df.dropna(subset=["company_id", "year"])
              .assign(company_id=lambda x: x["company_id"].astype(str).str.strip())
              .groupby("company_id")["year"].nunique())
    return [_finding("DQ-14", "MEDIUM", table_name, company_id, "year",
                     f"Only {int(count)} unique years; minimum is {minimum_years}")
            for company_id, count in counts.items() if int(count) < minimum_years]


def dq01_company_pk_uniqueness(df: pd.DataFrame) -> bool:
    """Run the legacy DQ-01 interface and log failures."""

    findings = rule_dq01_company_id_unique(df)
    if findings:
        write_validation_failures(findings, append=True)
        print("DQ-01 FAILED")
        return False
    print("DQ-01 PASSED")
    return True


def dq02_annual_pk_uniqueness(df: pd.DataFrame, table_name: str) -> bool:
    """Run the legacy DQ-02 interface and log failures."""

    findings = rule_dq02_annual_key_unique(df, table_name)
    if findings:
        write_validation_failures(findings, append=True)
        print(f"DQ-02 FAILED: {table_name}")
        return False
    print(f"DQ-02 PASSED: {table_name}")
    return True
