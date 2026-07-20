from __future__ import annotations

import argparse
import math
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.pdfgen import canvas


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "nifty100.db"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports" / "tearsheets"

SAMPLE_TICKERS = ["TCS", "HDFCBANK", "RELIANCE", "SUNPHARMA", "TATASTEEL"]

NAVY = colors.HexColor("#102A43")
NAVY_LIGHT = colors.HexColor("#D9EAF7")
TEXT = colors.HexColor("#243B53")
MUTED = colors.HexColor("#627D98")
BORDER = colors.HexColor("#D9E2EC")
GREEN = colors.HexColor("#1B7F5A")
GREEN_BG = colors.HexColor("#E8F5EE")
RED = colors.HexColor("#B42318")
RED_BG = colors.HexColor("#FDECEC")
AMBER = colors.HexColor("#9A6700")
AMBER_BG = colors.HexColor("#FFF4D6")
WHITE = colors.white


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def extract_year(value: object) -> int | None:
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


def format_number(value: object, decimals: int = 1, suffix: str = "") -> str:
    number = safe_float(value)
    if number is None:
        return "N/A"
    return f"{number:,.{decimals}f}{suffix}"


def format_crore(value: object) -> str:
    number = safe_float(value)
    if number is None:
        return "N/A"
    sign = "-" if number < 0 else ""
    return f"{sign}Rs. {abs(number):,.0f} Cr"


def clean_name(value: object) -> str:
    return " ".join(str(value or "").split())


