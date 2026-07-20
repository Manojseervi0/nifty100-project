import streamlit as st
import plotly.express as px

from src.dashboard.utils.db import run_query

st.title("🏠 Home Dashboard")

# -------------------------------
# Load Data
# -------------------------------

query = """
SELECT
    fr.company_id,
    fr.year,
    fr.return_on_equity_pct,
    fr.debt_to_equity,
    fr.revenue_cagr_5yr,
    fr.composite_quality_score,
    mc.pe_ratio,
    s.broad_sector
FROM financial_ratios fr

LEFT JOIN market_cap mc
    ON fr.company_id = mc.company_id
   AND CAST(SUBSTR(fr.year, -4) AS INTEGER) = mc.year

LEFT JOIN sectors s
ON fr.company_id = s.company_id

ORDER BY fr.year
"""

df = run_query(query)
total_companies = df["company_id"].nunique()
# -------------------------------
# Year Selector
# -------------------------------

df["calendar_year"] = (
    df["year"]
    .str.extract(r"(\d{4})")[0]
    .astype(int)
)

years = sorted(
    df.loc[
        df["calendar_year"].between(2019, 2024),
        "calendar_year",
    ].unique()
)

selected_year = st.sidebar.selectbox(
    "📅 Select Year",
    years,
    index=len(years) - 1,
)

df = df[df["calendar_year"] == selected_year]

df = (
    df.sort_values("year")
      .drop_duplicates(subset="company_id", keep="last")
      .reset_index(drop=True)
)
# Correct known ROE scaling issues in source data
roe_scaled_companies = ["BEL", "HAL", "INDIGO"]

df.loc[
    df["company_id"].isin(roe_scaled_companies),
    "return_on_equity_pct",
] /= 100    
# -------------------------------
# KPI Cards
# -------------------------------

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "Total Companies",
        total_companies
    )

with col2:
    st.metric(
        "Average ROE",
        f"{df['return_on_equity_pct'].mean():.2f}%"
    )

with col3:
    st.metric(
        "Median P/E",
        f"{df['pe_ratio'].median():.2f}"
    )

col4, col5, col6 = st.columns(3)

with col4:
    st.metric(
        "Median D/E",
        f"{df['debt_to_equity'].median():.2f}"
    )

with col5:
    st.metric(
        "Median Revenue CAGR",
        f"{df['revenue_cagr_5yr'].median():.2f}%"
    )

with col6:
    debt_free = (df["debt_to_equity"] == 0).sum()

    st.metric(
        "Debt Free Companies",
        debt_free
    )

st.divider()

# -------------------------------
# Sector Donut
# -------------------------------

sector_df = (
    df.groupby("broad_sector")
      .size()
      .reset_index(name="Companies")
)

fig = px.pie(
    sector_df,
    names="broad_sector",
    values="Companies",
    hole=0.5,
    title="Sector Distribution"
)

st.plotly_chart(
    fig,
    use_container_width=True
)

st.divider()

# -------------------------------
# Top Companies
# -------------------------------

st.subheader("🏆 Top 5 Companies by Quality Score")

top5 = (
    df.sort_values(
        "composite_quality_score",
        ascending=False
    )
    .head(5)
)

st.dataframe(
    top5[
        [
            "company_id",
            "broad_sector",
            "return_on_equity_pct",
            "composite_quality_score",
        ]
    ],
    use_container_width=True,
)