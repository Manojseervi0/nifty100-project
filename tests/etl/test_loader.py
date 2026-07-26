import sqlite3
from pathlib import Path
import importlib

import pytest


DB_PATH = Path("nifty100.db")


@pytest.fixture(scope="module")
def load_database():
    """
    Importing loader.py executes the ETL script and loads
    all Excel files into the SQLite database.
    """
    import src.etl.loader as loader
    importlib.reload(loader)
    yield


def get_tables():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table'
    """)

    tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    return tables


def table_row_count(table_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]

    conn.close()
    return count


def table_columns(table_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(f"PRAGMA table_info({table_name})")
    cols = [row[1] for row in cursor.fetchall()]

    conn.close()
    return cols


def test_database_created(load_database):
    assert DB_PATH.exists()


@pytest.mark.parametrize(
    "table",
    [
        "companies",
        "profitandloss",
        "balancesheet",
        "cashflow",
        "analysis",
        "documents",
        "prosandcons",
        "financial_ratios",
        "sectors",
        "peer_groups",
        "stock_prices",
        "market_cap",
    ],
)
def test_table_exists(load_database, table):
    assert table in get_tables()


@pytest.mark.parametrize(
    "table",
    [
        "companies",
        "profitandloss",
        "balancesheet",
        "cashflow",
        "analysis",
        "documents",
        "prosandcons",
        "financial_ratios",
        "sectors",
        "peer_groups",
        "stock_prices",
        "market_cap",
    ],
)
def test_table_not_empty(load_database, table):
    assert table_row_count(table) > 0


def test_companies_has_id(load_database):
    cols = table_columns("companies")
    assert "id" in cols


def test_profitandloss_has_company_id(load_database):
    cols = table_columns("profitandloss")
    assert "company_id" in cols


def test_balancesheet_has_company_id(load_database):
    cols = table_columns("balancesheet")
    assert "company_id" in cols


def test_cashflow_has_company_id(load_database):
    cols = table_columns("cashflow")
    assert "company_id" in cols


def test_analysis_has_company_id(load_database):
    cols = table_columns("analysis")
    assert "company_id" in cols





def test_company_ids_not_null(load_database):
    conn = sqlite3.connect(DB_PATH)

    df = __import__("pandas").read_sql(
        "SELECT id FROM companies",
        conn,
    )

    conn.close()

    assert df["id"].isna().sum() == 0


def test_company_ids_are_strings(load_database):
    conn = sqlite3.connect(DB_PATH)

    df = __import__("pandas").read_sql(
        "SELECT id FROM companies",
        conn,
    )

    conn.close()

    assert df["id"].astype(str).str.strip().ne("").all()