def prepare_history(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    result = df.copy()
    result["year_num"] = result["year"].map(extract_year)
    result = result.dropna(subset=["year_num"]).copy()
    result["year_num"] = result["year_num"].astype(int)
    sort_cols = ["company_id", "year_num"]
    if "id" in result.columns:
        sort_cols.append("id")
    result = result.sort_values(sort_cols)
    return result.drop_duplicates(["company_id", "year_num"], keep="last").reset_index(drop=True)


def tail_years(df: pd.DataFrame, count: int = 10) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    return df.sort_values("year_num").tail(count).reset_index(drop=True)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_company_bundle(conn: sqlite3.Connection, ticker: str) -> dict:
    ticker = ticker.strip().upper()

    company = pd.read_sql_query(
        """
        SELECT
            c.id AS company_id,
            c.company_name,
            c.about_company,
            s.broad_sector,
            s.sub_sector
        FROM companies c
        LEFT JOIN sectors s ON s.company_id = c.id
        WHERE UPPER(c.id) = ?
        """,
        conn,
        params=[ticker],
    )

    if company.empty:
        raise ValueError(f"Ticker not found: {ticker}")

    def query(table: str) -> pd.DataFrame:
        return pd.read_sql_query(
            f"SELECT * FROM {table} WHERE UPPER(company_id) = ?",
            conn,
            params=[ticker],
        )

    return {
        "company": company.iloc[0].to_dict(),
        "ratios": prepare_history(query("financial_ratios")),
        "pl": prepare_history(query("profitandloss")),
        "bs": prepare_history(query("balancesheet")),
        "cf": prepare_history(query("cashflow")),
        "db_pros_cons": query("prosandcons"),
    }


def load_generated_pros_cons(output_dir: Path, ticker: str, db_fallback: pd.DataFrame) -> tuple[list[str], list[str]]:
    path = output_dir / "pros_cons_generated.csv"
    pros: list[str] = []
    cons: list[str] = []

    if path.exists():
        try:
            df = pd.read_csv(path)
            if {"company_id", "type", "text"}.issubset(df.columns):
                subset = df[df["company_id"].astype(str).str.upper() == ticker.upper()].copy()
                if "confidence_pct" in subset.columns:
                    subset["confidence_pct"] = pd.to_numeric(subset["confidence_pct"], errors="coerce")
                    subset = subset.sort_values("confidence_pct", ascending=False)
                pros = subset.loc[subset["type"].astype(str).str.lower() == "pro", "text"].dropna().astype(str).tolist()
                cons = subset.loc[subset["type"].astype(str).str.lower() == "con", "text"].dropna().astype(str).tolist()
        except Exception:
            pass

    if not pros and not db_fallback.empty and "pros" in db_fallback.columns:
        pros = db_fallback["pros"].dropna().astype(str).tolist()
    if not cons and not db_fallback.empty and "cons" in db_fallback.columns:
        cons = db_fallback["cons"].dropna().astype(str).tolist()

    if not pros:
        pros = ["No high-confidence positive signal was available in the current dataset."]
    if not cons:
        cons = ["No high-confidence risk signal was available in the current dataset."]

    return pros[:4], cons[:4]


def classify_capital_allocation(cfo: float | None, cfi: float | None, cff: float | None) -> str:
    if None in (cfo, cfi, cff):
        return "Insufficient Data"
    signs = (
        "+" if float(cfo) >= 0 else "-",
        "+" if float(cfi) >= 0 else "-",
        "+" if float(cff) >= 0 else "-",
    )
    mapping = {
        ("+", "-", "-"): "Reinvestor",
        ("+", "+", "-"): "Liquidating Assets",
        ("-", "+", "+"): "Distress Signal",
        ("-", "-", "+"): "Growth Funded by Debt",
        ("+", "+", "+"): "Cash Accumulator",
        ("-", "-", "-"): "Pre-Revenue",
        ("+", "-", "+"): "Mixed",
    }
    return mapping.get(signs, "Other")


def load_capital_allocation(output_dir: Path, ticker: str, cf_history: pd.DataFrame) -> str:
    excel_path = output_dir / "cashflow_intelligence.xlsx"
    if excel_path.exists():
        try:
            df = pd.read_excel(excel_path)
            company_col = next((c for c in ["company_id", "ticker"] if c in df.columns), None)
            label_col = next(
                (c for c in ["capital_allocation_label", "capital_allocation_pattern", "pattern_label"] if c in df.columns),
                None,
            )
            if company_col and label_col:
                row = df[df[company_col].astype(str).str.upper() == ticker.upper()]
                if not row.empty and pd.notna(row.iloc[0][label_col]):
                    return str(row.iloc[0][label_col])
        except Exception:
            pass

    csv_path = output_dir / "capital_allocation.csv"
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            if {"company_id", "year", "pattern_label"}.issubset(df.columns):
                subset = df[df["company_id"].astype(str).str.upper() == ticker.upper()].copy()
                subset["year_num"] = subset["year"].map(extract_year)
                subset = subset.dropna(subset=["year_num"]).sort_values("year_num")
                if not subset.empty:
                    return str(subset.iloc[-1]["pattern_label"])
        except Exception:
            pass

    if cf_history.empty:
        return "Insufficient Data"
    latest = cf_history.sort_values("year_num").iloc[-1]
    return classify_capital_allocation(
        safe_float(latest.get("operating_activity")),
        safe_float(latest.get("investing_activity")),
        safe_float(latest.get("financing_activity")),
    )


# ---------------------------------------------------------------------------
# Chart creation
# ---------------------------------------------------------------------------

def save_revenue_profit_chart(pl: pd.DataFrame, path: Path) -> None:
    data = tail_years(pl, 10)
    fig, ax = plt.subplots(figsize=(8.2, 3.0), dpi=160)
    if data.empty:
        ax.text(0.5, 0.5, "No Profit & Loss history available", ha="center", va="center")
        ax.axis("off")
    else:
        years = data["year_num"].astype(str).tolist()
        sales = pd.to_numeric(data["sales"], errors="coerce").fillna(0).to_numpy(dtype=float)
        net_profit = pd.to_numeric(data["net_profit"], errors="coerce").fillna(0).to_numpy(dtype=float)
        x = np.arange(len(years))
        width = 0.38
        ax.bar(x - width / 2, sales, width, label="Revenue")
        ax.bar(x + width / 2, net_profit, width, label="Net Profit")
        ax.set_xticks(x)
        ax.set_xticklabels(years, rotation=40, ha="right", fontsize=8)
        ax.set_ylabel("Rs. Crore", fontsize=9)
        ax.set_title("10-Year Revenue and Net Profit", loc="left", fontsize=11, fontweight="bold")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(frameon=False, fontsize=8, ncol=2)
        ax.tick_params(axis="y", labelsize=8)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def save_roe_roce_chart(ratios: pd.DataFrame, path: Path) -> None:
    data = tail_years(ratios, 10)
    fig, ax1 = plt.subplots(figsize=(8.2, 3.0), dpi=160)
    if data.empty:
        ax1.text(0.5, 0.5, "No ratio history available", ha="center", va="center")
        ax1.axis("off")
    else:
        years = data["year_num"].astype(str).tolist()
        roe = pd.to_numeric(data["return_on_equity_pct"], errors="coerce")
        roce = pd.to_numeric(data["return_on_capital_employed_pct"], errors="coerce")
        x = np.arange(len(years))
        line1 = ax1.plot(x, roe, marker="o", linewidth=2, label="ROE")
        ax1.set_ylabel("ROE (%)", fontsize=9)
        ax1.set_xticks(x)
        ax1.set_xticklabels(years, rotation=40, ha="right", fontsize=8)
        ax1.grid(axis="y", alpha=0.25)
        ax1.tick_params(axis="y", labelsize=8)
        ax2 = ax1.twinx()
        line2 = ax2.plot(x, roce, marker="s", linewidth=2, linestyle="--", label="ROCE")
        ax2.set_ylabel("ROCE (%)", fontsize=9)
        ax2.tick_params(axis="y", labelsize=8)
        lines = line1 + line2
        ax1.legend(lines, [line.get_label() for line in lines], frameon=False, fontsize=8, loc="best")
        ax1.set_title("10-Year ROE and ROCE Trend", loc="left", fontsize=11, fontweight="bold")
        ax1.spines["top"].set_visible(False)
        ax2.spines["top"].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def save_balance_sheet_chart(bs: pd.DataFrame, path: Path) -> None:
    data = tail_years(bs, 10)
    fig, ax = plt.subplots(figsize=(5.0, 3.0), dpi=160)
    if data.empty:
        ax.text(0.5, 0.5, "No balance-sheet history available", ha="center", va="center")
        ax.axis("off")
    else:
        years = data["year_num"].astype(str).tolist()
        equity = (
            pd.to_numeric(data["equity_capital"], errors="coerce").fillna(0)
            + pd.to_numeric(data["reserves"], errors="coerce").fillna(0)
        ).to_numpy(dtype=float)
        borrowings = pd.to_numeric(data["borrowings"], errors="coerce").fillna(0).to_numpy(dtype=float)
        other = pd.to_numeric(data["other_liabilities"], errors="coerce").fillna(0).to_numpy(dtype=float)
        x = np.arange(len(years))
        ax.bar(x, equity, label="Equity + Reserves")
        ax.bar(x, borrowings, bottom=equity, label="Borrowings")
        ax.bar(x, other, bottom=equity + borrowings, label="Other Liabilities")
        ax.set_xticks(x)
        ax.set_xticklabels(years, rotation=45, ha="right", fontsize=7)
        ax.set_ylabel("Rs. Crore", fontsize=8)
        ax.set_title("Balance Sheet Composition", loc="left", fontsize=10, fontweight="bold")
        ax.tick_params(axis="y", labelsize=7)
        ax.grid(axis="y", alpha=0.2)
        ax.legend(frameon=False, fontsize=6.5, ncol=1)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def save_cashflow_waterfall(cf: pd.DataFrame, path: Path) -> None:
    data = tail_years(cf, 1)
    fig, ax = plt.subplots(figsize=(5.0, 3.0), dpi=160)
    if data.empty:
        ax.text(0.5, 0.5, "No cash-flow data available", ha="center", va="center")
        ax.axis("off")
    else:
        row = data.iloc[-1]
        cfo = safe_float(row.get("operating_activity")) or 0.0
        cfi = safe_float(row.get("investing_activity")) or 0.0
        cff = safe_float(row.get("financing_activity")) or 0.0
        net = safe_float(row.get("net_cash_flow"))
        if net is None:
            net = cfo + cfi + cff

        changes = [cfo, cfi, cff]
        starts = [0.0]
        for value in changes[:-1]:
            starts.append(starts[-1] + value)

        for idx, (start, value) in enumerate(zip(starts, changes)):
            bottom = start if value >= 0 else start + value
            ax.bar(idx, abs(value), bottom=bottom, width=0.62)
            ax.plot([idx - 0.31, idx + 0.31], [start, start], linewidth=0.8)
        ax.bar(3, net, width=0.62)
        ax.axhline(0, linewidth=0.8)
        ax.set_xticks(range(4))
        ax.set_xticklabels(["CFO", "CFI", "CFF", "Net Cash"], fontsize=8)
        ax.set_ylabel("Rs. Crore", fontsize=8)
        ax.set_title(f"Cash Flow Waterfall - {int(row['year_num'])}", loc="left", fontsize=10, fontweight="bold")
        ax.tick_params(axis="y", labelsize=7)
        ax.grid(axis="y", alpha=0.2)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# PDF drawing helpers
# ---------------------------------------------------------------------------

def build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "kpi_label": ParagraphStyle(
            "KpiLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            textColor=MUTED,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "kpi_value": ParagraphStyle(
            "KpiValue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=16,
            textColor=NAVY,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=10.6,
            textColor=TEXT,
            alignment=TA_LEFT,
            wordWrap="CJK",
            leftIndent=0,
            rightIndent=0,
            spaceAfter=2,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            textColor=TEXT,
            wordWrap="CJK",
        ),
    }


