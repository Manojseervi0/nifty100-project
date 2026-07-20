import streamlit as st
import pandas as pd

from src.screener.engine import (
    load_screener_data,
    get_latest_year_data,
    apply_filters,
    get_filter_pass_counts,
    load_config,
)

# =====================================================
# Page Config
# =====================================================

st.set_page_config(
    page_title="Stock Screener",
    layout="wide",
)

st.title("🔍 Stock Screener")

# =====================================================
# Load Config & Data
# =====================================================

config = load_config()

df = load_screener_data()

# Latest Year Only
# NOTE: `year` is a text label ("Mar 2019", "Dec 2023", ...) and does
# NOT sort chronologically as a string. get_latest_year_data() uses
# the numeric year extracted from that label instead.
df = get_latest_year_data(df)

# =====================================================
# Session State
# =====================================================

# NOTE: max_pe=20 / max_pb=3 are deep-value thresholds. On a
# large-cap Nifty100 universe, only a small minority of companies
# ever trade that cheap, so combining that with 8 other simultaneous
# quality/growth conditions can realistically yield 0 matches. These
# defaults are set to realistic large-cap ranges so "Custom" mode
# starts with a non-empty, still-meaningful result set. Users can
# tighten toward value-investor thresholds deliberately via the
# sliders once they see the trade-off (the diagnostic panel below
# shows exactly which filter is the bottleneck if they do).
default_filters = {
    "min_roe": 15.0,
    "max_de": 2.0,
    "min_fcf": 0.0,
    "min_revenue_cagr_5yr": 8.0,
    "min_pat_cagr_5yr": 8.0,
    "min_opm": 10.0,
    "max_pe": 40.0,
    "max_pb": 8.0,
    "min_dividend_yield": 0.5,
    "min_icr": 1.5,
}

if "filters" not in st.session_state:
    st.session_state.filters = default_filters.copy()

# =====================================================
# Sidebar
# =====================================================

st.sidebar.title("Screeners")

preset = st.sidebar.selectbox(
    "Choose Preset",
    [
        "Custom",
        "quality_compounder",
        "value_pick",
        "growth_accelerator",
        "dividend_champion",
        "debt_free_blue_chip",
        "turnaround_watch",
    ],
)

if preset != "Custom":
    preset_filters = config["presets"][preset]

    temp = default_filters.copy()
    temp.update(preset_filters)

    st.session_state.filters = temp

filters = st.session_state.filters

st.sidebar.divider()

st.sidebar.header("Filters")

# =====================================================
# Filters
# =====================================================

filters["min_roe"] = st.sidebar.slider(
    "Minimum ROE (%)",
    0.0,
    60.0,
    float(filters["min_roe"]),
    0.5,
)

filters["max_de"] = st.sidebar.slider(
    "Maximum Debt / Equity",
    0.0,
    5.0,
    float(filters["max_de"]),
    0.1,
)

filters["min_fcf"] = st.sidebar.number_input(
    "Minimum Free Cash Flow (Cr)",
    value=float(filters["min_fcf"]),
)

filters["min_revenue_cagr_5yr"] = st.sidebar.slider(
    "Revenue CAGR 5Y (%)",
    -50.0,
    100.0,
    float(filters["min_revenue_cagr_5yr"]),
    1.0,
)

filters["min_pat_cagr_5yr"] = st.sidebar.slider(
    "PAT CAGR 5Y (%)",
    -50.0,
    100.0,
    float(filters["min_pat_cagr_5yr"]),
    1.0,
)

filters["min_opm"] = st.sidebar.slider(
    "Operating Profit Margin (%)",
    -20.0,
    80.0,
    float(filters["min_opm"]),
    1.0,
)

filters["max_pe"] = st.sidebar.slider(
    "Maximum P/E",
    0.0,
    150.0,
    float(filters["max_pe"]),
    1.0,
)

filters["max_pb"] = st.sidebar.slider(
    "Maximum P/B",
    0.0,
    20.0,
    float(filters["max_pb"]),
    0.5,
)

filters["min_dividend_yield"] = st.sidebar.slider(
    "Minimum Dividend Yield (%)",
    0.0,
    10.0,
    float(filters["min_dividend_yield"]),
    0.1,
)

filters["min_icr"] = st.sidebar.slider(
    "Minimum Interest Coverage",
    0.0,
    20.0,
    float(filters["min_icr"]),
    0.5,
)

# =====================================================
# Apply Filters
# =====================================================

result = apply_filters(df, filters)

# =====================================================
# Top Metrics
# =====================================================

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "Matching Companies",
        len(result),
    )

with col2:
    avg_score = (
        result["composite_quality_score"].mean()
        if not result.empty
        else 0
    )

    st.metric(
        "Average Quality Score",
        f"{avg_score:.2f}",
    )

with col3:
    best_company = (
        result.iloc[0]["company_name"]
        if not result.empty
        else "-"
    )

    st.metric(
        "Top Ranked Company",
        best_company,
    )

if result.empty:
    st.warning(
        "No companies match this combination of filters. "
        "See below for which filter is the bottleneck."
    )

    diagnostics = get_filter_pass_counts(df, filters)

    diagnostics_display = diagnostics.rename(columns={
        "filter": "Filter",
        "threshold": "Threshold",
        "passes_alone": "Passes (this filter only)",
        "passes_in_combination": "Passes (combined so far)",
        "total_rows": "Total Companies",
    })

    st.dataframe(
        diagnostics_display,
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "'Passes (this filter only)' shows how many of the 92 "
        "companies satisfy that one condition on its own. "
        "'Passes (combined so far)' applies filters cumulatively in "
        "the order shown, so a large drop between rows tells you "
        "which filter is the actual bottleneck once combined with "
        "the ones above it."
    )

st.divider()

# =====================================================
# Sort Results
# =====================================================

result = result.sort_values(
    by="composite_quality_score",
    ascending=False,
)

# =====================================================
# Display Columns
# =====================================================

display_df = result[
    [
        "company_id",
        "company_name",
        "broad_sector",
        "return_on_equity_pct",
        "debt_to_equity",
        "free_cash_flow_cr",
        "revenue_cagr_5yr",
        "pat_cagr_5yr",
        "operating_profit_margin_pct",
        "interest_coverage",
        "pe_ratio",
        "pb_ratio",
        "dividend_yield_pct",
        "market_cap_crore",
        "composite_quality_score",
    ]
].copy()

display_df.columns = [
    "Ticker",
    "Company",
    "Sector",
    "ROE %",
    "D/E",
    "FCF (Cr)",
    "Revenue CAGR 5Y",
    "PAT CAGR 5Y",
    "OPM %",
    "ICR",
    "P/E",
    "P/B",
    "Dividend Yield %",
    "Market Cap (Cr)",
    "Quality Score",
]

display_df = display_df.round(2)

# =====================================================
# Download CSV
# =====================================================

csv = display_df.to_csv(index=False).encode("utf-8")

st.download_button(
    label="📥 Download CSV",
    data=csv,
    file_name="screener_results.csv",
    mime="text/csv",
)

st.divider()

# =====================================================
# Result Table
# =====================================================

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
)

# =====================================================
# Footer
# =====================================================

st.caption(
    f"Showing {len(display_df)} companies matching current filters."
)