import plotly.express as px
import streamlit as st

from src.dashboard.utils.db import get_capital_allocation


st.title("💰 Capital Allocation Map")

# ----------------------------------
# Load Capital Allocation Data
# ----------------------------------

capital_data = get_capital_allocation()

if capital_data.empty:
    st.warning("Capital allocation data not available.")
    st.stop()

# Zero values are treated as non-negative so that
# the three cash-flow signs form exactly 8 patterns.
capital_data["operating_sign"] = capital_data[
    "operating_activity"
].apply(
    lambda value: "+" if value >= 0 else "-"
)

capital_data["investing_sign"] = capital_data[
    "investing_activity"
].apply(
    lambda value: "+" if value >= 0 else "-"
)

capital_data["financing_sign"] = capital_data[
    "financing_activity"
].apply(
    lambda value: "+" if value >= 0 else "-"
)

capital_data["pattern"] = (
    "Operating "
    + capital_data["operating_sign"]
    + " | Investing "
    + capital_data["investing_sign"]
    + " | Financing "
    + capital_data["financing_sign"]
)

# Equal weight ensures every company appears in the treemap.
capital_data["company_count"] = 1

# ----------------------------------
# Capital Allocation Treemap
# ----------------------------------

st.subheader("🗺️ Capital Allocation Patterns")

fig = px.treemap(
    capital_data,
    path=[
        "pattern",
        "company_id",
    ],
    values="company_count",
    hover_data={
        "year": True,
        "operating_activity": ":,.2f",
        "investing_activity": ":,.2f",
        "financing_activity": ":,.2f",
        "company_count": False,
    },
    title="Nifty 100 Companies by Capital Allocation Pattern",
)

st.plotly_chart(
    fig,
    use_container_width=True,
    key="capital_allocation_treemap",
)

# ----------------------------------
# Companies by Capital Pattern
# ----------------------------------

st.divider()

st.subheader("🏢 Companies by Capital Allocation Pattern")

patterns = sorted(capital_data["pattern"].unique())

selected_pattern = st.selectbox(
    "Select Pattern",
    patterns,
)

pattern_companies = (
    capital_data[
        capital_data["pattern"] == selected_pattern
    ][["company_id"]]
    .sort_values("company_id")
    .reset_index(drop=True)
)

st.write(
    f"**{len(pattern_companies)} companies** "
    f"in {selected_pattern}"
)

st.dataframe(
    pattern_companies,
    use_container_width=True,
    hide_index=True,
)