def draw_header(c: canvas.Canvas, company_name: str, ticker: str, page_title: str) -> None:
    width, height = A4
    c.setFillColor(NAVY)
    c.rect(0, height - 22 * mm, width, 22 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(15 * mm, height - 12.5 * mm, company_name[:58])
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 15 * mm, height - 9.5 * mm, ticker)
    c.setFont("Helvetica", 7.5)
    c.drawRightString(width - 15 * mm, height - 15 * mm, page_title)


def draw_section_title(c: canvas.Canvas, title: str, x: float, y: float, width: float) -> None:
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(x, y, title)
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.8)
    c.line(x, y - 2, x + width, y - 2)


def draw_kpi_grid(c: canvas.Canvas, kpis: list[tuple[str, str]], y_top: float, styles: dict[str, ParagraphStyle]) -> None:
    page_width, _ = A4
    margin = 15 * mm
    available = page_width - 2 * margin
    gap = 4 * mm
    tile_w = (available - 2 * gap) / 3
    tile_h = 23 * mm

    for index, (label, value) in enumerate(kpis[:6]):
        row = index // 3
        col = index % 3
        x = margin + col * (tile_w + gap)
        y = y_top - (row + 1) * tile_h - row * 3 * mm

        c.setFillColor(colors.HexColor("#F7FAFC"))
        c.setStrokeColor(BORDER)
        c.roundRect(x, y, tile_w, tile_h, 4, fill=1, stroke=1)

        label_p = Paragraph(label, styles["kpi_label"])
        value_p = Paragraph(value, styles["kpi_value"])
        _, lh = label_p.wrap(tile_w - 8, 12 * mm)
        _, vh = value_p.wrap(tile_w - 8, 12 * mm)
        label_p.drawOn(c, x + 4, y + tile_h - 7 * mm - lh / 2)
        value_p.drawOn(c, x + 4, y + 5 * mm - vh / 2 + 5)


