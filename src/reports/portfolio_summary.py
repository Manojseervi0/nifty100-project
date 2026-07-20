from __future__ import annotations

import argparse
import math
import re
import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "nifty100.db"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports" / "portfolio" / "portfolio_summary.pdf"

NAVY = colors.HexColor("#102A43")
NAVY_2 = colors.HexColor("#243B53")
TEXT = colors.HexColor("#243B53")
MUTED = colors.HexColor("#627D98")
BORDER = colors.HexColor("#D9E2EC")
CARD_BG = colors.HexColor("#F7FAFC")
GREEN = colors.HexColor("#1B7F5A")
GREEN_BG = colors.HexColor("#E8F5EE")
RED = colors.HexColor("#B42318")
RED_BG = colors.HexColor("#FDECEC")
AMBER = colors.HexColor("#9A6700")
AMBER_BG = colors.HexColor("#FFF4D6")
WHITE = colors.white

# Lower is better only for leverage.
METRICS = [
    {
        "column": "return_on_equity_pct",
        "label": "ROE",
        "suffix": "%",
        "decimals": 1,
        "lower_is_better": False,
    },
    {
        "column": "return_on_capital_employed_pct",
        "label": "ROCE",
        "suffix": "%",
        "decimals": 1,
        "lower_is_better": False,
    },
    {
        "column": "net_profit_margin_pct",
        "label": "Net Profit Margin",
        "suffix": "%",
        "decimals": 1,
        "lower_is_better": False,
    },
    {
        "column": "debt_to_equity",
        "label": "Debt / Equity",
        "suffix": "x",
        "decimals": 2,
        "lower_is_better": True,
    },
    {
        "column": "revenue_cagr_5yr",
        "label": "Revenue CAGR 5Y",
        "suffix": "%",
        "decimals": 1,
        "lower_is_better": False,
    },
    {
        "column": "free_cash_flow_cr",
        "label": "Free Cash Flow",
        "suffix": " Cr",
        "decimals": 0,
        "lower_is_better": False,
        "prefix": "Rs. ",
    },
]


def extract_year(value: object) -> int | None:
    """Extract the last 4-digit financial year from mixed year strings."""
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


def clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def format_metric(value: object, metric: dict) -> str:
    number = safe_float(value)
    if number is None:
        return "N/A"

    prefix = metric.get("prefix", "")
    suffix = metric.get("suffix", "")
    decimals = int(metric.get("decimals", 1))
    return f"{prefix}{number:,.{decimals}f}{suffix}"


def prepare_ratio_history(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise years and keep one final record per company-year."""
    if df.empty:
        return df.copy()

    result = df.copy()
    result["year_num"] = result["year"].map(extract_year)
    result = result.dropna(subset=["year_num"]).copy()
    result["year_num"] = result["year_num"].astype(int)

    sort_columns = ["company_id", "year_num"]
    if "id" in result.columns:
        sort_columns.append("id")

    result = result.sort_values(sort_columns)
    return result.drop_duplicates(["company_id", "year_num"], keep="last").reset_index(drop=True)


def load_companies(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            c.id AS company_id,
            c.company_name,
            COALESCE(s.broad_sector, 'Unknown') AS broad_sector,
            COALESCE(s.sub_sector, 'Unknown') AS sub_sector
        FROM companies c
        LEFT JOIN sectors s ON s.company_id = c.id
        ORDER BY UPPER(c.id), c.id
        """,
        conn,
    )


def load_ratios(conn: sqlite3.Connection) -> pd.DataFrame:
    return prepare_ratio_history(
        pd.read_sql_query("SELECT * FROM financial_ratios", conn)
    )


def company_latest_previous(
    ratios: pd.DataFrame,
    ticker: str,
) -> tuple[pd.Series | None, pd.Series | None, int]:
    subset = ratios[
        ratios["company_id"].astype(str).str.upper() == ticker.upper()
    ].sort_values("year_num")

    if subset.empty:
        return None, None, 0

    latest = subset.iloc[-1]
    previous = subset.iloc[-2] if len(subset) >= 2 else None
    return latest, previous, int(subset["year_num"].nunique())


