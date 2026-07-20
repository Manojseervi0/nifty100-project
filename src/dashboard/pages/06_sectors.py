import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.utils.db import (
    get_pl,
    get_ratios,
    get_sectors,
    get_valuation,
)

st.title("🏭 Sector Analysis")

# ----------------------------------
# Sector Selection
# ----------------------------------

sectors = get_sectors()

if sectors.empty:
    st.warning("No sector data available.")
    st.stop()

sector_options = (
    sectors["broad_sector"]
    .dropna()
    .drop_duplicates()
    .sort_values()
    .tolist()
)

selected_sector = st.selectbox(
    "Select Sector",
    sector_options,
)

st.write(f"Selected Sector: **{selected_sector}**")

# ----------------------------------
# Prepare Bubble Chart Data
# ----------------------------------

sector_companies = sectors[
    sectors["broad_sector"] == selected_sector
].copy()

bubble_rows = []

for _, company in sector_companies.iterrows():
    ticker = company["company_id"]

    ratios = get_ratios(ticker)
    pl = get_pl(ticker)
    valuation = get_valuation(ticker)

    if ratios.empty or pl.empty or valuation.empty:
        continue

    ratios = ratios[ratios["year"] != "TTM"].copy()
    pl = pl[pl["year"] != "TTM"].copy()

    if ratios.empty or pl.empty:
        continue

    ratios["sort_year"] = (
        ratios["year"]
        .astype(str)
        .str.extract(r"(\d{4})")[0]
        .astype(int)
    )

    pl["sort_year"] = (
        pl["year"]
        .astype(str)
        .str.extract(r"(\d{4})")[0]
        .astype(int)
    )

    latest_ratio = ratios.sort_values("sort_year").iloc[-1]
    latest_pl = pl.sort_values("sort_year").iloc[-1]
    latest_valuation = valuation.iloc[-1]

    bubble_rows.append(
    {
        "company_id": ticker,
        "sub_sector": company["sub_sector"],
        "revenue": latest_pl["sales"],
        "roe": latest_ratio["return_on_equity_pct"],
        "market_cap": latest_valuation["market_cap_crore"],
        "roce": latest_ratio[
            "return_on_capital_employed_pct"
        ],
        "net_profit_margin": latest_ratio[
            "net_profit_margin_pct"
        ],
        "debt_to_equity": latest_ratio["debt_to_equity"],
        "revenue_cagr": latest_ratio["revenue_cagr_5yr"],
    }
)

bubble_data = pd.DataFrame(bubble_rows)

# ----------------------------------
# Sector Bubble Chart
# ----------------------------------

st.divider()

st.subheader("🫧 Revenue vs ROE")

if not bubble_data.empty:
    bubble_data = bubble_data.dropna(
        subset=[
            "revenue",
            "roe",
            "market_cap",
        ]
    )

    fig = px.scatter(
        bubble_data,
        x="revenue",
        y="roe",
        size="market_cap",
        color="sub_sector",
        hover_name="company_id",
        size_max=60,
        labels={
            "revenue": "Revenue (₹ Cr)",
            "roe": "ROE (%)",
            "market_cap": "Market Cap (₹ Cr)",
            "sub_sector": "Sub-sector",
        },
        title=f"{selected_sector} — Revenue vs ROE",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        key="sector_bubble_chart",
    )
else:
    st.info("Bubble chart data not available for this sector.")


# ----------------------------------
# Sector Median KPI Bar Chart
# ----------------------------------

st.divider()

st.subheader("📊 Sector Median KPIs")

kpi_columns = {
    "ROE": "roe",
    "ROCE": "roce",
    "Net Profit Margin": "net_profit_margin",
    "Debt / Equity": "debt_to_equity",
    "Revenue CAGR": "revenue_cagr",
}

median_rows = []

for label, column in kpi_columns.items():
    values = pd.to_numeric(
        bubble_data[column],
        errors="coerce",
    )

    median_rows.append(
        {
            "KPI": label,
            "Median": values.median(),
        }
    )

median_data = pd.DataFrame(median_rows).dropna()

if not median_data.empty:
    median_fig = px.bar(
        median_data,
        x="KPI",
        y="Median",
        text_auto=".2f",
        title=f"{selected_sector} — Median KPI Comparison",
        labels={
            "KPI": "Metric",
            "Median": "Median Value",
        },
    )

    median_fig.update_layout(
        showlegend=False,
    )

    st.plotly_chart(
        median_fig,
        use_container_width=True,
        key="sector_median_kpi_chart",
    )
else:
    st.info("Sector median KPI data not available.")