def draw_bullet_box(
    c: canvas.Canvas,
    title: str,
    items: Iterable[str],
    x: float,
    y: float,
    width: float,
    height: float,
    accent: colors.Color,
    background: colors.Color,
    styles: dict[str, ParagraphStyle],
) -> None:
    c.setFillColor(background)
    c.setStrokeColor(accent)
    c.roundRect(x, y, width, height, 5, fill=1, stroke=1)
    c.setFillColor(accent)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + 8, y + height - 15, title)

    data = []
    for text in list(items)[:4]:
        bullet = f"<font color='{accent.hexval()}'>●</font>&nbsp;&nbsp;{str(text)}"
        data.append([Paragraph(bullet, styles["bullet"])])

    if not data:
        data = [[Paragraph("N/A", styles["bullet"])]]

    table = Table(data, colWidths=[width - 18], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    _, table_h = table.wrap(width - 18, height - 28)
    max_h = height - 29
    if table_h <= max_h:
        table.drawOn(c, x + 9, y + height - 25 - table_h)
    else:
        # A defensive fallback: use the first three rows if unusually long text exceeds the box.
        table = Table(data[:3], colWidths=[width - 18], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )
        _, table_h = table.wrap(width - 18, max_h)
        table.drawOn(c, x + 9, y + height - 25 - table_h)


def draw_badge(c: canvas.Canvas, label: str, x: float, y: float, width: float) -> None:
    distress = label in {"Distress Signal", "Growth Funded by Debt", "Pre-Revenue"}
    fill = RED_BG if distress else AMBER_BG
    stroke = RED if distress else AMBER
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.roundRect(x, y, width, 15 * mm, 6, fill=1, stroke=1)
    c.setFillColor(stroke)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x + 8, y + 9.5 * mm, "CAPITAL ALLOCATION")
    c.setFont("Helvetica-Bold", 12)
    max_text_width = width - 16
    text = label
    while stringWidth(text, "Helvetica-Bold", 12) > max_text_width and len(text) > 4:
        text = text[:-1]
    if text != label:
        text = text.rstrip() + "..."
    c.drawString(x + 8, y + 3.8 * mm, text)


