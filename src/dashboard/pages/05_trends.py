import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.utils.db import (
    get_companies,
    get_ratios,
)

st.title("📈 Trend Analysis")

# ----------------------------------
# Company Search
# ----------------------------------

companies = get_companies()

if companies.empty:
    st.warning("No companies available.")
    st.stop()

company_labels = {
    f"{row['company_name']} ({row['company_id']})": row["company_id"]
    for _, row in companies.iterrows()
}

selected_label = st.selectbox(
    "🔍 Search Company",
    list(company_labels.keys()),
)

selected_company = company_labels[selected_label]

st.write(f"Selected Company: **{selected_company}**")


# ----------------------------------
# Metric Selection
# ----------------------------------

metric_options = {
    "ROE": "return_on_equity_pct",
    "ROCE": "return_on_capital_employed_pct",
    "Net Profit Margin": "net_profit_margin_pct",
    "Debt / Equity": "debt_to_equity",
    "Revenue CAGR": "revenue_cagr_5yr",
    "PAT CAGR": "pat_cagr_5yr",
    "EPS CAGR": "eps_cagr_5yr",
    "Interest Coverage": "interest_coverage",
}

selected_metrics = st.multiselect(
    "Select up to 3 Metrics",
    list(metric_options.keys()),
    default=["ROE"],
    max_selections=3,
)

st.write(
    "Selected Metrics: "
    + ", ".join(selected_metrics)
)

# ----------------------------------
# Load Trend Data
# ----------------------------------

ratios = get_ratios(selected_company)

if ratios.empty:
    st.info(
        "Trend data is not available for this company."
    )
    st.stop()

# Remove TTM rows
ratios = ratios[ratios["year"] != "TTM"].copy()

# Sort chronologically
ratios["sort_year"] = (
    ratios["year"]
    .astype(str)
    .str.extract(r"(\d{4})")[0]
    .astype(int)
)

ratios = (
    ratios
    .sort_values("sort_year")
    .tail(10)
    .drop(columns="sort_year")
)

available_years = len(ratios)

if available_years < 10:
    st.info(
        f"Only {available_years} years of historical data "
        "are available for this company."
    )

# ----------------------------------
# 10-Year Trend Chart
# ----------------------------------

if selected_metrics:
    st.divider()

    st.subheader("📊 10-Year Metric Trends")

    fig = go.Figure()

    for metric_label in selected_metrics:
        metric_column = metric_options[metric_label]
        metric_values = ratios[metric_column].tolist()

        yoy_labels = ["N/A"]

        for index in range(1, len(metric_values)):
            previous_value = metric_values[index - 1]
            current_value = metric_values[index]

            if (
                pd.isna(previous_value)
                or pd.isna(current_value)
                or previous_value == 0
            ):
                yoy_labels.append("N/A")
            else:
                yoy_change = (
                    (current_value - previous_value)
                    / previous_value
                    * 100
                )
                yoy_labels.append(f"{yoy_change:+.1f}%")

        fig.add_trace(
            go.Scatter(
                x=ratios["year"],
                y=ratios[metric_column],
                mode="lines+markers+text",
                text=yoy_labels,
                textposition="top center",
                name=metric_label,
            )
        )

    fig.update_layout(
        title=f"{selected_company} — 10-Year Trend",
        xaxis_title="Year",
        yaxis_title="Value",
        legend_title="Metric",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        key="trend_analysis_chart",
    )
else:
    st.info("Select at least one metric to view the trend.")