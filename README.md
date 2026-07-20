# Nifty100 Analytics Dashboard

A financial analytics and valuation platform built using Python, SQLite, Pandas, Plotly, and Streamlit. The project provides company-level financial analysis, screening, peer comparison, trend analysis, sector insights, capital allocation analysis, annual reports, and valuation flags for a 92-company universe.

---

## Tech Stack

- Python
- SQLite
- Pandas
- NumPy
- Plotly
- Streamlit
- OpenPyXL

---

# Sprint 1 - Data Foundation

## Completed

- Environment Setup
- SQLite Database Creation
- ETL Pipeline
- Data Loading
- Data Quality Validation
- 35+ Unit Tests

## Database Tables

- companies
- profitandloss
- balancesheet
- cashflow
- analysis
- documents
- prosandcons
- financial_ratios
- sectors
- peer_groups
- peer_percentiles
- stock_prices
- market_cap

## Outputs

- nifty100.db
- load_audit.csv
- validation_failures.csv
- exploratory_queries.sql

---

# Sprint 2 - Financial Ratio Engine

## Completed

- Profitability Ratios
  - Net Profit Margin
  - Operating Profit Margin
  - ROE
  - ROCE
  - ROA
- Leverage and Efficiency Ratios
- Revenue CAGR Engine
- PAT CAGR Engine
- EPS CAGR Engine
- CAGR Edge Case Handling
- Cash Flow KPI Engine
- Composite Quality Score
- Capital Allocation Classification
- Financial Ratio Validation
- Edge Case Logging
- 71 Unit Tests Passed

## Database Updates

Added the following financial metrics:

- revenue_cagr_5yr
- pat_cagr_5yr
- eps_cagr_5yr
- pat_cagr_5yr_flag
- eps_cagr_5yr_flag
- return_on_capital_employed_pct
- composite_quality_score

## Outputs

- capital_allocation.csv
- ratio_edge_cases.log

## Validation Summary

- Financial ratio data available across the project company universe
- Duplicate company-year records identified and cleaned during integration QA
- 71/71 unit tests passed

---

# Sprint 4 - Streamlit Dashboard and Valuation

Sprint 4 delivers an interactive 8-screen financial analytics dashboard and a valuation module for the Nifty100 project.

## Dashboard Run Instructions

Activate the project virtual environment and run:

```bash
streamlit run src/dashboard/app.py
```

The dashboard will open locally at:

```text
http://localhost:8501
```

---

# Dashboard Screens

## 1. Home

The Home screen provides a high-level overview of the company universe.

Features:

- Average ROE
- Median P/E
- Median Debt-to-Equity
- Total Companies
- Median 5-Year Revenue CAGR
- Debt-Free Companies count
- Sector breakdown donut chart
- Top 5 companies by Composite Quality Score
- Year selector from 2019 to 2024

All dashboard metrics update according to the selected year.

---

## 2. Company Profile

The Company Profile screen provides detailed company-level financial analysis.

Features:

- Company search by name or ticker
- Company name and ticker
- Sector and sub-sector information
- Company description
- ROE
- ROCE
- Net Profit Margin
- Debt-to-Equity
- Revenue CAGR
- Free Cash Flow
- Revenue and Net Profit historical chart
- ROE and ROCE historical trend
- Company pros and cons

Companies with partial financial data are handled gracefully and unavailable metrics are displayed as `N/A`.

---

## 3. Financial Screener

The Financial Screener allows companies to be filtered using multiple financial metrics.

Available filters include:

- Minimum ROE
- Maximum Debt-to-Equity
- Minimum Free Cash Flow
- Minimum Revenue CAGR
- Minimum PAT CAGR
- Minimum Operating Profit Margin
- Maximum P/E
- Maximum P/B
- Minimum Dividend Yield
- Minimum Interest Coverage Ratio

Available presets:

- Quality
- Value
- Growth
- Dividend
- Debt-Free
- Turnaround

The results table updates dynamically as filters change.

The filtered results can also be downloaded as a CSV file.

---

## 4. Peer Comparison

The Peer Comparison screen compares companies within predefined peer groups.

Features:

- Peer group selection
- Company selection
- Radar chart with 8 financial metrics
- Selected company versus peer group average
- KPI comparison table
- Benchmark company highlighting

The radar chart is implemented using Plotly `Scatterpolar`.

---

## 5. Trend Analysis

The Trend Analysis screen allows historical comparison of up to three financial metrics.

Features:

- Company search
- Multi-metric selection
- Maximum of three metrics per chart
- Up to 10 years of historical data
- YoY percentage change annotations
- Partial-data handling

When fewer than 10 years of data are available, the dashboard displays an informational message showing the number of available years.

---

## 6. Sector Analysis

The Sector Analysis screen provides a visual comparison of companies within a selected sector.

Features:

- Sector selection
- Revenue on X-axis
- ROE on Y-axis
- Market Capitalisation represented by bubble size
- Sub-sector represented using bubble categories
- Company-level hover information
- Sector median KPI chart

The screen helps compare profitability, scale, growth, and leverage within sectors.

---

## 7. Capital Allocation Map

The Capital Allocation screen analyses how companies generate and use cash.

Companies are classified into eight possible capital allocation patterns based on the signs of:

- Operating Cash Flow
- Investing Cash Flow
- Financing Cash Flow

Features:

- Treemap covering the company universe
- Capital allocation pattern grouping
- Pattern selector
- Company list for the selected allocation pattern

---

## 8. Annual Reports

The Annual Reports screen provides available company annual report links.

Features:

- Company search
- List of available report years
- Clickable annual report links
- Unavailable report handling
- Red `Report unavailable` status for invalid or unavailable links

Companies without available annual reports are handled without application errors.

---

# Valuation Module

The valuation module is located at:

```text
src/analytics/valuation.py
```

Run the valuation module using:

```bash
python -m src.analytics.valuation
```

## Valuation Metrics

The module calculates:

- P/E
- P/B
- EV/EBITDA
- Free Cash Flow Yield
- 5-Year Median P/E
- Sector Median P/E comparison
- P/E deviation from sector median

FCF Yield is calculated as:

```text
FCF Yield = Free Cash Flow / Market Capitalisation × 100
```

## Valuation Flags

Companies are classified using sector-relative P/E valuation.

### Caution

```text
P/E > Sector Median P/E × 1.5
```

### Discount

```text
P/E < Sector Median P/E × 0.7
```

### Fair

Companies that fall between the Discount and Caution thresholds.

---

# Valuation Outputs

## valuation_summary.xlsx

Location:

```text
output/valuation_summary.xlsx
```

Contains 92 companies with the following columns:

- company_id
- company_name
- sector
- P/E
- P/B
- EV/EBITDA
- FCF_yield_pct
- 5yr_median_PE
- PE_vs_sector_median_pct
- flag

## valuation_flags.csv

Location:

```text
output/valuation_flags.csv
```

Contains companies classified as:

- Caution
- Discount

Final valuation output:

- 92 companies
- 48 Fair
- 30 Discount
- 14 Caution

---

# Integration QA

The complete dashboard was tested across companies from multiple sectors including:

- Information Technology
- Financials
- FMCG
- Energy
- Healthcare

## QA Results

- All 8 Streamlit screens load successfully
- Dashboard tested across multiple company tickers
- Partial-data companies do not crash the application
- Missing metrics are displayed as `N/A`
- Companies with fewer than 10 years of data are handled correctly
- Screener tested with extreme filter values
- Empty screener results do not crash the application
- CSV download tested successfully
- Charts fit within the dashboard page width
- Company Profile load time tested below 3 seconds
- Valuation summary contains exactly 92 companies

---

# Data Quality and Edge Cases

During integration testing, several data edge cases were identified.

## Duplicate Records

Duplicate company-year records were identified in:

- financial_ratios
- cashflow
- profitandloss
- balancesheet

The duplicate records were reviewed before cleanup.

Exact duplicate records were removed while retaining one valid record for each company-year combination.

Conflicting ABB cash-flow-related records were reviewed separately and the internally consistent data series was retained.

## Partial Data

Some companies have fewer than 10 years of historical financial data.

Examples include:

- JIOFIN
- LICI
- ADANIGREEN
- HAL
- IRFC
- LODHA

The Trend Analysis screen displays the available number of historical years instead of failing.

## Missing Financial Ratio Data

ATGL and SBIN are part of the canonical 92-company universe but do not currently have corresponding records in the `financial_ratios` table.

The dashboard handles these companies as partial-data cases:

- Company Profile remains accessible
- Available company information is displayed
- Available Profit & Loss data is displayed
- Missing ratio metrics are shown as `N/A`

---

# Performance Findings

Streamlit database query functions use:

```python
@st.cache_data(ttl=600)
```

This reduces repeated SQLite queries and improves dashboard responsiveness.

Company Profile performance was tested using multiple companies and observed load times remained below the Sprint requirement of 3 seconds.

---

# Sprint 4 Retrospective

## What Went Well

- All 8 dashboard screens were successfully integrated
- Shared cached database functions reduced repeated query execution
- Plotly provided responsive and interactive financial visualisations
- Screener filtering and CSV export worked successfully
- The valuation module successfully generated outputs for the complete 92-company master universe
- Partial and missing data were handled without application crashes

## Data Challenges Discovered

- Duplicate company-year records existed in multiple financial tables
- Some companies had inconsistent historical data coverage
- The company master table and financial ratio data initially had a universe mismatch
- Some companies had missing financial ratio data while other financial datasets were available

## UX Decisions

- Missing financial values are shown as `N/A`
- Partial historical data displays an informational message
- Invalid or unavailable annual report URLs display a clear unavailable status
- Capital allocation patterns can be selected to display the corresponding companies
- Dashboard charts use responsive page-width layouts

## Future Improvements

- Improve source-level data consistency before database loading
- Add automated duplicate detection to the ETL pipeline
- Add more historical market data
- Add automated dashboard integration tests
- Improve company-level data completeness
- Add deployment support for a hosted Streamlit environment

---

# Project Structure

```text
nifty100-project/
│
├── nifty100.db
├── README.md
│
├── output/
│   ├── valuation_summary.xlsx
│   └── valuation_flags.csv
│
└── src/
    ├── analytics/
    │   └── valuation.py
    │
    └── dashboard/
        ├── app.py
        │
        ├── pages/
        │   ├── 01_home.py
        │   ├── 02_profile.py
        │   ├── 03_screener.py
        │   ├── 04_peers.py
        │   ├── 05_trends.py
        │   ├── 06_sectors.py
        │   ├── 07_capital.py
        │   └── 08_reports.py
        │
        └── utils/
            └── db.py
```

---

# Sprint 4 Completion Status

- [x] Streamlit application scaffold
- [x] Home screen
- [x] Company Profile screen
- [x] Financial Screener
- [x] Peer Comparison
- [x] Trend Analysis
- [x] Sector Analysis
- [x] Capital Allocation Map
- [x] Annual Reports
- [x] Valuation module
- [x] valuation_summary.xlsx generated
- [x] valuation_flags.csv generated
- [x] 92-company valuation coverage
- [x] Screener CSV export
- [x] Partial-data handling
- [x] Integration QA
- [x] Performance testing
- [x] README documentation

---

## Final Status

Sprint 4 development, integration QA, valuation outputs, and technical documentation are complete.

The dashboard can be started using:

```bash
streamlit run src/dashboard/app.py
```