# ---------------------------------------------------------------------------
# Main tearsheet generation
# ---------------------------------------------------------------------------

def generate_tearsheet(
    ticker: str,
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> Path:
    ticker = ticker.strip().upper()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    report_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = report_dir / f"{ticker}_tearsheet.pdf"

    with sqlite3.connect(db_path) as conn:
        bundle = load_company_bundle(conn, ticker)

    company = bundle["company"]
    ratios = bundle["ratios"]
    pl = bundle["pl"]
    bs = bundle["bs"]
    cf = bundle["cf"]

    latest_ratio = ratios.sort_values("year_num").iloc[-1] if not ratios.empty else pd.Series(dtype=object)
    latest_pl = pl.sort_values("year_num").iloc[-1] if not pl.empty else pd.Series(dtype=object)

    pros, cons = load_generated_pros_cons(output_dir, ticker, bundle["db_pros_cons"])
    capital_label = load_capital_allocation(output_dir, ticker, cf)

    company_name = clean_name(company.get("company_name")) or ticker
    sector = clean_name(company.get("broad_sector")) or "N/A"
    sub_sector = clean_name(company.get("sub_sector")) or "N/A"

    kpis = [
        ("Return on Equity", format_number(latest_ratio.get("return_on_equity_pct"), 1, "%")),
        ("ROCE", format_number(latest_ratio.get("return_on_capital_employed_pct"), 1, "%")),
        ("Net Profit Margin", format_number(latest_ratio.get("net_profit_margin_pct"), 1, "%")),
        ("Debt to Equity", format_number(latest_ratio.get("debt_to_equity"), 2, "x")),
        ("Revenue CAGR (5Y)", format_number(latest_ratio.get("revenue_cagr_5yr"), 1, "%")),
        ("Free Cash Flow", format_crore(latest_ratio.get("free_cash_flow_cr"))),
    ]

    styles = build_styles()
    ensure_parent(pdf_path)

    with tempfile.TemporaryDirectory(prefix=f"{ticker}_tearsheet_") as tmp:
        tmpdir = Path(tmp)
        revenue_chart = tmpdir / "revenue_profit.png"
        roe_chart = tmpdir / "roe_roce.png"
        bs_chart = tmpdir / "balance_sheet.png"
        cf_chart = tmpdir / "cashflow_waterfall.png"

        save_revenue_profit_chart(pl, revenue_chart)
        save_roe_roce_chart(ratios, roe_chart)
        save_balance_sheet_chart(bs, bs_chart)
        save_cashflow_waterfall(cf, cf_chart)

        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        page_w, page_h = A4
        margin = 15 * mm
        content_w = page_w - 2 * margin

        # Page 1
        draw_header(c, company_name, ticker, "Company Tearsheet - Page 1 of 2")
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8.5)
        c.drawString(margin, page_h - 29 * mm, f"{sector}  |  {sub_sector}  |  Latest FY: {int(latest_ratio.get('year_num')) if not latest_ratio.empty and pd.notna(latest_ratio.get('year_num')) else 'N/A'}")

        draw_kpi_grid(c, kpis, page_h - 34 * mm, styles)

        # Keep the first chart fully below the two-row KPI grid.
        chart1_y = page_h - 145 * mm
        draw_section_title(c, "Growth and Earnings", margin, chart1_y + 52 * mm, content_w)
        c.drawImage(str(revenue_chart), margin, chart1_y, width=content_w, height=49 * mm, preserveAspectRatio=True, anchor="c", mask="auto")

        chart2_y = 18 * mm
        draw_section_title(c, "Capital Efficiency Trend", margin, chart2_y + 66 * mm, content_w)
        c.drawImage(str(roe_chart), margin, chart2_y, width=content_w, height=63 * mm, preserveAspectRatio=True, anchor="c", mask="auto")

        c.showPage()

        # Page 2
        draw_header(c, company_name, ticker, "Company Tearsheet - Page 2 of 2")

        chart_gap = 5 * mm
        chart_w = (content_w - chart_gap) / 2
        chart_h = 71 * mm
        chart_y = page_h - 104 * mm
        draw_section_title(c, "Balance Sheet and Cash Flow", margin, chart_y + chart_h + 5 * mm, content_w)
        c.drawImage(str(bs_chart), margin, chart_y, width=chart_w, height=chart_h, preserveAspectRatio=True, anchor="c", mask="auto")
        c.drawImage(str(cf_chart), margin + chart_w + chart_gap, chart_y, width=chart_w, height=chart_h, preserveAspectRatio=True, anchor="c", mask="auto")

        boxes_y = 55 * mm
        box_gap = 5 * mm
        box_w = (content_w - box_gap) / 2
        box_h = 74 * mm
        draw_bullet_box(c, "Pros", pros, margin, boxes_y, box_w, box_h, GREEN, GREEN_BG, styles)
        draw_bullet_box(c, "Cons", cons, margin + box_w + box_gap, boxes_y, box_w, box_h, RED, RED_BG, styles)

        draw_badge(c, capital_label, margin, 20 * mm, content_w)

        c.save()

    return pdf_path


