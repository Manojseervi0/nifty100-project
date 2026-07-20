from __future__ import annotations

import argparse
import math
import re
import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.reports.tearsheet import generate_tearsheet


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "nifty100.db"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_TEARSHEET_DIR = PROJECT_ROOT / "reports" / "tearsheets"
DEFAULT_SECTOR_DIR = PROJECT_ROOT / "reports" / "sector"

NAVY = colors.HexColor("#102A43")
NAVY_2 = colors.HexColor("#243B53")
LIGHT_BLUE = colors.HexColor("#EAF2F8")
LIGHT_GREY = colors.HexColor("#F5F7FA")
MID_GREY = colors.HexColor("#D9E2EC")
TEXT = colors.HexColor("#243B53")
MUTED = colors.HexColor("#627D98")
WHITE = colors.white
GREEN = colors.HexColor("#1B7F5A")
RED = colors.HexColor("#B42318")

# The project database currently stores power-related businesses inside
# broad_sector='Energy'. Sprint 5 requires 11 sector reports, so for reporting
# only we promote clearly utility-oriented sub-sectors into a separate
# 'Utilities' reporting sector. The database itself is not modified.
UTILITY_SUBSECTORS = {
    "power & utilities",
    "power transmission",
    "renewable energy",
}

METRICS = [
    ("return_on_equity_pct", "ROE", "%", 1),
    ("return_on_capital_employed_pct", "ROCE", "%", 1),
    ("net_profit_margin_pct", "Net Profit Margin", "%", 1),
    ("debt_to_equity", "Debt / Equity", "x", 2),
    ("revenue_cagr_5yr", "Revenue CAGR 5Y", "%", 1),
    ("pat_cagr_5yr", "PAT CAGR 5Y", "%", 1),
    ("eps_cagr_5yr", "EPS CAGR 5Y", "%", 1),
    ("composite_quality_score", "Composite Score", "", 1),
]


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


def format_metric(value: object, suffix: str = "", decimals: int = 1) -> str:
    number = safe_float(value)
    if number is None:
        return "N/A"
    return f"{number:,.{decimals}f}{suffix}"


def reporting_sector(broad_sector: object, sub_sector: object) -> str:
    broad = str(broad_sector or "Unknown").strip() or "Unknown"
    sub = str(sub_sector or "").strip().lower()
    if broad.lower() == "energy" and sub in UTILITY_SUBSECTORS:
        return "Utilities"
    return broad


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_")
    return slug.lower() or "unknown"


def load_company_universe(conn: sqlite3.Connection) -> pd.DataFrame:
    companies = pd.read_sql_query(
        """
        SELECT
            c.id AS company_id,
            c.company_name,
            COALESCE(s.broad_sector, 'Unknown') AS broad_sector,
            COALESCE(s.sub_sector, 'Unknown') AS sub_sector
        FROM companies c
        LEFT JOIN sectors s ON s.company_id = c.id
        ORDER BY c.id
        """,
        conn,
    )

    coverage = pd.read_sql_query(
        """
        SELECT company_id, year
        FROM profitandloss
        """,
        conn,
    )

    if coverage.empty:
        year_counts = pd.DataFrame(columns=["company_id", "available_years"])
    else:
        coverage["year_num"] = coverage["year"].map(extract_year)
        coverage = coverage.dropna(subset=["year_num"])
        year_counts = (
            coverage.groupby("company_id")["year_num"]
            .nunique()
            .rename("available_years")
            .reset_index()
        )

    companies = companies.merge(year_counts, on="company_id", how="left")
    companies["available_years"] = companies["available_years"].fillna(0).astype(int)
    companies["reporting_sector"] = companies.apply(
        lambda row: reporting_sector(row["broad_sector"], row["sub_sector"]), axis=1
    )
    return companies


def load_latest_metrics(conn: sqlite3.Connection) -> pd.DataFrame:
    ratios = pd.read_sql_query("SELECT * FROM financial_ratios", conn)
    if ratios.empty:
        return pd.DataFrame(columns=["company_id"] + [col for col, *_ in METRICS])

    ratios["year_num"] = ratios["year"].map(extract_year)
    ratios = ratios.dropna(subset=["year_num"]).copy()
    ratios["year_num"] = ratios["year_num"].astype(int)

    sort_columns = ["company_id", "year_num"]
    if "id" in ratios.columns:
        sort_columns.append("id")

    ratios = ratios.sort_values(sort_columns)
    latest = ratios.drop_duplicates("company_id", keep="last").copy()
    keep = ["company_id", "year", "year_num"] + [col for col, *_ in METRICS]
    return latest[[column for column in keep if column in latest.columns]]


