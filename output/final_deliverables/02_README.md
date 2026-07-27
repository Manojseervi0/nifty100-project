# Nifty100 Analytics Dashboard

A comprehensive financial analytics, screening, valuation, cash-flow intelligence, NLP, and automated reporting platform built for a 92-company Nifty100 project universe.

The project combines a validated SQLite data foundation with financial ratio computation, screening, peer comparison, interactive Streamlit dashboards, valuation analysis, automated pros/cons generation, cash-flow intelligence, capital allocation analysis, and PDF reporting.

---

## Tech Stack

- Python
- SQLite
- Pandas
- NumPy
- Plotly
- Streamlit
- Matplotlib
- OpenPyXL
- ReportLab

---

## Project Status

| Sprint | Module | Status |
|---|---|---|
| Sprint 1 | Data Foundation | ✅ Completed |
| Sprint 2 | Financial Ratio Engine | ✅ Completed |
| Sprint 3 | Screener & Peer Comparison Engine | ✅ Completed |
| Sprint 4 | Dashboard & Valuation Module | ✅ Completed |
| Sprint 5 | Intelligence, NLP & PDF Reports | ✅ Completed |

---

# Sprint 1 - Data Foundation

Sprint 1 established the complete data foundation for the project.

## Completed

- Environment setup
- SQLite database creation
- ETL pipeline
- Data loading and normalisation
- Data quality validation
- Primary and foreign key checks
- Load audit generation
- 35+ ETL unit tests

## Core Data Tables

- `companies`
- `profitandloss`
- `balancesheet`
- `cashflow`
- `analysis`
- `documents`
- `prosandcons`
- `financial_ratios`
- `sectors`
- `peer_groups`
- `peer_percentiles`
- `stock_prices`
- `market_cap`

## Major Outputs

```text
nifty100.db
output/load_audit.csv
output/validation_failures.csv
notebooks/exploratory_queries.sql
```

## Validation Summary

- 92 companies loaded into the canonical company universe
- Data quality rules implemented and reviewed
- Foreign key validation completed
- Critical ETL issues resolved before downstream analytics
- Historical financial data made available for subsequent modules

---

# Sprint 2 - Financial Ratio Engine

Sprint 2 introduced the core financial analytics engine.

## Profitability Metrics

- Net Profit Margin
- Operating Profit Margin
- Return on Equity
- Return on Capital Employed
- Return on Assets

## Leverage and Efficiency Metrics

- Debt-to-Equity
- Interest Coverage Ratio
- Net Debt
- Asset Turnover

## Growth Metrics

- Revenue CAGR
- PAT CAGR
- EPS CAGR

CAGR calculations include edge-case handling for:

- Normal positive growth
- Turnaround
- Decline to loss
- Both periods negative
- Zero base
- Insufficient historical data

## Cash Flow KPIs

- Free Cash Flow
- CFO Quality
- CapEx Intensity
- FCF Conversion
- Capital Allocation Classification

## Composite Quality Score

A composite quality score is calculated using profitability, cash quality, growth, and leverage metrics.

## Important Financial Ratio Columns

The `financial_ratios` table includes metrics such as:

- `net_profit_margin_pct`
- `operating_profit_margin_pct`
- `return_on_equity_pct`
- `return_on_capital_employed_pct`
- `debt_to_equity`
- `interest_coverage`
- `asset_turnover`
- `free_cash_flow_cr`
- `earnings_per_share`
- `book_value_per_share`
- `dividend_payout_ratio_pct`
- `total_debt_cr`
- `cash_from_operations_cr`
- `revenue_cagr_5yr`
- `pat_cagr_5yr`
- `eps_cagr_5yr`
- `composite_quality_score`

## Outputs

```text
output/capital_allocation.csv
output/ratio_edge_cases.log
```

## Validation Summary

- Formula edge cases handled
- Financial-sector leverage exceptions handled
- Duplicate company-year records reviewed during integration QA
- 71 unit tests passed

---

# Sprint 3 - Screener & Peer Comparison Engine

