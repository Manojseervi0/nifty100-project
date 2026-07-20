import sqlite3

import pandas as pd
import streamlit as st

DB_PATH = "nifty100.db"


@st.cache_data(ttl=600)
def run_query(query: str) -> pd.DataFrame:
    """
    Execute SQL query and return DataFrame.
    """
    conn = sqlite3.connect(DB_PATH)

    try:
        df = pd.read_sql(query, conn)
    finally:
        conn.close()

    return df


@st.cache_data(ttl=600)
def get_companies():
    query = """
    SELECT
        id AS company_id,
        company_name
    FROM companies
    ORDER BY company_name
    """
    return run_query(query)


@st.cache_data(ttl=600)
def get_ratios(company_id, year=None):
    """
    Load financial ratios for a company.
    Returns all years unless a specific year is provided.
    """

    query = f"""
    SELECT
        fr.*,
        c.company_name,
        c.about_company,
        c.website,
        s.broad_sector,
        mc.market_cap_crore
    FROM financial_ratios fr

    LEFT JOIN companies c
        ON fr.company_id = c.id

    LEFT JOIN sectors s
        ON fr.company_id = s.company_id

    LEFT JOIN market_cap mc
        ON fr.company_id = mc.company_id
       AND CAST(SUBSTR(fr.year, -4) AS INTEGER) = mc.year

    WHERE fr.company_id = '{company_id}'
    """

    if year:
        query += f" AND fr.year = '{year}'"

    query += """
    ORDER BY CAST(SUBSTR(fr.year, -4) AS INTEGER)
    """

    df = run_query(query)

    scaled_companies = {"BEL", "HAL", "INDIGO"}

    if company_id in scaled_companies:
        df["return_on_equity_pct"] = (
            df["return_on_equity_pct"] / 100
        )
        df["return_on_capital_employed_pct"] = (
            df["return_on_capital_employed_pct"] / 100
        )

    return df


@st.cache_data(ttl=600)
def get_pl(ticker):
    """
    Load Profit & Loss data.
    """

    query = f"""
    SELECT
        year,
        sales,
        net_profit
    FROM profitandloss
    WHERE company_id = '{ticker}'
    ORDER BY CAST(SUBSTR(year, -4) AS INTEGER)
    """

    return run_query(query)


@st.cache_data(ttl=600)
def get_bs(ticker):
    """
    Load Balance Sheet data.
    """

    query = f"""
    SELECT *
    FROM balancesheet
    WHERE company_id = '{ticker}'
    ORDER BY CAST(SUBSTR(year, -4) AS INTEGER)
    """

    return run_query(query)


@st.cache_data(ttl=600)
def get_cf(ticker):
    """
    Load Cash Flow data.
    """

    query = f"""
    SELECT *
    FROM cashflow
    WHERE company_id = '{ticker}'
    ORDER BY CAST(SUBSTR(year, -4) AS INTEGER)
    """

    return run_query(query)

@st.cache_data(ttl=600)
def get_capital_allocation() -> pd.DataFrame:
    """
    Load latest cash flow data for the 92 dashboard companies.
    """

    query = """
    WITH latest_cashflow AS (
        SELECT
            cf.company_id,
            cf.year,
            cf.operating_activity,
            cf.investing_activity,
            cf.financing_activity,
            ROW_NUMBER() OVER (
                PARTITION BY cf.company_id
                ORDER BY CAST(cf.id AS INTEGER) DESC
            ) AS row_num
        FROM cashflow cf
        INNER JOIN (
            SELECT DISTINCT company_id
            FROM financial_ratios
        ) fr
            ON cf.company_id = fr.company_id
    )
    SELECT
        company_id,
        year,
        operating_activity,
        investing_activity,
        financing_activity
    FROM latest_cashflow
    WHERE row_num = 1
    ORDER BY company_id
    """

    return run_query(query)


@st.cache_data(ttl=600)
def get_sectors():
    """
    Load sector information.
    """

    query = """
    SELECT *
    FROM sectors
    ORDER BY broad_sector, company_id
    """

    return run_query(query)


@st.cache_data(ttl=600)
def get_peers(group_name):
    """
    Load peer group companies.
    """

    query = f"""
    SELECT *
    FROM peer_groups
    WHERE peer_group_name = '{group_name}'
    ORDER BY company_id
    """

    return run_query(query)


@st.cache_data(ttl=600)
def get_peer_groups() -> pd.DataFrame:
    """
    Load all available peer group names.
    """

    query = """
    SELECT DISTINCT peer_group_name
    FROM peer_groups
    WHERE peer_group_name IS NOT NULL
    ORDER BY peer_group_name
    """

    return run_query(query)

@st.cache_data(ttl=600)
def get_peer_percentiles(group_name: str) -> pd.DataFrame:
    """
    Load peer percentile data for a peer group.
    """

    query = f"""
    SELECT
        company_id,
        peer_group_name,
        metric,
        value,
        percentile_rank,
        year,
        is_benchmark
    FROM peer_percentiles
    WHERE peer_group_name = '{group_name}'
    """

    return run_query(query)

@st.cache_data(ttl=600)
def get_valuation(ticker):
    """
    Load valuation data.
    """

    query = f"""
    SELECT *
    FROM market_cap
    WHERE company_id = '{ticker}'
    ORDER BY year
    """

    return run_query(query)

@st.cache_data(ttl=600)
def get_pros_cons(ticker: str) -> pd.DataFrame:
    """
    Load Pros & Cons for a company.
    """
    query = f"""
    SELECT
        pros,
        cons
    FROM prosandcons
    WHERE company_id = '{ticker}'
    """

    return run_query(query)

@st.cache_data(ttl=600)
def get_annual_reports(ticker: str) -> pd.DataFrame:
    """
    Load available annual reports for a company.
    """

    query = f"""
    SELECT
        Year AS year,
        Annual_Report AS report_url
    FROM documents
    WHERE company_id = '{ticker}'
    ORDER BY Year DESC
    """

    return run_query(query)

