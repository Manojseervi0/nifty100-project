# Nifty100 Project

## Sprint 1 - Data Foundation

### Completed
- Environment Setup
- SQLite Database Creation
- ETL Pipeline
- Data Loading
- Data Quality Validation
- 35+ Unit Tests

### Database Tables
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
- stock_prices
- market_cap

### Outputs
- nifty100.db
- load_audit.csv
- validation_failures.csv
- exploratory_queries.sql

## Sprint 2 - Financial Ratio Engine

### Completed
- Profitability Ratios (NPM, OPM, ROE, ROCE, ROA)
- Leverage & Efficiency Ratios
- CAGR Engine (Revenue, PAT, EPS)
- CAGR Edge Case Handling
- Cash Flow KPI Engine
- Composite Quality Score
- ROCE Population
- PAT CAGR Population
- EPS CAGR Population
- Capital Allocation Classification
- Edge Case Logging
- Financial Ratio Validation
- 71 Unit Tests Passed

### Database Updates
- Added revenue_cagr_5yr
- Added pat_cagr_5yr
- Added eps_cagr_5yr
- Added pat_cagr_5yr_flag
- Added eps_cagr_5yr_flag
- Added return_on_capital_employed_pct
- Added composite_quality_score

### Outputs
- capital_allocation.csv
- ratio_edge_cases.log

### Validation Summary
- financial_ratios table contains 1184 rows
- 71/71 tests passed
- Duplicate company-year combinations identified and documented