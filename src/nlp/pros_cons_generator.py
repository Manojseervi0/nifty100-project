from __future__ import annotations

import argparse
import math
import re
import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "nifty100.db"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"

FINANCIALS_SECTOR = "Financials"
MIN_CONFIDENCE = 60.0


def extract_year(value: object) -> int | None:
    """Extract a 4-digit year from values such as 'Mar 2024' or 2024."""
    if value is None or pd.isna(value):
        return None

    matches = re.findall(r"(?:19|20)\d{2}", str(value))
    return int(matches[-1]) if matches else None


def safe_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    return number if math.isfinite(number) else None


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def load_table(conn: sqlite3.Connection, table_name: str) -> pd.DataFrame:
    return pd.read_sql_query(f"SELECT * FROM {table_name}", conn)


def prepare_history(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add numeric year, drop rows without a usable year, and keep one
    company-year row. This prevents duplicate records from affecting trends.
    """
    if df.empty:
        return df.copy()

    result = df.copy()
    result["year_num"] = result["year"].map(extract_year)
    result = result[result["year_num"].notna()].copy()
    result["year_num"] = result["year_num"].astype(int)

    sort_columns = ["company_id", "year_num"]
    if "id" in result.columns:
        sort_columns.append("id")

    result = result.sort_values(sort_columns)
    result = result.drop_duplicates(
        subset=["company_id", "year_num"],
        keep="last",
    )

    return result.reset_index(drop=True)


def latest_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    return (
        df.sort_values(["company_id", "year_num"])
        .groupby("company_id", as_index=False)
        .tail(1)
        .set_index("company_id")
    )


def company_history(
    df: pd.DataFrame,
    company_id: str,
    columns: Iterable[str],
) -> pd.DataFrame:
    available_columns = ["year_num", *columns]

    return (
        df.loc[df["company_id"] == company_id, available_columns]
        .sort_values("year_num")
        .reset_index(drop=True)
    )


def latest_numeric_series(
    history: pd.DataFrame,
    column: str,
    count: int,
) -> list[float]:
    if history.empty or column not in history.columns:
        return []

    values = pd.to_numeric(history[column], errors="coerce").dropna()
    return values.astype(float).tail(count).tolist()


def count_trailing_positive(values: list[float]) -> int:
    count = 0
    for value in reversed(values):
        if value > 0:
            count += 1
        else:
            break
    return count


def add_signal(
    rows: list[dict],
    company_id: str,
    signal_type: str,
    rule_id: str,
    text: str,
    confidence: float,
) -> None:
    confidence = round(clamp(confidence), 1)

    if confidence <= MIN_CONFIDENCE:
        return

    rows.append(
        {
            "company_id": company_id,
            "type": signal_type,
            "rule_id": rule_id,
            "text": text,
            "confidence_pct": confidence,
        }
    )


def get_row(df: pd.DataFrame, company_id: str) -> pd.Series | None:
    if df.empty or company_id not in df.index:
        return None

    row = df.loc[company_id]

    if isinstance(row, pd.DataFrame):
        return row.iloc[-1]

    return row


def fmt(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def generate_company_signals(
    company_id: str,
    sector: str,
    ratios_hist: pd.DataFrame,
    pl_hist: pd.DataFrame,
    bs_hist: pd.DataFrame,
    latest_ratio: pd.Series | None,
    latest_pl: pd.Series | None,
    latest_bs: pd.Series | None,
    latest_market: pd.Series | None,
) -> list[dict]:

    rows: list[dict] = []

    ratio_history = company_history(
        ratios_hist,
        company_id,
        [
            "return_on_equity_pct",
            "operating_profit_margin_pct",
            "debt_to_equity",
            "interest_coverage",
            "free_cash_flow_cr",
            "earnings_per_share",
        ],
    )

    profit_history = company_history(
        pl_hist,
        company_id,
        ["sales", "net_profit", "eps"],
    )

    balance_history = company_history(
        bs_hist,
        company_id,
        ["total_assets", "borrowings", "investments"],
    )

    roe_values = latest_numeric_series(
        ratio_history,
        "return_on_equity_pct",
        10,
    )
    fcf_values = latest_numeric_series(
        ratio_history,
        "free_cash_flow_cr",
        10,
    )
    opm_values = latest_numeric_series(
        ratio_history,
        "operating_profit_margin_pct",
        10,
    )
    de_values = latest_numeric_series(
        ratio_history,
        "debt_to_equity",
        10,
    )
    eps_values = latest_numeric_series(
        ratio_history,
        "earnings_per_share",
        10,
    )
    sales_values = latest_numeric_series(
        profit_history,
        "sales",
        10,
    )

    latest_de = (
        safe_float(latest_ratio.get("debt_to_equity"))
        if latest_ratio is not None
        else None
    )
    latest_fcf = (
        safe_float(latest_ratio.get("free_cash_flow_cr"))
        if latest_ratio is not None
        else None
    )
    latest_icr = (
        safe_float(latest_ratio.get("interest_coverage"))
        if latest_ratio is not None
        else None
    )
    latest_roe = (
        safe_float(latest_ratio.get("return_on_equity_pct"))
        if latest_ratio is not None
        else None
    )
    latest_roce = (
        safe_float(latest_ratio.get("return_on_capital_employed_pct"))
        if latest_ratio is not None
        else None
    )
    latest_opm = (
        safe_float(latest_ratio.get("operating_profit_margin_pct"))
        if latest_ratio is not None
        else None
    )
    revenue_cagr = (
        safe_float(latest_ratio.get("revenue_cagr_5yr"))
        if latest_ratio is not None
        else None
    )
    pat_cagr = (
        safe_float(latest_ratio.get("pat_cagr_5yr"))
        if latest_ratio is not None
        else None
    )
    eps_cagr = (
        safe_float(latest_ratio.get("eps_cagr_5yr"))
        if latest_ratio is not None
        else None
    )
    dividend_payout = (
        safe_float(latest_ratio.get("dividend_payout_ratio_pct"))
        if latest_ratio is not None
        else None
    )

    latest_net_profit = (
        safe_float(latest_pl.get("net_profit"))
        if latest_pl is not None
        else None
    )

    dividend_yield = (
        safe_float(latest_market.get("dividend_yield_pct"))
        if latest_market is not None
        else None
    )

    # -------------------------
    # PRO RULES 1 TO 12
    # -------------------------

    # PRO-01: ROE > 20% sustained for 3+ years
    if len(roe_values) >= 3 and all(value > 20 for value in roe_values[-3:]):
        average_roe = sum(roe_values[-3:]) / 3
        confidence = 72 + min(28, max(0, average_roe - 20) * 1.4)

        add_signal(
            rows,
            company_id,
            "pro",
            "PRO-01",
            (
                "Consistently high return on equity above 20% "
                "demonstrates exceptional capital efficiency"
            ),
            confidence,
        )

    # PRO-02: FCF positive for 5+ consecutive years
    positive_fcf_years = count_trailing_positive(fcf_values)
    if positive_fcf_years >= 5:
        confidence = 78 + min(22, (positive_fcf_years - 5) * 4)

        add_signal(
            rows,
            company_id,
            "pro",
            "PRO-02",
            (
                "Strong free cash flow generation over 5 years signals "
                "healthy business fundamentals"
            ),
            confidence,
        )

    # PRO-03: D/E = 0 in latest year
    if latest_de is not None and abs(latest_de) <= 0.01:
        add_signal(
            rows,
            company_id,
            "pro",
            "PRO-03",
            (
                "Debt-free balance sheet provides financial flexibility "
                "and eliminates interest burden"
            ),
            96,
        )

    # PRO-04: Revenue CAGR > 15% over 5 years
    if revenue_cagr is not None and revenue_cagr > 15:
        confidence = 68 + min(32, (revenue_cagr - 15) * 1.6)

        add_signal(
            rows,
            company_id,
            "pro",
            "PRO-04",
            (
                "Revenue growing at above 15% CAGR over 5 years reflects "
                "strong business momentum"
            ),
            confidence,
        )

    # PRO-05: OPM > 25% in latest year
    if latest_opm is not None and latest_opm > 25:
        confidence = 68 + min(32, (latest_opm - 25) * 1.3)

        add_signal(
            rows,
            company_id,
            "pro",
            "PRO-05",
            (
                "Operating profit margin above 25% indicates strong "
                "pricing power and cost discipline"
            ),
            confidence,
        )

    # PRO-06: PAT CAGR > 20% over 5 years
    if pat_cagr is not None and pat_cagr > 20:
        confidence = 68 + min(32, (pat_cagr - 20) * 1.4)

        add_signal(
            rows,
            company_id,
            "pro",
            "PRO-06",
            (
                "Net profit compounding at above 20% over 5 years creates "
                "significant shareholder value"
            ),
            confidence,
        )

    # PRO-07: ICR > 10 or Debt Free
    debt_free = latest_de is not None and abs(latest_de) <= 0.01

    if debt_free or (latest_icr is not None and latest_icr > 10):
        confidence = (
            95
            if debt_free
            else 70 + min(30, max(0, latest_icr - 10) * 1.2)
        )

        add_signal(
            rows,
            company_id,
            "pro",
            "PRO-07",
            (
                "Very high interest coverage ratio reflects negligible "
                "financial stress from debt servicing"
            ),
            confidence,
        )

    # PRO-08: Dividend Yield > 2% with positive FCF
    if (
        dividend_yield is not None
        and dividend_yield > 2
        and latest_fcf is not None
        and latest_fcf > 0
    ):
        confidence = 68 + min(32, (dividend_yield - 2) * 8)

        add_signal(
            rows,
            company_id,
            "pro",
            "PRO-08",
            (
                "Consistent dividend yield above 2% backed by positive "
                "free cash flow"
            ),
            confidence,
        )

    # PRO-09: EPS CAGR > 15% over 5 years
    if eps_cagr is not None and eps_cagr > 15:
        confidence = 68 + min(32, (eps_cagr - 15) * 1.5)

        add_signal(
            rows,
            company_id,
            "pro",
            "PRO-09",
            (
                "Earnings per share growing above 15% CAGR indicates "
                "strong earnings quality and compounding"
            ),
            confidence,
        )

    # PRO-10: ROE improving for 3 consecutive observations
    if (
        len(roe_values) >= 3
        and roe_values[-3] < roe_values[-2] < roe_values[-1]
    ):
        improvement = roe_values[-1] - roe_values[-3]
        confidence = 70 + min(30, max(0, improvement) * 2)

        add_signal(
            rows,
            company_id,
            "pro",
            "PRO-10",
            (
                "Return on equity improving for 3 consecutive years shows "
                "strengthening business quality"
            ),
            confidence,
        )

    # PRO-11:
    # Sprint text says "Revenue CAGR > PAT CAGR" but the supplied wording
    # says revenue is growing slower than profits. Operating leverage is
    # therefore implemented as PAT CAGR > Revenue CAGR.
    if (
        revenue_cagr is not None
        and pat_cagr is not None
        and pat_cagr > revenue_cagr
        and pat_cagr > 0
    ):
        gap = pat_cagr - revenue_cagr
        confidence = 66 + min(34, max(0, gap) * 1.7)

        add_signal(
            rows,
            company_id,
            "pro",
            "PRO-11",
            (
                "Revenue growing slower than profits shows improving "
                "operating leverage and scale benefits"
            ),
            confidence,
        )

    # PRO-12: Assets growing while debt declines
    valid_balance = balance_history.dropna(
        subset=["total_assets", "borrowings"]
    )

    if len(valid_balance) >= 2:
        previous_bs = valid_balance.iloc[-2]
        current_bs = valid_balance.iloc[-1]

        previous_assets = safe_float(previous_bs["total_assets"])
        current_assets = safe_float(current_bs["total_assets"])
        previous_debt = safe_float(previous_bs["borrowings"])
        current_debt = safe_float(current_bs["borrowings"])

        if (
            previous_assets is not None
            and current_assets is not None
            and previous_debt is not None
            and current_debt is not None
            and current_assets > previous_assets
            and current_debt < previous_debt
        ):
            asset_growth = (
                ((current_assets - previous_assets) / abs(previous_assets)) * 100
                if previous_assets != 0
                else 0
            )
            debt_decline = (
                ((previous_debt - current_debt) / abs(previous_debt)) * 100
                if previous_debt != 0
                else 0
            )

            confidence = 70 + min(
                30,
                max(0, asset_growth) * 0.6
                + max(0, debt_decline) * 0.4,
            )

            add_signal(
                rows,
                company_id,
                "pro",
                "PRO-12",
                (
                    "Growing asset base funded with declining debt reflects "
                    "increasingly self-sustaining growth"
                ),
                confidence,
            )

    # -------------------------
    # CON RULES 1 TO 12
    # -------------------------

    # CON-01: D/E > 2 for non-financial companies
    if (
        latest_de is not None
        and latest_de > 2
        and str(sector).strip().lower() != FINANCIALS_SECTOR.lower()
    ):
        confidence = 70 + min(30, (latest_de - 2) * 10)

        add_signal(
            rows,
            company_id,
            "con",
            "CON-01",
            (
                f"Debt-to-equity ratio of {latest_de:.2f} is elevated for "
                "a non-financial company and warrants monitoring"
            ),
            confidence,
        )

    # CON-02: FCF negative for 3 consecutive years
    if len(fcf_values) >= 3 and all(value < 0 for value in fcf_values[-3:]):
        magnitude = abs(sum(fcf_values[-3:]) / 3)
        confidence = 78 + min(22, math.log10(magnitude + 1) * 5)

        add_signal(
            rows,
            company_id,
            "con",
            "CON-02",
            (
                "Free cash flow negative for 3 consecutive years raises "
                "concern about cash generation quality"
            ),
            confidence,
        )

    # CON-03: OPM declining for 3 consecutive observations
    if (
        len(opm_values) >= 3
        and opm_values[-3] > opm_values[-2] > opm_values[-1]
    ):
        decline = opm_values[-3] - opm_values[-1]
        confidence = 68 + min(32, max(0, decline) * 3)

        add_signal(
            rows,
            company_id,
            "con",
            "CON-03",
            (
                "Operating margins declining for 3 consecutive years "
                "suggest pricing or cost pressure"
            ),
            confidence,
        )

    # CON-04: Net profit negative in latest year
    if latest_net_profit is not None and latest_net_profit < 0:
        confidence = 90 + min(
            10,
            math.log10(abs(latest_net_profit) + 1) * 2,
        )

        add_signal(
            rows,
            company_id,
            "con",
            "CON-04",
            "Company reported a net loss in the most recent financial year",
            confidence,
        )

    # CON-05: Revenue declining for 2+ consecutive years
    if (
        len(sales_values) >= 3
        and sales_values[-3] > sales_values[-2] > sales_values[-1]
    ):
        decline_pct = (
            ((sales_values[-3] - sales_values[-1]) / abs(sales_values[-3])) * 100
            if sales_values[-3] != 0
            else 0
        )

        confidence = 72 + min(28, max(0, decline_pct) * 1.5)

        add_signal(
            rows,
            company_id,
            "con",
            "CON-05",
            (
                "Revenue contraction over 2 consecutive years indicates "
                "demand weakness or market share loss"
            ),
            confidence,
        )

    # CON-06: ICR < 1.5
    if latest_icr is not None and latest_icr < 1.5:
        confidence = 75 + min(25, max(0, 1.5 - latest_icr) * 15)

        add_signal(
            rows,
            company_id,
            "con",
            "CON-06",
            (
                "Interest coverage ratio below 1.5x indicates the company "
                "is at risk of not meeting its debt obligations"
            ),
            confidence,
        )

    # CON-07: Dividend payout > 100%
    if dividend_payout is not None and dividend_payout > 100:
        confidence = 75 + min(25, (dividend_payout - 100) * 0.3)

        add_signal(
            rows,
            company_id,
            "con",
            "CON-07",
            (
                "Dividend payout ratio above 100% means the company is "
                "paying dividends beyond current earnings, which may be "
                "unsustainable"
            ),
            confidence,
        )

    # CON-08: D/E rising for 3 consecutive observations
    if (
        len(de_values) >= 3
        and de_values[-3] < de_values[-2] < de_values[-1]
    ):
        increase = de_values[-1] - de_values[-3]
        confidence = 68 + min(32, max(0, increase) * 18)

        add_signal(
            rows,
            company_id,
            "con",
            "CON-08",
            (
                "Rising debt-to-equity ratio over 3 years suggests "
                "increasing financial leverage risk"
            ),
            confidence,
        )

    # CON-09: EPS declining for 3 consecutive observations
    if (
        len(eps_values) >= 3
        and eps_values[-3] > eps_values[-2] > eps_values[-1]
    ):
        decline = eps_values[-3] - eps_values[-1]
        confidence = 68 + min(32, max(0, decline) * 2)

        add_signal(
            rows,
            company_id,
            "con",
            "CON-09",
            (
                "Earnings per share declining for 3 consecutive years "
                "reflects deteriorating profitability"
            ),
            confidence,
        )

    # CON-10: ROCE < 10%
    if latest_roce is not None and latest_roce < 10:
        confidence = 72 + min(28, max(0, 10 - latest_roce) * 3)

        add_signal(
            rows,
            company_id,
            "con",
            "CON-10",
            (
                "Return on capital employed below 10% suggests the "
                "business is not generating sufficient returns on "
                "invested capital"
            ),
            confidence,
        )

    # CON-11: Net Debt > 3x EBITDA
    # EBITDA is derived from Enterprise Value / EV-EBITDA because the
    # source database does not contain a direct EBITDA column.
    if latest_bs is not None and latest_market is not None:
        borrowings = safe_float(latest_bs.get("borrowings"))
        investments = safe_float(latest_bs.get("investments"))
        enterprise_value = safe_float(
            latest_market.get("enterprise_value_crore")
        )
        ev_ebitda = safe_float(latest_market.get("ev_ebitda"))

        if (
            borrowings is not None
            and investments is not None
            and enterprise_value is not None
            and ev_ebitda is not None
            and ev_ebitda != 0
        ):
            net_debt = borrowings - investments
            ebitda = enterprise_value / ev_ebitda

            if ebitda > 0:
                net_debt_to_ebitda = net_debt / ebitda

                if net_debt_to_ebitda > 3:
                    confidence = 75 + min(
                        25,
                        (net_debt_to_ebitda - 3) * 7,
                    )

                    add_signal(
                        rows,
                        company_id,
                        "con",
                        "CON-11",
                        (
                            "Net debt exceeding 3 times EBITDA is a high "
                            "leverage ratio and limits financial flexibility"
                        ),
                        confidence,
                    )

    # CON-12: Revenue CAGR < 5% over 5 years
    if revenue_cagr is not None and revenue_cagr < 5:
        confidence = 70 + min(30, max(0, 5 - revenue_cagr) * 3)

        add_signal(
            rows,
            company_id,
            "con",
            "CON-12",
            (
                "Revenue growing at below 5% over 5 years lags normal "
                "growth expectations and suggests limited business momentum"
            ),
            confidence,
        )

    # ---------------------------------------------------------
    # COVERAGE FALLBACKS
    # ---------------------------------------------------------
    # The fixed 12+12 rules can legitimately leave strong companies with
    # no con, or sparse-data companies with no pro. The sprint exit criterion
    # nevertheless requires at least one of each for all 92 companies.
    # These fallbacks are explicitly labelled and never pretend that a fixed
    # threshold rule was breached.

    has_pro = any(row["type"] == "pro" for row in rows)
    has_con = any(row["type"] == "con" for row in rows)

    if not has_pro:
        candidate_metrics = [
            ("ROE", latest_roe, "%"),
            ("ROCE", latest_roce, "%"),
            ("Operating margin", latest_opm, "%"),
            ("Revenue CAGR", revenue_cagr, "%"),
            ("PAT CAGR", pat_cagr, "%"),
            ("Free cash flow", latest_fcf, " Cr"),
        ]
        available = [
            item for item in candidate_metrics if item[1] is not None
        ]

        if available:
            metric_name, metric_value, suffix = max(
                available,
                key=lambda item: item[1],
            )
            text = (
                f"No high-conviction pro rule was triggered; the strongest "
                f"available financial signal is {metric_name} at "
                f"{fmt(metric_value)}{suffix}"
            )
        else:
            text = (
                "Limited comparable financial data is available; no major "
                "positive threshold was triggered, but the company remains "
                "covered for further review"
            )

        add_signal(
            rows,
            company_id,
            "pro",
            "PRO-FALLBACK",
            text,
            61,
        )

    if not has_con:
        watch_candidates: list[tuple[str, float, str]] = []

        if latest_roe is not None:
            watch_candidates.append(
                (
                    "ROE",
                    abs(latest_roe - 20),
                    f"ROE is {fmt(latest_roe)}%",
                )
            )

        if latest_roce is not None:
            watch_candidates.append(
                (
                    "ROCE",
                    abs(latest_roce - 10),
                    f"ROCE is {fmt(latest_roce)}%",
                )
            )

        if revenue_cagr is not None:
            watch_candidates.append(
                (
                    "Revenue growth",
                    abs(revenue_cagr - 5),
                    f"5-year revenue CAGR is {fmt(revenue_cagr)}%",
                )
            )

        if latest_de is not None:
            watch_candidates.append(
                (
                    "Leverage",
                    abs(2 - latest_de),
                    f"debt-to-equity is {fmt(latest_de, 2)}",
                )
            )

        if watch_candidates:
            # Pick the metric closest to a monitored risk threshold.
            _, _, detail = min(
                watch_candidates,
                key=lambda item: item[1],
            )

            text = (
                "No major con rule was triggered; as a monitoring watchpoint, "
                f"{detail} and should be tracked alongside future results"
            )
        else:
            text = (
                "No major con rule was triggered, but limited comparable "
                "financial data remains a monitoring risk until additional "
                "history becomes available"
            )

        add_signal(
            rows,
            company_id,
            "con",
            "CON-FALLBACK",
            text,
            61,
        )

    return rows


def run_generator(
    db_path: Path,
    output_dir: Path,
) -> pd.DataFrame:

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        companies = load_table(conn, "companies")
        sectors = load_table(conn, "sectors")
        ratios = prepare_history(load_table(conn, "financial_ratios"))
        profit_loss = prepare_history(load_table(conn, "profitandloss"))
        balance_sheet = prepare_history(load_table(conn, "balancesheet"))
        market_cap = prepare_history(load_table(conn, "market_cap"))

    master = companies[["id", "company_name"]].rename(
        columns={"id": "company_id"}
    )

    master = master.merge(
        sectors[["company_id", "broad_sector"]],
        on="company_id",
        how="left",
    )

    latest_ratio_df = latest_rows(ratios)
    latest_pl_df = latest_rows(profit_loss)
    latest_bs_df = latest_rows(balance_sheet)
    latest_market_df = latest_rows(market_cap)

    generated_rows: list[dict] = []

    for row in master.itertuples(index=False):
        generated_rows.extend(
            generate_company_signals(
                company_id=row.company_id,
                sector=row.broad_sector,
                ratios_hist=ratios,
                pl_hist=profit_loss,
                bs_hist=balance_sheet,
                latest_ratio=get_row(latest_ratio_df, row.company_id),
                latest_pl=get_row(latest_pl_df, row.company_id),
                latest_bs=get_row(latest_bs_df, row.company_id),
                latest_market=get_row(latest_market_df, row.company_id),
            )
        )

    output_df = pd.DataFrame(
        generated_rows,
        columns=[
            "company_id",
            "type",
            "rule_id",
            "text",
            "confidence_pct",
        ],
    )

    output_df = output_df.sort_values(
        ["company_id", "type", "confidence_pct"],
        ascending=[True, True, False],
    ).reset_index(drop=True)

    coverage = (
        output_df.groupby(["company_id", "type"])
        .size()
        .unstack(fill_value=0)
        .reindex(master["company_id"], fill_value=0)
    )

    missing_pro = coverage.index[
        coverage.get("pro", pd.Series(0, index=coverage.index)) < 1
    ].tolist()

    missing_con = coverage.index[
        coverage.get("con", pd.Series(0, index=coverage.index)) < 1
    ].tolist()

    if missing_pro or missing_con:
        raise RuntimeError(
            "Coverage validation failed. "
            f"Missing pros: {missing_pro}; missing cons: {missing_con}"
        )

    output_path = output_dir / "pros_cons_generated.csv"
    output_df.to_csv(output_path, index=False)

    strict_rows = output_df[
        ~output_df["rule_id"].isin(["PRO-FALLBACK", "CON-FALLBACK"])
    ]

    pro_count = int((output_df["type"] == "pro").sum())
    con_count = int((output_df["type"] == "con").sum())
    fallback_count = int(
        output_df["rule_id"].isin(["PRO-FALLBACK", "CON-FALLBACK"]).sum()
    )

    print("=" * 64)
    print("DAY 30 - AUTO PROS / CONS GENERATOR COMPLETE")
    print("=" * 64)
    print(f"Companies processed        : {master['company_id'].nunique()}")
    print(f"Generated records          : {len(output_df)}")
    print(f"Pros generated             : {pro_count}")
    print(f"Cons generated             : {con_count}")
    print(f"Strict rule signals        : {len(strict_rows)}")
    print(f"Coverage fallback signals  : {fallback_count}")
    print(f"Companies missing a pro    : {len(missing_pro)}")
    print(f"Companies missing a con    : {len(missing_con)}")
    print()
    print(f"Generated: {output_path}")

    return output_df


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate rule-based company pros and cons with confidence scores."
        )
    )

    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    args = parser.parse_args()

    run_generator(
        db_path=args.db,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()