Sprint 3 introduced financial screening and peer-relative company analysis.

## Financial Screener

The screener supports filters across metrics such as:

- ROE
- Debt-to-Equity
- Free Cash Flow
- Revenue CAGR
- PAT CAGR
- Operating Profit Margin
- P/E
- P/B
- Dividend Yield
- Interest Coverage Ratio
- Market Capitalisation
- Net Profit
- EPS CAGR
- Asset Turnover
- Revenue

## Screener Presets

Available presets include:

- Quality Compounder
- Value Pick
- Growth Accelerator
- Dividend Champion
- Debt-Free Blue Chip
- Turnaround Watch

## Peer Comparison Engine

Peer percentile rankings are computed using:

- ROE
- ROCE
- Net Profit Margin
- Debt-to-Equity
- Free Cash Flow
- PAT CAGR
- Revenue CAGR
- EPS CAGR
- Interest Coverage
- Asset Turnover

For Debt-to-Equity, percentile logic is inverted so lower leverage receives a better rank.

## Major Outputs

```text
output/screener_output.xlsx
output/peer_comparison.xlsx
reports/radar_charts/
```

Peer rankings are stored in the `peer_percentiles` table.

---

# Sprint 4 - Streamlit Dashboard & Valuation

Sprint 4 delivered an interactive 8-screen Streamlit dashboard and a sector-relative valuation module.

## Run the Dashboard

```bash
streamlit run src/dashboard/app.py
```

The application opens locally at:

```text
http://localhost:8501
```

## Dashboard Screens

### 1. Home

Features:

- Average ROE
- Median P/E
- Median Debt-to-Equity
- Total Companies
- Median 5-Year Revenue CAGR
- Debt-Free Companies count
- Sector breakdown donut chart
- Top 5 companies by Composite Quality Score
- Financial year selector

### 2. Company Profile

Features:

- Search by company name or ticker
- Company name and ticker
- Sector and sub-sector
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

Missing values are displayed as `N/A`.

### 3. Financial Screener

Features:

- Live financial filters
- Six preset screeners
- Result count
- Composite Quality Score
- Dynamic results table
- CSV export

### 4. Peer Comparison

Features:

- Peer group selection
- Company selection
- Radar chart
- Eight financial metrics
- Company versus peer-group average
- KPI comparison table
- Benchmark company highlighting

### 5. Trend Analysis

Features:

- Company search
- Multi-metric selection
- Maximum three metrics per chart
- Up to 10 years of historical data
- YoY percentage change annotations
- Partial-data handling

### 6. Sector Analysis

Features:

- Sector selection
- Revenue on X-axis
- ROE on Y-axis
- Market Capitalisation as bubble size
- Sub-sector as bubble category
- Company hover information
- Sector median KPI chart

### 7. Capital Allocation Map

The screen classifies companies using the signs of:

- Operating Cash Flow
- Investing Cash Flow
- Financing Cash Flow

Features:

- Treemap covering the company universe
- Capital allocation pattern grouping
- Pattern selector
- Company list by selected pattern

### 8. Annual Reports

Features:

- Company search
- Available report years
- Clickable annual report links
- Missing report handling
- Unavailable report status

---

## Valuation Module

Location:

```text
src/analytics/valuation.py
```

Run using:

```bash
python -m src.analytics.valuation
```

### Valuation Metrics

- P/E
- P/B
- EV/EBITDA
- Free Cash Flow Yield
- 5-Year Median P/E
- Sector Median P/E comparison
- P/E deviation from sector median

FCF Yield:

```text
FCF Yield = Free Cash Flow / Market Capitalisation × 100
```

### Valuation Flags

**Caution**

```text
P/E > Sector Median P/E × 1.5
```

**Discount**

```text
P/E < Sector Median P/E × 0.7
```

**Fair**

Companies falling between the Discount and Caution thresholds.

### Valuation Outputs

```text
output/valuation_summary.xlsx
output/valuation_flags.csv
```

Final valuation output:

- 92 companies
- 48 Fair
- 30 Discount
- 14 Caution

---

## Sprint 4 Integration QA

- All 8 Streamlit screens load successfully
- Dashboard tested across multiple sectors and tickers
- Partial-data companies do not crash the application
- Missing metrics display as `N/A`
- Screener works with extreme filter values
- Empty screener results are handled safely
- CSV download works correctly
- Charts fit within the page width
- Company Profile load time tested below 3 seconds
- Valuation output contains 92 companies

---

# Sprint 5 - Intelligence, NLP & PDF Reports

Sprint 5 added automated financial intelligence, NLP processing, cash-flow analysis, capital allocation reporting, and PDF report generation.

## Day 29 - NLP Analysis Parser

Location:

```text
src/nlp/parser.py
```

Run using:

```bash
python -m src.nlp.parser
```

The parser extracts structured values from:

- `compounded_sales_growth`
- `compounded_profit_growth`
- `stock_price_cagr`
- `roe`

Supported formats include:

```text
10 Years: 21%
5 Years 14%
1 Year: -2%
Last Year: 12%
TTM: -3%
```

### Final Results

- Analysis source rows: 20
- Parsed metric records: 80
- Parse failures: 0
- CAGR comparisons: 10
- Divergences above 5 percentage points: 0

### Outputs

```text
output/analysis_parsed.csv
output/parse_failures.csv
output/cagr_cross_validation.csv
```

---

## Day 30 - Automated Pros and Cons Generator

Location:

```text
src/nlp/pros_cons_generator.py
```

Run using:

```bash
python -m src.nlp.pros_cons_generator
```

The module uses:

- 12 Pro Rules
- 12 Con Rules
- Confidence scoring
- Financial-sector exceptions
- Missing-data handling

### Final Results

- Companies processed: 92
- Total generated records: 550
- Pros generated: 405
- Cons generated: 145
- Strict rule signals: 506
- Coverage fallback signals: 44
- Companies missing a pro: 0
- Companies missing a con: 0

### Output

```text
output/pros_cons_generated.csv
```

---

## Day 31 - Cash Flow Intelligence

Location:

```text
src/analytics/cashflow_kpis.py
```

Run using:

```bash
python -m src.analytics.cashflow_kpis
```

The module calculates:

- CFO Quality Score
- CFO Quality Label
- CapEx Intensity
- CapEx Classification
- 5-Year FCF CAGR
- FCF Conversion Rate
- Distress Signal
- Deleveraging Flag
- Capital Allocation Pattern

### Final Results

- Companies processed: 92
- Distress alerts: 13
- Deleveraging companies: 25
- Missing cash-flow cases: 1

### Outputs

```text
output/cashflow_intelligence.xlsx
output/distress_alerts.csv
```

---

## Day 32 - Capital Allocation Analysis

Location:

```text
src/analytics/capital_allocation_report.py
```

Run using:

```bash
python -m src.analytics.capital_allocation_report
```

The module:

- Normalises ticker values
- Normalises financial years
- Removes duplicate records
- Resolves conflicting company-year records
- Validates the canonical company universe
- Generates latest-year pattern distribution
- Tracks year-over-year capital allocation changes
- Updates Cash Flow Intelligence output

### Final Results

- Raw source rows: 1,187
- Clean capital rows: 1,063
- Canonical company coverage: 92/92
- Missing canonical companies: 0
- Latest pattern companies: 92
- Pattern changes identified: 530
- Cash Flow Intelligence rows: 92

### Outputs

```text
output/capital_allocation.csv
output/capital_allocation_distribution.csv
output/pattern_changes.csv
output/capital_allocation_audit.csv
output/capital_allocation_raw_backup.csv
```

---

## Day 33 - Company Tearsheet Reports

Location:

```text
src/reports/tearsheet.py
```

Run using:

```bash
python -m src.reports.tearsheet
```

The template was tested using:

- TCS
- HDFCBANK
- RELIANCE
- SUNPHARMA
- TATASTEEL

### Page 1