def trend_status(
    latest_value: object,
    previous_value: object,
    *,
    lower_is_better: bool = False,
    flat_threshold_pct: float = 2.0,
) -> str:
    """
    Return one of: UP, DOWN, FLAT, NA.

    UP/DOWN describe business improvement, not the raw numeric direction.
    For Debt/Equity, a lower latest value is therefore an improvement (UP).
    Values within +/-2% of the previous value are treated as FLAT.
    """
    latest = safe_float(latest_value)
    previous = safe_float(previous_value)

    if latest is None or previous is None:
        return "NA"

    if previous == 0:
        if abs(latest) <= 0.02:
            return "FLAT"
        raw_improved = latest < previous if lower_is_better else latest > previous
        return "UP" if raw_improved else "DOWN"

    change_pct = ((latest - previous) / abs(previous)) * 100
    if abs(change_pct) <= flat_threshold_pct:
        return "FLAT"

    raw_improved = latest < previous if lower_is_better else latest > previous
    return "UP" if raw_improved else "DOWN"


def trend_change_text(
    latest_value: object,
    previous_value: object,
    *,
    lower_is_better: bool = False,
) -> str:
    latest = safe_float(latest_value)
    previous = safe_float(previous_value)

    if latest is None or previous is None:
        return "No prior comparison"

    if previous == 0:
        return "Changed from zero base"

    change_pct = ((latest - previous) / abs(previous)) * 100
    if lower_is_better:
        # This text reports the raw metric movement, while the arrow reports quality direction.
        direction = "lower" if latest < previous else "higher"
        return f"{abs(change_pct):.1f}% {direction} vs prior year"

    direction = "higher" if latest > previous else "lower"
    return f"{abs(change_pct):.1f}% {direction} vs prior year"


def draw_trend_arrow(
    c: canvas.Canvas,
    x: float,
    y: float,
    status: str,
    size: float = 7 * mm,
) -> None:
    """Draw arrows as vector lines to avoid missing Unicode arrow glyphs."""
    if status == "UP":
        stroke = GREEN
        fill = GREEN_BG
    elif status == "DOWN":
        stroke = RED
        fill = RED_BG
    elif status == "FLAT":
        stroke = AMBER
        fill = AMBER_BG
    else:
        stroke = MUTED
        fill = colors.HexColor("#EEF2F6")

    radius = size / 2
    c.setFillColor(fill)
    c.setStrokeColor(fill)
    c.circle(x, y, radius, stroke=0, fill=1)

    c.setStrokeColor(stroke)
    c.setFillColor(stroke)
    c.setLineWidth(1.8)

    shaft = size * 0.34
    head = size * 0.17

    if status == "UP":
        c.line(x, y - shaft, x, y + shaft)
        c.line(x, y + shaft, x - head, y + shaft - head)
        c.line(x, y + shaft, x + head, y + shaft - head)
    elif status == "DOWN":
        c.line(x, y + shaft, x, y - shaft)
        c.line(x, y - shaft, x - head, y - shaft + head)
        c.line(x, y - shaft, x + head, y - shaft + head)
    elif status == "FLAT":
        c.line(x - shaft, y, x + shaft, y)
        c.line(x + shaft, y, x + shaft - head, y + head)
        c.line(x + shaft, y, x + shaft - head, y - head)
    else:
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(x, y - 2, "N/A")


def draw_wrapped_paragraph(
    c: canvas.Canvas,
    text: str,
    x: float,
    y_top: float,
    width: float,
    height: float,
    style: ParagraphStyle,
) -> None:
    paragraph = Paragraph(text, style)
    _, required_height = paragraph.wrap(width, height)
    paragraph.drawOn(c, x, y_top - min(required_height, height))


