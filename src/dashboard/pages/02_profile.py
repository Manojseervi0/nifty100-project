import streamlit as st
import plotly.express as px

from src.dashboard.utils.db import (
    get_companies,
    get_ratios,
    get_pl,
    get_pros_cons,
    get_sectors,
)
st.title("🏢 Company Profile")

# ----------------------------------
# Load Company List
# ----------------------------------

companies = get_companies()
companies = companies.sort_values("company_id")

selected_company = st.selectbox(
    "🔍 Select Company",
    companies["company_id"].tolist(),
    accept_new_options=True,
)

st.divider()

# ----------------------------------
# Load Financial Ratios
# ----------------------------------

ratios = get_ratios(selected_company)

if ratios.empty:
    company_row = companies[
        companies["company_id"] == selected_company
    ]

    company_name = (
        company_row.iloc[0]["company_name"]
        if not company_row.empty
        else selected_company
    )

    sectors = get_sectors()
    sector_row = sectors[
        sectors["company_id"] == selected_company
    ]

    sector = "N/A"
    sub_sector = "N/A"

    if not sector_row.empty:
        if "broad_sector" in sector_row.columns:
            sector = sector_row.iloc[0]["broad_sector"]

        if "sub_sector" in sector_row.columns:
            sub_sector = sector_row.iloc[0]["sub_sector"]

    st.info(
        "Financial ratio data is partially available for this company. "
        "Missing metrics are shown as N/A."
    )

    st.markdown(f"## {company_name}")
    st.write(f"**Ticker:** {selected_company}")
    st.write(f"**Sector:** {sector}")
    st.write(f"**Sub-sector:** {sub_sector}")

    kpi_labels = [
        "ROE",
        "ROCE",
        "Net Profit Margin",
        "D/E",
        "Revenue CAGR 5yr",
        "FCF",
    ]

    kpi_cols = st.columns(6)

    for col, label in zip(kpi_cols, kpi_labels):
        col.metric(label, "N/A")

    pl = get_pl(selected_company)

    if not pl.empty:
        st.subheader("Revenue & Net Profit")

        pl_chart = pl[
            pl["year"].astype(str).str.upper() != "TTM"
        ].copy()

        pl_chart = pl_chart.tail(10)

        fig = px.bar(
            pl_chart,
            x="year",
            y=["sales", "net_profit"],
            barmode="group",
            labels={
                "value": "Amount",
                "year": "Year",
                "variable": "Metric",
            },
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Revenue and profit data is not available.")

    st.stop()

# Remove TTM rows
ratios = ratios[ratios["year"] != "TTM"].copy()

# Sort by extracted year
ratios["sort_year"] = (
    ratios["year"]
    .str.extract(r"(\d{4})")
    .astype(int)
)

ratios = (
    ratios.sort_values("sort_year")
          .drop(columns="sort_year")
)

latest = ratios.iloc[-1]

# ----------------------------------
# Company Card
# ----------------------------------

st.subheader(f"📈 {selected_company}")

col1, col2 = st.columns(2)

with col1:
    st.write(f"**Ticker:** {selected_company}")

    if "company_name" in latest:
        st.write(f"**Company:** {latest['company_name']}")

    if "broad_sector" in latest:
        st.write(f"**Sector:** {latest['broad_sector']}")

    st.write(f"**Latest Year:** {latest['year']}")

with col2:

    if "market_cap_crore" in latest:
        st.write(
            f"**Market Cap:** ₹ {latest['market_cap_crore']:,.2f} Cr"
        )

    if "composite_quality_score" in latest:
        st.write(
            f"**Quality Score:** {latest['composite_quality_score']:.2f}"
        )

st.divider()

# ----------------------------------
# KPI Cards
# ----------------------------------

c1, c2, c3 = st.columns(3)

c1.metric(
    "ROE",
    f"{latest['return_on_equity_pct']:.2f}%"
)

c2.metric(
    "ROCE",
    f"{latest['return_on_capital_employed_pct']:.2f}%"
)

c3.metric(
    "Net Profit Margin",
    f"{latest['net_profit_margin_pct']:.2f}%"
)

c4, c5, c6 = st.columns(3)

c4.metric(
    "Debt / Equity",
    f"{latest['debt_to_equity']:.2f}"
)

c5.metric(
    "Revenue CAGR",
    f"{latest['revenue_cagr_5yr']:.2f}%"
)

c6.metric(
    "Free Cash Flow",
    f"{latest['free_cash_flow_cr']:,.2f} Cr"
)
st.divider()

st.subheader("📝 About Company")

if (
    "about_company" in latest.index
    and latest["about_company"] is not None
    and str(latest["about_company"]).strip() != ""
):
    st.write(latest["about_company"])
else:
    st.info("About company not available.")

# ----------------------------------
# Revenue vs Net Profit
# ----------------------------------

pl = get_pl(selected_company)

if not pl.empty:

    pl = pl[pl["year"] != "TTM"].copy()

    pl["sort_year"] = (
        pl["year"]
        .str.extract(r"(\d{4})")
        .astype(int)
    )

    pl = (
        pl.sort_values("sort_year")
          .drop(columns="sort_year")
    )

    st.divider()

    st.subheader("📊 Revenue vs Net Profit (10 Years)")

    fig = px.bar(
        pl,
        x="year",
        y=["sales", "net_profit"],
        barmode="group",
        title=f"{selected_company} Financial Performance",
        labels={
            "value": "₹ Crore",
            "variable": "Metric",
        },
    )

    fig.update_layout(
        xaxis_title="Year",
        yaxis_title="₹ Crore",
        legend_title=""
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

else:
    st.info("No Profit & Loss history available.")

# ----------------------------------
# ROE vs ROCE Trend
# ----------------------------------

st.divider()

st.subheader("📈 ROE vs ROCE Trend")

fig = px.line(
    ratios,
    x="year",
    y=[
        "return_on_equity_pct",
        "return_on_capital_employed_pct",
    ],
    markers=True,
    title=f"{selected_company} ROE vs ROCE Trend",
)

fig.update_layout(
    xaxis_title="Year",
    yaxis_title="Percentage (%)",
    legend_title=""
)

st.plotly_chart(
    fig,
    use_container_width=True,
)



# ----------------------------------
# Pros & Cons
# ----------------------------------

st.divider()

st.subheader("✅ Pros & ❌ Cons")

pros_cons = get_pros_cons(selected_company)

if not pros_cons.empty:

    pros_col, cons_col = st.columns(2)

    with pros_col:
        st.markdown("### ✅ Pros")

        pros = pros_cons["pros"].dropna()

        if not pros.empty:
            for pro in pros:
                if str(pro).strip():
                    st.success(str(pro))
        else:
            st.info("No pros available.")

    with cons_col:
        st.markdown("### ❌ Cons")

        cons = pros_cons["cons"].dropna()

        if not cons.empty:
            for con in cons:
                if str(con).strip():
                    st.error(str(con))
        else:
            st.info("No cons available.")

else:
    st.info("Pros and cons not available for this company.")