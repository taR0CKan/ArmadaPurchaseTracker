"""Create the SQLite database for parsed 223-FZ purchases."""

import sqlite3
from pathlib import Path
from decimal import Decimal, InvalidOperation


DB_PATH = Path(__file__).resolve().parent.parent / "purchases.db"


def ensure_reminders_table() -> None:
    """Create the reminder ledger and migrate the executor display name column."""
    with sqlite3.connect(DB_PATH, timeout=30) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(purchases)")}
        if "executor_name" not in columns:
            connection.execute("ALTER TABLE purchases ADD COLUMN executor_name TEXT")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS purchase_reminders (
                purchase_number TEXT NOT NULL,
                lead_days INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (purchase_number, lead_days)
            )"""
        )


def main() -> None:
    with sqlite3.connect(DB_PATH) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(purchases)")
        }
        column_types = {
            row[1]: row[2].upper()
            for row in connection.execute("PRAGMA table_info(purchases)")
        }
        if columns and (
            "description" not in columns or column_types.get("initial_price") != "INTEGER"
        ):
            old_rows = connection.execute("SELECT * FROM purchases").fetchall()
            old_names = [row[1] for row in connection.execute("PRAGMA table_info(purchases)")]
            old_records = [dict(zip(old_names, row)) for row in old_rows]
            connection.execute("ALTER TABLE purchases RENAME TO purchases_old")
            connection.execute(
                """
                CREATE TABLE purchases (
                    purchase_number TEXT PRIMARY KEY,
                    description TEXT,
                    start_date DATETIME,
                    end_date DATETIME,
                    submission_procedure TEXT,
                    initial_price INTEGER,
                    source_message TEXT,
                    executor TEXT,
                    executor_name TEXT,
                    is_approved INTEGER NOT NULL DEFAULT 0,
                    purchase_URL TEXT
                )
                """
            )
            for record in old_records:
                record.setdefault("description", None)
                record.setdefault("source_message", None)
                record.setdefault("executor", None)
                record.setdefault("executor_name", None)
                record.setdefault("is_approved", 0)
                record.setdefault("purchase_URL", None)
                price = record.get("initial_price")
                if price is not None:
                    try:
                        record["initial_price"] = int(Decimal(str(price)) * 100)
                    except InvalidOperation:
                        record["initial_price"] = None
                connection.execute(
                    """INSERT INTO purchases (
                        purchase_number, description, start_date, end_date,
                        submission_procedure, initial_price, source_message,
                        executor, executor_name, is_approved, purchase_URL
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    tuple(record.get(name) for name in (
                        "purchase_number", "description", "start_date", "end_date",
                        "submission_procedure", "initial_price", "source_message",
                        "executor", "executor_name", "is_approved", "purchase_URL"
                    )),
                )
            connection.execute("DROP TABLE purchases_old")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS purchases (
                purchase_number TEXT PRIMARY KEY,
                description TEXT,
                start_date DATETIME,
                end_date DATETIME,
                submission_procedure TEXT,
                initial_price INTEGER,
                source_message TEXT,
                executor TEXT,
                executor_name TEXT,
                is_approved INTEGER NOT NULL DEFAULT 0,
                purchase_URL TEXT
            )
            """
        )
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(purchases)")
        }
        if "source_message" not in columns:
            connection.execute("ALTER TABLE purchases ADD COLUMN source_message TEXT")
        if "executor" not in columns:
            connection.execute("ALTER TABLE purchases ADD COLUMN executor TEXT")
        if "executor_name" not in columns:
            connection.execute("ALTER TABLE purchases ADD COLUMN executor_name TEXT")
        if "is_approved" not in columns:
            connection.execute(
                "ALTER TABLE purchases ADD COLUMN is_approved INTEGER NOT NULL DEFAULT 0"
            )
        if "purchase_URL" not in columns:
            connection.execute("ALTER TABLE purchases ADD COLUMN purchase_URL TEXT")
    ensure_reminders_table()
    print(f"Database ready: {DB_PATH}")


if __name__ == "__main__":
    main()