def draw_header(
    c: canvas.Canvas,
    company: pd.Series,
    page_number: int,
    total_pages: int,
) -> None:
    page_w, page_h = A4
    header_h = 43 * mm

    c.setFillColor(NAVY)
    c.rect(0, page_h - header_h, page_w, header_h, stroke=0, fill=1)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PortfolioCompanyTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=23,
        textColor=WHITE,
        alignment=TA_LEFT,
    )

    company_name = clean_text(company.get("company_name")) or str(company["company_id"])
    ticker = str(company["company_id"]).upper()
    draw_wrapped_paragraph(
        c,
        company_name,
        15 * mm,
        page_h - 11 * mm,
        page_w - 30 * mm,
        19 * mm,
        title_style,
    )

    c.setFillColor(colors.HexColor("#D9EAF7"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(15 * mm, page_h - 33 * mm, ticker)

    c.setFont("Helvetica", 9)
    sector = clean_text(company.get("broad_sector")) or "Unknown"
    sub_sector = clean_text(company.get("sub_sector")) or "Unknown"
    c.drawString(41 * mm, page_h - 33 * mm, f"{sector} | {sub_sector}")

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#BCCCDC"))
    c.drawRightString(
        page_w - 15 * mm,
        page_h - 33 * mm,
        f"Company {page_number} of {total_pages}",
    )


def draw_kpi_card(
    c: canvas.Canvas,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    metric: dict,
    latest: pd.Series | None,
    previous: pd.Series | None,
) -> None:
    c.setFillColor(CARD_BG)
    c.setStrokeColor(BORDER)
    c.roundRect(x, y, width, height, 4 * mm, stroke=1, fill=1)

    column = metric["column"]
    latest_value = latest.get(column) if latest is not None and column in latest.index else None
    previous_value = previous.get(column) if previous is not None and column in previous.index else None

    status = trend_status(
        latest_value,
        previous_value,
        lower_is_better=bool(metric.get("lower_is_better", False)),
    )

    c.setFillColor(MUTED)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(x + 5 * mm, y + height - 8 * mm, metric["label"])

    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 16)
    value_text = format_metric(latest_value, metric)
    c.drawString(x + 5 * mm, y + height - 19 * mm, value_text)

    arrow_x = x + width - 12 * mm
    arrow_y = y + height - 17 * mm
    draw_trend_arrow(c, arrow_x, arrow_y, status, 8 * mm)

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.5)
    change_text = trend_change_text(
        latest_value,
        previous_value,
        lower_is_better=bool(metric.get("lower_is_better", False)),
    )
    c.drawString(x + 5 * mm, y + 7 * mm, change_text)


def draw_snapshot_table(
    c: canvas.Canvas,
    latest: pd.Series | None,
    previous: pd.Series | None,
    x: float,
    y_top: float,
    width: float,
) -> None:
    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y_top, "Latest vs Previous Financial Year")

    y = y_top - 8 * mm
    row_h = 8 * mm
    col_widths = [width * 0.42, width * 0.25, width * 0.25]

    latest_year = str(int(latest["year_num"])) if latest is not None and pd.notna(latest.get("year_num")) else "Latest"
    prev_year = str(int(previous["year_num"])) if previous is not None and pd.notna(previous.get("year_num")) else "Previous"

    headers = ["Metric", latest_year, prev_year]
    c.setFillColor(NAVY_2)
    c.rect(x, y - row_h, width, row_h, stroke=0, fill=1)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8)

    cursor = x
    for header, col_w in zip(headers, col_widths):
        c.drawString(cursor + 3 * mm, y - 5.2 * mm, header)
        cursor += col_w

    y -= row_h
    for idx, metric in enumerate(METRICS):
        fill = colors.white if idx % 2 == 0 else colors.HexColor("#F7FAFC")
        c.setFillColor(fill)
        c.setStrokeColor(BORDER)
        c.rect(x, y - row_h, width, row_h, stroke=1, fill=1)

        latest_value = latest.get(metric["column"]) if latest is not None and metric["column"] in latest.index else None
        previous_value = previous.get(metric["column"]) if previous is not None and metric["column"] in previous.index else None

        values = [
            metric["label"],
            format_metric(latest_value, metric),
            format_metric(previous_value, metric),
        ]

        c.setFillColor(TEXT)
        c.setFont("Helvetica", 7.8)
        cursor = x
        for value, col_w in zip(values, col_widths):
            c.drawString(cursor + 3 * mm, y - 5.2 * mm, str(value))
            cursor += col_w

        y -= row_h


