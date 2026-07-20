

import plotly.graph_objects as go
import streamlit as st

from src.dashboard.utils.db import (
    get_peer_groups,
    get_peer_percentiles,
    get_peers,
)

st.title("🤝 Peer Comparison")

# ----------------------------------
# Load Peer Groups
# ----------------------------------

peer_groups = get_peer_groups()

if peer_groups.empty:
    st.warning("No peer groups available.")
    st.stop()

selected_group = st.selectbox(
    "Select Peer Group",
    peer_groups["peer_group_name"].tolist(),
)

st.write(f"Selected Peer Group: **{selected_group}**")


# ----------------------------------
# Load Peer Data
# ----------------------------------

peers = get_peers(selected_group)
peer_data = get_peer_percentiles(selected_group)

if peers.empty or peer_data.empty:
    st.warning("Peer comparison data not available.")
    st.stop()

# Use benchmark company as the default selection
company_options = peers["company_id"].tolist()

benchmark = peers[peers["is_benchmark"] == 1]

if not benchmark.empty:
    benchmark_company = benchmark.iloc[0]["company_id"]
    default_index = company_options.index(benchmark_company)
else:
    default_index = 0

selected_company = st.selectbox(
    "Select Company",
    company_options,
    index=default_index,
)

# ----------------------------------
# Prepare Latest Peer Metrics
# ----------------------------------

peer_data["sort_year"] = (
    peer_data["year"]
    .astype(str)
    .str.extract(r"(\d{4})")[0]
    .astype(int)
)

latest_peer_data = (
    peer_data
    .sort_values("sort_year")
    .drop_duplicates(
        subset=["company_id", "metric"],
        keep="last",
    )
)

radar_metrics = [
    "return_on_equity_pct",
    "return_on_capital_employed_pct",
    "net_profit_margin_pct",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "eps_cagr_5yr",
    "interest_coverage",
    "debt_to_equity",
]

metric_labels = {
    "return_on_equity_pct": "ROE",
    "return_on_capital_employed_pct": "ROCE",
    "net_profit_margin_pct": "Net Profit Margin",
    "revenue_cagr_5yr": "Revenue CAGR",
    "pat_cagr_5yr": "PAT CAGR",
    "eps_cagr_5yr": "EPS CAGR",
    "interest_coverage": "Interest Coverage",
    "debt_to_equity": "Debt / Equity",
}

radar_data = latest_peer_data[
    latest_peer_data["metric"].isin(radar_metrics)
].copy()

selected_metrics = (
    radar_data[
        radar_data["company_id"] == selected_company
    ]
    .set_index("metric")
    .reindex(radar_metrics)
)

peer_average = (
    radar_data
    .groupby("metric")["percentile_rank"]
    .mean()
    .reindex(radar_metrics)
)

# ----------------------------------
# Radar Chart
# ----------------------------------

st.divider()

st.subheader("📊 Company vs Peer Group Average")

categories = [
    metric_labels[metric]
    for metric in radar_metrics
]

company_values = (
    selected_metrics["percentile_rank"]
    .astype(float)
    .mul(100)
    .tolist()
)

average_values = (
    peer_average
    .astype(float)
    .mul(100)
    .tolist()
)

fig = go.Figure()

fig.add_trace(
    go.Scatterpolar(
        r=company_values,
        theta=categories,
        fill="toself",
        name=selected_company,
    )
)

fig.add_trace(
    go.Scatterpolar(
        r=average_values,
        theta=categories,
        fill="toself",
        name="Peer Group Average",
    )
)

fig.update_layout(
    polar={
        "radialaxis": {
            "visible": True,
            "range": [0, 100],
        }
    },
    showlegend=True,
    title=(
        f"{selected_company} vs "
        f"{selected_group} Average"
    ),
)

st.plotly_chart(
    fig,
    use_container_width=True,
    key="peer_radar_chart",
)

# ----------------------------------
# KPI Comparison Table
# ----------------------------------

st.divider()

st.subheader("📋 Peer KPI Comparison")

comparison_table = (
    radar_data
    .pivot(
        index="company_id",
        columns="metric",
        values="value",
    )
    .reindex(
        index=company_options,
        columns=radar_metrics,
    )
    .rename(columns=metric_labels)
)

comparison_table.index.name = "Company"

benchmark_companies = set(
    peers.loc[
        peers["is_benchmark"] == 1,
        "company_id",
    ].tolist()
)

styled_table = (
    comparison_table.style
    .apply(
        lambda row: [
            "background-color: #5c4d16; font-weight: bold;"
            if row.name in benchmark_companies
            else ""
            for _ in row
        ],
        axis=1,
    )
    .format("{:.2f}", na_rep="N/A")
)

st.dataframe(
    styled_table,
    use_container_width=True,
)