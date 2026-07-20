from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st

from src.dashboard.utils.db import (
    get_annual_reports,
    get_companies,
)

st.title("📄 Annual Reports")

@st.cache_data(ttl=3600, show_spinner=False)
def report_returns_404(url: str) -> bool:
    """
    Check whether an annual report URL is unavailable.
    """
    url = str(url).strip()

    if (
        not url
        or url.lower() in {"null", "none", "nan"}
        or not url.startswith(("http://", "https://"))
    ):
        return True

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
        },
    )

    try:
        with urlopen(request, timeout=5):
            return False
    except HTTPError as error:
        return error.code == 404
    except (URLError, ValueError):
        return False

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
# Annual Report List
# ----------------------------------

reports = get_annual_reports(selected_company)

st.divider()

st.subheader("📚 Available Annual Reports")

if reports.empty:
    st.info("No annual reports available for this company.")
else:
    for _, report in reports.iterrows():
        year = int(report["year"])
        report_url = report["report_url"]

        col1, col2 = st.columns([1, 3])

        with col1:
            st.write(f"**{year}**")

        with col2:
            if report_returns_404(report_url):
                st.error("🔴 Report unavailable")
            else:
                st.link_button(
                    "Open BSE Annual Report",
                    report_url,
                )