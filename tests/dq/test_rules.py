import pandas as pd

from src.etl.validator import (
    rule_dq01_company_id_unique,
    rule_dq02_annual_key_unique,
    rule_dq03_company_id_not_null,
    rule_dq04_year_format_valid,
    rule_dq05_company_fk_valid,
    rule_dq06_revenue_non_negative,
    rule_dq07_margin_range_valid,
    rule_dq08_assets_non_negative,
    rule_dq09_balance_sheet_balances,
    rule_dq10_cashflow_reconciles,
    rule_dq11_document_url_valid,
    rule_dq12_required_fields_present,
    rule_dq13_debt_to_equity_outlier,
    rule_dq14_minimum_history,
)


def assert_finding(findings, rule_id, severity):
    assert findings
    assert findings[0].rule_id == rule_id
    assert findings[0].severity == severity


def test_dq01_duplicate_company_id():
    assert_finding(rule_dq01_company_id_unique(pd.DataFrame({"id": ["TCS", "TCS"]})), "DQ-01", "CRITICAL")


def test_dq02_duplicate_annual_key():
    df = pd.DataFrame({"company_id": ["TCS", "TCS"], "year": [2024, 2024]})
    assert_finding(rule_dq02_annual_key_unique(df), "DQ-02", "CRITICAL")


def test_dq03_null_company_id():
    assert_finding(rule_dq03_company_id_not_null(pd.DataFrame({"company_id": [None]})), "DQ-03", "CRITICAL")


def test_dq04_invalid_year():
    df = pd.DataFrame({"company_id": ["TCS"], "year": ["FYXX"]})
    assert_finding(rule_dq04_year_format_valid(df), "DQ-04", "HIGH")


def test_dq05_orphan_company_id():
    df = pd.DataFrame({"company_id": ["UNKNOWN"]})
    assert_finding(rule_dq05_company_fk_valid(df, {"TCS", "INFY"}), "DQ-05", "CRITICAL")


def test_dq06_negative_revenue():
    df = pd.DataFrame({"company_id": ["TCS"], "sales": [-1]})
    assert_finding(rule_dq06_revenue_non_negative(df), "DQ-06", "HIGH")


def test_dq07_margin_out_of_range():
    df = pd.DataFrame({"company_id": ["TCS"], "net_profit_margin_pct": [125], "operating_profit_margin_pct": [25]})
    assert_finding(rule_dq07_margin_range_valid(df), "DQ-07", "HIGH")


def test_dq08_negative_assets():
    df = pd.DataFrame({"company_id": ["TCS"], "total_assets": [-100]})
    assert_finding(rule_dq08_assets_non_negative(df), "DQ-08", "HIGH")


def test_dq09_balance_sheet_mismatch():
    df = pd.DataFrame({"company_id": ["TCS"], "total_assets": [1000], "total_liabilities": [300], "shareholders_equity": [500]})
    assert_finding(rule_dq09_balance_sheet_balances(df), "DQ-09", "CRITICAL")


def test_dq10_cashflow_not_reconciled():
    df = pd.DataFrame({"company_id": ["TCS"], "cash_from_operations": [100], "cash_from_investing": [-20], "cash_from_financing": [-10], "net_change_in_cash": [20]})
    assert_finding(rule_dq10_cashflow_reconciles(df), "DQ-10", "HIGH")


def test_dq11_invalid_document_url():
    df = pd.DataFrame({"company_id": ["TCS"], "Annual_Report": ["not-a-url"]})
    assert_finding(rule_dq11_document_url_valid(df), "DQ-11", "MEDIUM")


def test_dq12_missing_required_value():
    df = pd.DataFrame({"company_id": ["TCS"], "company_name": [None]})
    assert_finding(rule_dq12_required_fields_present(df, ["company_name"], "companies"), "DQ-12", "HIGH")


def test_dq13_high_de_for_non_financial():
    df = pd.DataFrame({"company_id": ["TCS"], "debt_to_equity": [6.5], "broad_sector": ["Information Technology"]})
    assert_finding(rule_dq13_debt_to_equity_outlier(df), "DQ-13", "HIGH")


def test_dq14_insufficient_history():
    df = pd.DataFrame({"company_id": ["TCS"] * 9, "year": list(range(2016, 2025))})
    assert_finding(rule_dq14_minimum_history(df), "DQ-14", "MEDIUM")
