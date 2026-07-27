from __future__ import annotations

"""Day 43 — SQLite index optimisation.

Adds indexes on `company_id` (and the year/date column, where one exists)
for every large, company-scoped table. Uses `CREATE INDEX IF NOT EXISTS`
throughout, so running this script twice — or a hundred times — is a no-op
after the first run. Does not alter any table's columns or data: indexes
are a query-plan optimisation, not a schema change to the data model.

Run directly:
    python -m tests.performance.db_indexes
or:
    python tests/performance/db_indexes.py
"""

import sqlite3
import time
from pathlib import Path

from src.api.database import DATABASE_PATH

# Tables considered "large" for this pass: every company-scoped table with
# more than ~500 rows in the current dataset. Each entry maps table name ->
# the period column to pair with company_id, or None if the table has no
# such column (stock_prices stores `date`, not `year` — see below).
TARGET_TABLES: dict[str, str | None] = {
    "balancesheet": "year",
    "cashflow": "year",
    "financial_ratios": "year",
    "market_cap": "year",
    "profitandloss": "year",
    "peer_percentiles": "year",
    "documents": "Year",  # capitalised in this table only
    "stock_prices": "date",  # no `year` column exists on this table
}


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    """Return whether a table exists in the connected database."""

    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _column_exists(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    """Return whether a column exists on a table (case-insensitive)."""

    columns = {
        row[1].lower() for row in connection.execute(f'PRAGMA table_info("{table_name}")')
    }
    return column_name.lower() in columns


def _existing_index_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    """Return the set of index names already present on a table."""

    return {
        row[1] for row in connection.execute(f'PRAGMA index_list("{table_name}")')
    }


def create_indexes(connection: sqlite3.Connection) -> list[dict]:
    """Create company_id/year indexes for every target table.

    Returns a list of {table, index_name, column, created} records
    describing what happened, for logging/reporting purposes.
    """

    results: list[dict] = []

    for table_name, period_column in TARGET_TABLES.items():
        if not _table_exists(connection, table_name):
            results.append(
                {
                    "table": table_name,
                    "index_name": None,
                    "column": None,
                    "created": False,
                    "note": "table not found in this database — skipped",
                }
            )
            continue

        before = _existing_index_names(connection, table_name)

        # Single-column index on company_id (every WHERE company_id = ?
        # lookup in the routers benefits from this).
        if _column_exists(connection, table_name, "company_id"):
            index_name = f"idx_{table_name}_company_id"
            connection.execute(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                f'ON "{table_name}" (company_id)'
            )
            results.append(
                {
                    "table": table_name,
                    "index_name": index_name,
                    "column": "company_id",
                    "created": index_name not in before,
                }
            )

        # Single-column index on the period column (year, or date for
        # stock_prices), plus a composite (company_id, period) index for
        # queries that filter on both (e.g. valuation.py's
        # "company_id = ? AND year BETWEEN ? AND ?").
        if period_column and _column_exists(connection, table_name, period_column):
            year_index_name = f"idx_{table_name}_{period_column.lower()}"
            connection.execute(
                f'CREATE INDEX IF NOT EXISTS "{year_index_name}" '
                f'ON "{table_name}" ("{period_column}")'
            )
            results.append(
                {
                    "table": table_name,
                    "index_name": year_index_name,
                    "column": period_column,
                    "created": year_index_name not in before,
                }
            )

            if _column_exists(connection, table_name, "company_id"):
                composite_index_name = f"idx_{table_name}_company_id_{period_column.lower()}"
                connection.execute(
                    f'CREATE INDEX IF NOT EXISTS "{composite_index_name}" '
                    f'ON "{table_name}" (company_id, "{period_column}")'
                )
                results.append(
                    {
                        "table": table_name,
                        "index_name": composite_index_name,
                        "column": f"company_id, {period_column}",
                        "created": composite_index_name not in before,
                    }
                )
        elif period_column:
            results.append(
                {
                    "table": table_name,
                    "index_name": None,
                    "column": period_column,
                    "created": False,
                    "note": f"column '{period_column}' not found — skipped",
                }
            )

    connection.commit()
    return results


def _benchmark_lookup(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    sample_value: str,
    iterations: int = 200,
) -> float:
    """Time `iterations` lookups on one column and return total seconds."""

    start = time.perf_counter()

    for _ in range(iterations):
        connection.execute(
            f'SELECT * FROM "{table_name}" WHERE "{column_name}" = ?',
            (sample_value,),
        ).fetchall()

    return time.perf_counter() - start


def run() -> None:
    """Create indexes, print a before/after benchmark, and exit."""

    print(f"Database: {DATABASE_PATH}")

    if not Path(DATABASE_PATH).exists():
        print(f"ERROR: database not found at {DATABASE_PATH}")
        return

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        sample_company = connection.execute(
            "SELECT company_id FROM financial_ratios LIMIT 1"
        ).fetchone()
        sample_company_id = sample_company[0] if sample_company else "TCS"

        before_seconds = _benchmark_lookup(
            connection, "financial_ratios", "company_id", sample_company_id
        )

        results = create_indexes(connection)

        after_seconds = _benchmark_lookup(
            connection, "financial_ratios", "company_id", sample_company_id
        )

        print("\n--- Index creation ---")
        for row in results:
            status = "CREATED" if row["created"] else "already existed / skipped"
            note = f" ({row['note']})" if row.get("note") else ""
            print(f"  {row['table']:20s} {row['index_name'] or '-':40s} [{status}]{note}")

        print("\n--- Benchmark: 200x 'SELECT * FROM financial_ratios WHERE company_id = ?' ---")
        print(f"  Before indexing: {before_seconds * 1000:.2f} ms total")
        print(f"  After indexing:  {after_seconds * 1000:.2f} ms total")
        if before_seconds > 0:
            speedup = before_seconds / after_seconds if after_seconds > 0 else float("inf")
            print(f"  Speedup:         {speedup:.2f}x")

    finally:
        connection.close()


if __name__ == "__main__":
    run()
