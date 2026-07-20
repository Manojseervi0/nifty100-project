import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

st.set_page_config(
    page_title="Nifty 100 Analytics",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 Nifty 100 Financial Intelligence Platform")

st.markdown(
    """
Welcome to the **Nifty 100 Financial Intelligence Platform**.

Use the navigation menu on the left to explore:

- 🏠 Home
- 🏢 Company Profile
- 🔍 Stock Screener
- 👥 Peer Comparison
- 📈 Trend Analysis
- 🏭 Sector Analysis
- 💰 Capital Allocation
- 📄 Annual Reports
"""
)

st.success("Dashboard initialized successfully.")