- Company header
- Six KPI tiles
- Revenue historical chart
- Net Profit historical chart
- ROE trend
- ROCE trend

### Page 2

- Balance Sheet composition
- Cash Flow waterfall
- Automated Pros
- Automated Cons
- Capital Allocation badge

### Sample Test Results

- Requested tickers: 5
- Generated PDFs: 5
- Failures: 0

Generated location:

```text
reports/tearsheets/
```

---

## Day 34 - Batch Tearsheets & Sector Reports

Location:

```text
src/reports/sector_report.py
```

Run using:

```bash
python -m src.reports.sector_report
```

### Company Tearsheet Results

- Canonical companies: 92
- Eligible tearsheets: 91
- Generated tearsheets: 91
- Skipped companies: 1
- PDFs below 30 KB: 0
- Tearsheet failures: 0

### Skipped Company

```text
JIOFIN
```

Reason:

```text
Fewer than 3 years of Profit & Loss data
```

### Sector Report Results

- Raw broad sectors: 10
- Reporting sectors: 11
- Generated sector PDFs: 11
- Sector report failures: 0

### Outputs

```text
reports/tearsheets/
reports/sector/

output/skipped_tearsheets.csv
output/tearsheet_batch_audit.csv
output/sector_report_audit.csv
```

---

## Day 35 - Portfolio Summary PDF

Location:

```text
src/reports/portfolio_summary.py
```

Run using:

```bash
python -m src.reports.portfolio_summary
```

Each company page includes:

- Company name
- Ticker
- Sector
- Six major financial KPIs
- Latest-year values
- Previous-year values
- Trend indicators

### Final Results

- Canonical companies: 92
- Expected pages: 92
- Generated portfolio pages: 92
- Output size: approximately 0.31 MB

### Output

```text
reports/portfolio/portfolio_summary.pdf
```

---

# Sprint 5 Final Integration QA

## Pros and Cons Coverage

```text
Companies: 92
Missing Pro: 0
Missing Con: 0
```

## Cash Flow Intelligence Validation

```text
Rows: 92
Unique companies: 92
```

Required columns:

- `company_id`
- `sector`
- `cfo_quality_score`
- `cfo_quality_label`
- `capex_intensity_pct`
- `capex_label`
- `fcf_cagr_5yr`
- `fcf_conversion_pct`
- `distress_flag`
- `deleveraging_flag`
- `capital_allocation_label`

## PDF Validation

```text
Company tearsheets generated : 91
Documented skips              : 1
Sector reports                : 11
Portfolio summary pages       : 92
```

Additional validation:

- No batch tearsheet generation failures
- No sector report generation failures
- No generated tearsheet below 30 KB
- Skipped company documented
- 92-company Pros/Cons coverage achieved
- 92-company Cash Flow Intelligence coverage achieved

---

# Data Quality & Edge Cases

## Duplicate Records

Duplicate company-year records were identified in:

- `financial_ratios`
- `cashflow`
- `profitandloss`
- `balancesheet`
- `capital_allocation.csv`

Exact duplicate records were reviewed and cleaned where required.

## Partial Historical Data

Examples include:

- JIOFIN
- LICI
- ADANIGREEN
- HAL
- IRFC
- LODHA

JIOFIN currently has fewer than three years of Profit & Loss history and is therefore skipped during batch tearsheet generation.

## Missing Financial Data

The application handles partial or missing records using:

- `N/A` values
- Missing-data messages
- Safe report fallbacks
- Canonical company-universe joins

---

# Performance Findings

Streamlit database query functions use:

```python
@st.cache_data(ttl=600)
```

This reduces repeated SQLite queries and improves dashboard responsiveness.

Company Profile performance remained below the Sprint requirement of 3 seconds during testing.

---

# Project Structure