def generate_batch_tearsheets(
    companies: pd.DataFrame,
    db_path: Path,
    output_dir: Path,
    report_dir: Path,
    min_years: int = 3,
    min_size_kb: int = 30,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    report_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    skipped_rows: list[dict] = []
    audit_rows: list[dict] = []

    for row in companies.itertuples(index=False):
        ticker = str(row.company_id).upper()
        years = int(row.available_years)

        if years < min_years:
            skipped_rows.append(
                {
                    "company_id": ticker,
                    "company_name": row.company_name,
                    "available_years": years,
                    "reason": f"Fewer than {min_years} years of Profit & Loss data",
                }
            )
            audit_rows.append(
                {
                    "company_id": ticker,
                    "status": "SKIPPED",
                    "available_years": years,
                    "file_size_kb": None,
                    "message": skipped_rows[-1]["reason"],
                }
            )
            continue

        existing_path = report_dir / f"{ticker}_tearsheet.pdf"
        if existing_path.exists():
            existing_size_kb = round(existing_path.stat().st_size / 1024, 1)
            if existing_size_kb >= min_size_kb:
                audit_rows.append(
                    {
                        "company_id": ticker,
                        "status": "EXISTING_VALID",
                        "available_years": years,
                        "file_size_kb": existing_size_kb,
                        "message": "Existing PDF already meets size threshold",
                    }
                )
                continue

        try:
            path = generate_tearsheet(
                ticker=ticker,
                db_path=db_path,
                output_dir=output_dir,
                report_dir=report_dir,
            )
            size_kb = round(path.stat().st_size / 1024, 1) if path.exists() else 0.0
            status = "GENERATED" if size_kb >= min_size_kb else "TOO_SMALL"
            message = "OK" if status == "GENERATED" else f"PDF below {min_size_kb} KB threshold"
            audit_rows.append(
                {
                    "company_id": ticker,
                    "status": status,
                    "available_years": years,
                    "file_size_kb": size_kb,
                    "message": message,
                }
            )
        except Exception as exc:
            audit_rows.append(
                {
                    "company_id": ticker,
                    "status": "FAILED",
                    "available_years": years,
                    "file_size_kb": None,
                    "message": str(exc),
                }
            )

    skipped_df = pd.DataFrame(
        skipped_rows,
        columns=["company_id", "company_name", "available_years", "reason"],
    )
    audit_df = pd.DataFrame(
        audit_rows,
        columns=["company_id", "status", "available_years", "file_size_kb", "message"],
    )

    skipped_df.to_csv(output_dir / "skipped_tearsheets.csv", index=False)
    audit_df.to_csv(output_dir / "tearsheet_batch_audit.csv", index=False)
    return skipped_df, audit_df


def build_pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "SectorTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=27,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=4 * mm,
        ),
        "subtitle": ParagraphStyle(
            "SectorSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=MUTED,
            alignment=TA_LEFT,
            spaceAfter=5 * mm,
        ),
        "section": ParagraphStyle(
            "SectorSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=17,
            textColor=NAVY_2,
            spaceBefore=3 * mm,
            spaceAfter=3 * mm,
        ),
        "cell": ParagraphStyle(
            "SectorCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9,
            textColor=TEXT,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "cell_center": ParagraphStyle(
            "SectorCellCenter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9,
            textColor=TEXT,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "header": ParagraphStyle(
            "SectorHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9,
            textColor=WHITE,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "tile_label": ParagraphStyle(
            "TileLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "tile_value": ParagraphStyle(
            "TileValue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=NAVY,
            alignment=TA_CENTER,
        ),
    }


def _page_header_footer(canvas, doc, sector_name: str) -> None:
    canvas.saveState()
    page_w, page_h = landscape(A4)
    canvas.setFillColor(NAVY)
    canvas.rect(0, page_h - 10 * mm, page_w, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(12 * mm, page_h - 6.5 * mm, f"Nifty100 Analytics - {sector_name} Sector Report")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawRightString(page_w - 12 * mm, 7 * mm, f"Page {doc.page}")
    canvas.restoreState()


def generate_sector_pdf(sector_name: str, sector_df: pd.DataFrame, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = build_pdf_styles()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=18 * mm,
        bottomMargin=13 * mm,
        title=f"{sector_name} Sector Report",
        author="Nifty100 Analytics",
    )

    story = []
    story.append(Paragraph(f"{sector_name} Sector Report", styles["title"]))
    latest_years = pd.to_numeric(sector_df.get("year_num"), errors="coerce").dropna()
    latest_year = int(latest_years.max()) if not latest_years.empty else None
    year_text = str(latest_year) if latest_year else "latest available year"
    story.append(
        Paragraph(
            f"Summary of {len(sector_df)} companies using latest available financial ratios. "
            f"Reference year: {year_text}. Median calculations ignore unavailable values.",
            styles["subtitle"],
        )
    )

    story.append(Paragraph("Sector Median KPIs", styles["section"]))

    tiles = []
    for column, label, suffix, decimals in METRICS:
        series = pd.to_numeric(sector_df.get(column), errors="coerce")
        median = series.median() if series.notna().any() else None
        tiles.append(
            [
                Paragraph(label, styles["tile_label"]),
                Paragraph(format_metric(median, suffix, decimals), styles["tile_value"]),
            ]
        )

    tile_rows = []
    for start in range(0, len(tiles), 4):
        chunk = tiles[start : start + 4]
        label_row = [item[0] for item in chunk]
        value_row = [item[1] for item in chunk]
        while len(label_row) < 4:
            label_row.append(Paragraph("", styles["tile_label"]))
            value_row.append(Paragraph("", styles["tile_value"]))
        tile_rows.extend([label_row, value_row])

    tile_table = Table(tile_rows, colWidths=[65 * mm] * 4, rowHeights=[9 * mm, 14 * mm, 9 * mm, 14 * mm])
    tile_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE),
                ("BOX", (0, 0), (-1, -1), 0.6, MID_GREY),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, MID_GREY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(KeepTogether([tile_table]))
    story.append(Spacer(1, 6 * mm))

    # Sector composition summary helps the first page stay useful even when the
    # detailed company table spans multiple pages.
    sub_counts = (
        sector_df.groupby("sub_sector", dropna=False)["company_id"]
        .count()
        .sort_values(ascending=False)
        .reset_index(name="companies")
    )
    story.append(Paragraph("Sector Composition", styles["section"]))
    composition_data = [
        [Paragraph("Sub-sector", styles["header"]), Paragraph("Companies", styles["header"])]
    ]
    for row in sub_counts.itertuples(index=False):
        composition_data.append(
            [Paragraph(str(row.sub_sector), styles["cell"]), Paragraph(str(row.companies), styles["cell_center"])]
        )
    composition_table = Table(composition_data, colWidths=[110 * mm, 35 * mm], repeatRows=1)
    composition_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.4, MID_GREY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(composition_table)
    story.append(PageBreak())

    story.append(Paragraph("Company Comparison - Latest Available Metrics", styles["section"]))

    headers = ["Ticker", "Company"] + [label for _, label, _, _ in METRICS]
    table_data = [[Paragraph(header, styles["header"]) for header in headers]]

    display_df = sector_df.sort_values(
        ["composite_quality_score", "company_id"], ascending=[False, True], na_position="last"
    )

    for row in display_df.to_dict("records"):
        cells = [
            Paragraph(str(row.get("company_id", "")), styles["cell_center"]),
            Paragraph(str(row.get("company_name", "")), styles["cell"]),
        ]
        for column, _label, suffix, decimals in METRICS:
            cells.append(Paragraph(format_metric(row.get(column), suffix, decimals), styles["cell_center"]))
        table_data.append(cells)

    col_widths = [21 * mm, 48 * mm] + [23.5 * mm] * len(METRICS)
    company_table = Table(table_data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    company_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.35, MID_GREY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(company_table)

    doc.build(
        story,
        onFirstPage=lambda c, d: _page_header_footer(c, d, sector_name),
        onLaterPages=lambda c, d: _page_header_footer(c, d, sector_name),
    )
    return output_path


def generate_all_sector_reports(
    companies: pd.DataFrame,
    latest_metrics: pd.DataFrame,
    sector_dir: Path,
) -> pd.DataFrame:
    sector_dir.mkdir(parents=True, exist_ok=True)
    merged = companies.merge(latest_metrics, on="company_id", how="left")
    audit_rows: list[dict] = []

    for sector_name, sector_df in merged.groupby("reporting_sector", sort=True):
        path = sector_dir / f"{slugify(str(sector_name))}_report.pdf"
        try:
            generate_sector_pdf(str(sector_name), sector_df.copy(), path)
            audit_rows.append(
                {
                    "sector": sector_name,
                    "companies": len(sector_df),
                    "status": "GENERATED",
                    "file": str(path),
                    "file_size_kb": round(path.stat().st_size / 1024, 1),
                }
            )
        except Exception as exc:
            audit_rows.append(
                {
                    "sector": sector_name,
                    "companies": len(sector_df),
                    "status": "FAILED",
                    "file": str(path),
                    "file_size_kb": None,
                    "message": str(exc),
                }
            )

    return pd.DataFrame(audit_rows)


def run_day34(
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    tearsheet_dir: Path = DEFAULT_TEARSHEET_DIR,
    sector_dir: Path = DEFAULT_SECTOR_DIR,
    min_years: int = 3,
    min_size_kb: int = 30,
    generate_tearsheets: bool = True,
    generate_sectors: bool = True,
) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        companies = load_company_universe(conn)
        latest_metrics = load_latest_metrics(conn)

    skipped_df = pd.DataFrame()
    tearsheet_audit = pd.DataFrame()
    if generate_tearsheets:
        skipped_df, tearsheet_audit = generate_batch_tearsheets(
            companies=companies,
            db_path=db_path,
            output_dir=output_dir,
            report_dir=tearsheet_dir,
            min_years=min_years,
            min_size_kb=min_size_kb,
        )

    sector_audit = pd.DataFrame()
    if generate_sectors:
        sector_audit = generate_all_sector_reports(companies, latest_metrics, sector_dir)
        sector_audit.to_csv(output_dir / "sector_report_audit.csv", index=False)

    raw_sector_count = int(companies["broad_sector"].nunique(dropna=True))
    reporting_sector_count = int(companies["reporting_sector"].nunique(dropna=True))

    generated_tearsheets = (
        int(tearsheet_audit["status"].isin(["GENERATED", "EXISTING_VALID"]).sum())
        if not tearsheet_audit.empty
        else 0
    )
    too_small = int((tearsheet_audit["status"] == "TOO_SMALL").sum()) if not tearsheet_audit.empty else 0
    failed_tearsheets = int((tearsheet_audit["status"] == "FAILED").sum()) if not tearsheet_audit.empty else 0
    generated_sectors = int((sector_audit["status"] == "GENERATED").sum()) if not sector_audit.empty else 0
    failed_sectors = int((sector_audit["status"] == "FAILED").sum()) if not sector_audit.empty else 0

    print("=" * 72)
    print("DAY 34 - BATCH REPORT GENERATION COMPLETE")
    print("=" * 72)
    print(f"Canonical companies        : {len(companies)}")
    print(f"Raw broad sectors          : {raw_sector_count}")
    print(f"Reporting sectors          : {reporting_sector_count}")
    if generate_tearsheets:
        print(f"Eligible tearsheets        : {len(companies) - len(skipped_df)}")
        print(f"Generated tearsheets       : {generated_tearsheets}")
        print(f"Skipped (<{min_years} years)       : {len(skipped_df)}")
        print(f"PDFs below {min_size_kb} KB        : {too_small}")
        print(f"Tearsheet failures         : {failed_tearsheets}")
    if generate_sectors:
        print(f"Generated sector PDFs      : {generated_sectors}")
        print(f"Sector report failures     : {failed_sectors}")
    print()
    if generate_tearsheets:
        print(f"Tearsheets : {tearsheet_dir}")
        print(f"Skip log   : {output_dir / 'skipped_tearsheets.csv'}")
        print(f"Batch audit: {output_dir / 'tearsheet_batch_audit.csv'}")
    if generate_sectors:
        print(f"Sector PDFs: {sector_dir}")
        print(f"Sector audit: {output_dir / 'sector_report_audit.csv'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Sprint 5 Day 34 company tearsheets and sector reports."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--tearsheet-dir", type=Path, default=DEFAULT_TEARSHEET_DIR)
    parser.add_argument("--sector-dir", type=Path, default=DEFAULT_SECTOR_DIR)
    parser.add_argument("--min-years", type=int, default=3)
    parser.add_argument("--min-size-kb", type=int, default=30)
    parser.add_argument("--skip-tearsheets", action="store_true")
    parser.add_argument("--skip-sector-reports", action="store_true")
    args = parser.parse_args()

    run_day34(
        db_path=args.db,
        output_dir=args.output_dir,
        tearsheet_dir=args.tearsheet_dir,
        sector_dir=args.sector_dir,
        min_years=args.min_years,
        min_size_kb=args.min_size_kb,
        generate_tearsheets=not args.skip_tearsheets,
        generate_sectors=not args.skip_sector_reports,
    )


if __name__ == "__main__":
    main()