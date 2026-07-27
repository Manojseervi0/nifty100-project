from __future__ import annotations

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "nifty100.db"

INDEX_REQUIREMENTS = {
    "financial_ratios": ("company_id", "year"),
    "profitandloss": ("company_id", "year"),
    "balancesheet": ("company_id", "year"),
    "cashflow": ("company_id", "year"),
    "market_cap": ("company_id", "year"),
}


def quote_identifier(value: str) -> str:
    """Safely quote a SQLite identifier."""

    return '"' + value.replace('"', '""') + '"'


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    """Return whether a table exists in the database."""

    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    """Return all column names available in a table."""

    rows = connection.execute(
        f"PRAGMA table_info({quote_identifier(table_name)})"
    ).fetchall()
    return {str(row[1]) for row in rows}


def create_required_indexes(connection: sqlite3.Connection) -> None:
    """Create only safe company/year indexes on existing columns."""

    for table_name, columns in INDEX_REQUIREMENTS.items():
        if not table_exists(connection, table_name):
            print(f"[SKIP] Missing table: {table_name}")
            continue

        available_columns = table_columns(connection, table_name)
        missing_columns = [
            column for column in columns
            if column not in available_columns
        ]

        if missing_columns:
            print(
                f"[SKIP] {table_name}: missing columns "
                f"{', '.join(missing_columns)}"
            )
            continue

        index_name = (
            f"idx_{table_name}_"
            + "_".join(column.lower() for column in columns)
        )
        quoted_columns = ", ".join(
            quote_identifier(column) for column in columns
        )

        connection.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {quote_identifier(index_name)}
            ON {quote_identifier(table_name)} ({quoted_columns})
            """
        )

        print(
            f"[PASS] {index_name} -> "
            f"{table_name}({', '.join(columns)})"
        )


def verify_required_indexes(
    connection: sqlite3.Connection,
) -> bool:
    """Verify every required table has a matching compound index."""

    all_passed = True

    print("\nVerification")
    print("-" * 72)

    for table_name, expected_columns in INDEX_REQUIREMENTS.items():
        if not table_exists(connection, table_name):
            print(f"[FAIL] {table_name}: table missing")
            all_passed = False
            continue

        index_rows = connection.execute(
            f"PRAGMA index_list({quote_identifier(table_name)})"
        ).fetchall()

        matching_indexes: list[str] = []

        for index_row in index_rows:
            index_name = str(index_row[1])
            info_rows = connection.execute(
                f"PRAGMA index_info({quote_identifier(index_name)})"
            ).fetchall()
            indexed_columns = tuple(str(row[2]) for row in info_rows)

            if indexed_columns == expected_columns:
                matching_indexes.append(index_name)

        if matching_indexes:
            print(
                f"[PASS] {table_name}: "
                f"{', '.join(matching_indexes)}"
            )
        else:
            print(
                f"[FAIL] {table_name}: no index on "
                f"({', '.join(expected_columns)})"
            )
            all_passed = False

    return all_passed


def main() -> None:
    """Create and verify safe Sprint 6 SQLite indexes."""

    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_PATH}"
        )

    print(f"Database: {DATABASE_PATH}")
    print("Creating safe indexes only")
    print("-" * 72)

    with sqlite3.connect(DATABASE_PATH) as connection:
        create_required_indexes(connection)
        connection.commit()
        all_passed = verify_required_indexes(connection)

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    print("\nDatabase integrity:", integrity)
    print("Final status:", "PASS" if all_passed and integrity == "ok" else "FAIL")

    if not all_passed or integrity != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