```text
nifty100-project/
│
├── nifty100.db
├── README.md
│
├── output/
│   ├── analysis_parsed.csv
│   ├── parse_failures.csv
│   ├── cagr_cross_validation.csv
│   ├── pros_cons_generated.csv
│   ├── cashflow_intelligence.xlsx
│   ├── distress_alerts.csv
│   ├── capital_allocation.csv
│   ├── capital_allocation_distribution.csv
│   ├── capital_allocation_audit.csv
│   ├── capital_allocation_raw_backup.csv
│   ├── pattern_changes.csv
│   ├── skipped_tearsheets.csv
│   ├── tearsheet_batch_audit.csv
│   ├── sector_report_audit.csv
│   ├── valuation_summary.xlsx
│   └── valuation_flags.csv
│
├── reports/
│   ├── radar_charts/
│   ├── tearsheets/
│   ├── sector/
│   └── portfolio/
│       └── portfolio_summary.pdf
│
└── src/
    ├── analytics/
    │   ├── valuation.py
    │   ├── cashflow_kpis.py
    │   └── capital_allocation_report.py
    │
    ├── nlp/
    │   ├── __init__.py
    │   ├── parser.py
    │   └── pros_cons_generator.py
    │
    ├── reports/
    │   ├── __init__.py
    │   ├── tearsheet.py
    │   ├── sector_report.py
    │   └── portfolio_summary.py
    │
    └── dashboard/
        ├── app.py
        ├── pages/
        │   ├── 01_home.py
        │   ├── 02_profile.py
        │   ├── 03_screener.py
        │   ├── 04_peers.py
        │   ├── 05_trends.py
        │   ├── 06_sectors.py
        │   ├── 07_capital.py
        │   └── 08_reports.py
        └── utils/
            └── db.py
```

---

# Main Run Commands

## Dashboard

```bash
streamlit run src/dashboard/app.py
```

## Valuation Module

```bash
python -m src.analytics.valuation
```

## NLP Parser

```bash
python -m src.nlp.parser
```

## Pros and Cons Generator

```bash
python -m src.nlp.pros_cons_generator
```

## Cash Flow Intelligence

```bash
python -m src.analytics.cashflow_kpis
```

## Capital Allocation Report

```bash
python -m src.analytics.capital_allocation_report
```

## Sample Company Tearsheets

```bash
python -m src.reports.tearsheet
```

## Batch Tearsheets and Sector Reports

```bash
python -m src.reports.sector_report
```

## Portfolio Summary

```bash
python -m src.reports.portfolio_summary
```

---

# Sprint Completion Status

## Sprint 1

- [x] Data Foundation
- [x] ETL Pipeline
- [x] SQLite Database
- [x] Data Quality Validation

## Sprint 2

- [x] Financial Ratio Engine
- [x] CAGR Engine
- [x] Cash Flow KPIs
- [x] Composite Quality Score

## Sprint 3

- [x] Financial Screener
- [x] Screener Presets
- [x] Peer Comparison
- [x] Peer Percentile Rankings

## Sprint 4

- [x] 8-Screen Streamlit Dashboard
- [x] Valuation Module
- [x] Screener CSV Export
- [x] Integration QA

## Sprint 5

- [x] NLP Analysis Parser
- [x] CAGR Cross-Validation
- [x] Automated Pros and Cons
- [x] Cash Flow Intelligence
- [x] Distress Signal Detection
- [x] Deleveraging Detection
- [x] Capital Allocation Intelligence
- [x] Capital Allocation Data Cleaning
- [x] Pattern Change Tracking
- [x] Company Tearsheet Reports
- [x] Batch Tearsheet Generation
- [x] 11 Sector PDF Reports
- [x] Portfolio Summary Report
- [x] Final Integration QA

---

# Final Status

Sprint 1 through Sprint 5 development is complete.

The project currently provides:

- A validated SQLite financial database
- Automated financial ratio calculations
- Financial screening
- Peer comparison
- Interactive Streamlit analytics
- Sector-relative valuation
- NLP-based financial signal generation
- Cash-flow intelligence
- Capital allocation analysis
- Automated company tearsheets
- Sector-level PDF reports
- A complete 92-company portfolio summary

Start the dashboard using:

```bash
streamlit run src/dashboard/app.py
```
