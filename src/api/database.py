from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "nifty100.db"


def get_connection() -> sqlite3.Connection:
    """Create and return a configured SQLite connection."""

    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_PATH}"
        )

    connection = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False,
    )

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Provide a SQLite connection for FastAPI dependencies."""

    connection = get_connection()

    try:
        yield connection
    finally:
        connection.close()


def fetch_table_counts() -> dict[str, int]:
    """Return row counts for all user-created database tables."""

    connection = get_connection()

    try:
        table_rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        counts: dict[str, int] = {}

        for row in table_rows:
            table_name = row["name"]

            result = connection.execute(
                f'SELECT COUNT(*) AS row_count FROM "{table_name}"'
            ).fetchone()

            counts[table_name] = int(result["row_count"])

        return counts

    finally:
        connection.close()