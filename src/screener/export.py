from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from pathlib import Path

import pandas as pd

from src.screener.engine import (
    load_screener_data,
    normalize_sector_scores,
    run_all_presets,
)


OUTPUT_PATH = Path("output")
OUTPUT_PATH.mkdir(exist_ok=True)


def export_screener_results():
    """
    Export all preset screener results to Excel.
    """

    df = load_screener_data()

    df = normalize_sector_scores(df)

    preset_results = run_all_presets(df)

    output_file = OUTPUT_PATH / "screener_output.xlsx"

    with pd.ExcelWriter(
        output_file,
        engine="openpyxl"
    ) as writer:

        for preset_name, preset_df in preset_results.items():

            preset_df = (
                preset_df
                .sort_values("year")
                .drop_duplicates(
                    subset="company_id",
                    keep="last"
                )
            )
            preset_df = preset_df.sort_values(
                by="sector_quality_score",
                ascending=False
            )
            # Keep latest year only

            preset_df = preset_df.rename(
                columns={

                    "company_id":"Company",

                    "year":"Year",

                    "return_on_equity_pct":"ROE %",

                    "return_on_capital_employed_pct":"ROCE %",

                    "net_profit_margin_pct":"NPM %",

                    "operating_profit_margin_pct":"OPM %",

                    "debt_to_equity":"D/E",

                    "interest_coverage":"ICR",

                    "asset_turnover":"Asset Turnover",

                    "free_cash_flow_cr":"FCF (Cr)",

                    "revenue_cagr_5yr":"Revenue CAGR",

                    "pat_cagr_5yr":"PAT CAGR",

                    "eps_cagr_5yr":"EPS CAGR",

                    "composite_quality_score":"Quality Score",

                    "sector_quality_score":"Sector Score",

                    "market_cap_crore":"Market Cap",

                    "pe_ratio":"P/E",

                    "pb_ratio":"P/B",

                    "dividend_yield_pct":"Dividend Yield",

                    "sales":"Sales",

                    "net_profit":"Net Profit",

                    "broad_sector":"Sector"
                }
            )
            preset_df = preset_df[
                [
                    "Company",
                    "Year",
                    "Sector",
                    "ROE %",
                    "ROCE %",
                    "NPM %",
                    "OPM %",
                    "D/E",
                    "ICR",
                    "Asset Turnover",
                    "FCF (Cr)",
                    "Revenue CAGR",
                    "PAT CAGR",
                    "EPS CAGR",
                    "Quality Score",
                    "Sector Score",
                    "Market Cap",
                    "P/E",
                    "P/B",
                    "Dividend Yield",
                    "Sales",
                    "Net Profit",
                ]
            ]
            preset_df.to_excel(
                writer,
                sheet_name=preset_name[:31],   # Excel sheet limit
                index=False
            )

            worksheet = writer.sheets[preset_name[:31]]

            # Bold header
            for cell in worksheet[1]:
                cell.font = Font(bold=True)

            # Freeze top row
            worksheet.freeze_panes = "A2"

            # Auto-fit columns
            for column_cells in worksheet.columns:
                length = max(
                    len(str(cell.value)) if cell.value is not None else 0
                    for cell in column_cells
                )

                worksheet.column_dimensions[
                    get_column_letter(column_cells[0].column)
                ].width = min(length + 2, 30)

    print(f"Exported to {output_file}")


if __name__ == "__main__":
    export_screener_results()