def draw_page(
    c: canvas.Canvas,
    company: pd.Series,
    ratios: pd.DataFrame,
    page_number: int,
    total_pages: int,
) -> None:
    page_w, page_h = A4
    draw_header(c, company, page_number, total_pages)

    ticker = str(company["company_id"]).upper()
    latest, previous, available_years = company_latest_previous(ratios, ticker)

    latest_year = (
        str(int(latest["year_num"]))
        if latest is not None and pd.notna(latest.get("year_num"))
        else "N/A"
    )

    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(15 * mm, page_h - 54 * mm, "Financial KPI Snapshot")

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8.5)
    c.drawRightString(
        page_w - 15 * mm,
        page_h - 54 * mm,
        f"Latest ratio year: {latest_year} | Available ratio years: {available_years}",
    )

    margin_x = 15 * mm
    gap_x = 5 * mm
    card_w = (page_w - (2 * margin_x) - (2 * gap_x)) / 3
    card_h = 35 * mm
    first_row_y = page_h - 96 * mm
    second_row_y = first_row_y - card_h - 6 * mm

    for index, metric in enumerate(METRICS):
        row = index // 3
        col = index % 3
        x = margin_x + col * (card_w + gap_x)
        y = first_row_y if row == 0 else second_row_y
        draw_kpi_card(
            c,
            x=x,
            y=y,
            width=card_w,
            height=card_h,
            metric=metric,
            latest=latest,
            previous=previous,
        )

    snapshot_y = second_row_y - 15 * mm
    draw_snapshot_table(
        c,
        latest,
        previous,
        x=15 * mm,
        y_top=snapshot_y,
        width=page_w - 30 * mm,
    )

    note_y = 25 * mm
    c.setFillColor(colors.HexColor("#EEF4F8"))
    c.roundRect(15 * mm, note_y, page_w - 30 * mm, 17 * mm, 3 * mm, stroke=0, fill=1)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.5)
    c.drawString(
        20 * mm,
        note_y + 10 * mm,
        "Trend arrow meaning: up = improved, down = deteriorated, right = flat within 2%.",
    )
    c.drawString(
        20 * mm,
        note_y + 5 * mm,
        "For Debt / Equity, a decrease is treated as an improvement. Missing history is shown as N/A.",
    )

    c.setStrokeColor(BORDER)
    c.line(15 * mm, 15 * mm, page_w - 15 * mm, 15 * mm)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(15 * mm, 10 * mm, "Nifty100 Analytics Dashboard - Portfolio Summary")
    c.drawRightString(page_w - 15 * mm, 10 * mm, f"Page {page_number} / {total_pages}")


def generate_portfolio_summary(
    db_path: Path = DEFAULT_DB_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    tickers: Iterable[str] | None = None,
) -> Path:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    report_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        companies = load_companies(conn)
        ratios = load_ratios(conn)

    if tickers:
        requested = {str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()}
        companies = companies[
            companies["company_id"].astype(str).str.upper().isin(requested)
        ].copy()

    companies = companies.sort_values(
        by="company_id",
        key=lambda series: series.astype(str).str.upper(),
    ).reset_index(drop=True)

    if companies.empty:
        raise ValueError("No companies found for portfolio report generation.")

    pdf = canvas.Canvas(str(report_path), pagesize=A4, pageCompression=1)
    pdf.setTitle("Nifty100 Portfolio Summary")
    pdf.setAuthor("Nifty100 Analytics Dashboard")
    pdf.setSubject("One-page financial summary for each company")

    total_pages = len(companies)
    for page_number, (_, company) in enumerate(companies.iterrows(), start=1):
        draw_page(
            pdf,
            company=company,
            ratios=ratios,
            page_number=page_number,
            total_pages=total_pages,
        )
        pdf.showPage()

    pdf.save()
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the Sprint 5 portfolio summary PDF."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to nifty100.db",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Output PDF path",
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        default=None,
        help="Optional subset of tickers for QA testing",
    )
    args = parser.parse_args()

    output_path = generate_portfolio_summary(
        db_path=args.db,
        report_path=args.output,
        tickers=args.tickers,
    )

    with sqlite3.connect(args.db) as conn:
        canonical_count = int(conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0])

    if args.tickers:
        requested_count = len({ticker.upper() for ticker in args.tickers})
        pages_expected = requested_count
    else:
        pages_expected = canonical_count

    file_size_mb = output_path.stat().st_size / (1024 * 1024)

    print("=" * 72)
    print("DAY 35 - PORTFOLIO SUMMARY PDF COMPLETE")
    print("=" * 72)
    print(f"Canonical companies        : {canonical_count}")
    print(f"Pages expected             : {pages_expected}")
    print(f"Output size                : {file_size_mb:.2f} MB")
    print()
    print(f"Generated: {output_path}")


if __name__ == "__main__":
    main()