def generate_sample_tearsheets(
    tickers: Iterable[str],
    db_path: Path,
    output_dir: Path,
    report_dir: Path,
) -> list[Path]:
    generated: list[Path] = []
    failures: list[tuple[str, str]] = []

    for ticker in tickers:
        try:
            generated.append(generate_tearsheet(ticker, db_path, output_dir, report_dir))
        except Exception as exc:
            failures.append((ticker, str(exc)))

    print("=" * 68)
    print("DAY 33 - PDF TEARSHEET TEMPLATE COMPLETE")
    print("=" * 68)
    print(f"Requested tickers          : {len(list(tickers)) if not isinstance(tickers, list) else len(tickers)}")
    print(f"Generated PDFs             : {len(generated)}")
    print(f"Failures                   : {len(failures)}")
    print()
    for path in generated:
        print(f"Generated: {path}")
    for ticker, reason in failures:
        print(f"FAILED {ticker}: {reason}")

    return generated


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 2-page Nifty100 company tearsheets.")
    parser.add_argument("--tickers", nargs="+", default=SAMPLE_TICKERS, help="Tickers to generate. Defaults to the five Sprint 5 sample companies.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()

    generate_sample_tearsheets(
        [ticker.upper() for ticker in args.tickers],
        args.db,
        args.output_dir,
        args.report_dir,
    )


if __name__ == "__main__":
    main()