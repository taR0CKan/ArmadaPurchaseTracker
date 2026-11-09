"""Create the SQLite database for parsed 223-FZ purchases."""

import sqlite3
from pathlib import Path
from decimal import Decimal, InvalidOperation


DB_PATH = Path(__file__).resolve().parent.parent / "purchases.db"


def ensure_reminders_table() -> None:
    """Create a reminder ledger keyed by purchase, status, and lead time."""
    with sqlite3.connect(DB_PATH, timeout=30) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(purchases)")}
        if "executor_name" not in columns:
            connection.execute("ALTER TABLE purchases ADD COLUMN executor_name TEXT")
        reminder_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(purchase_reminders)")
        }
        if reminder_columns and "status" not in reminder_columns:
            connection.execute("ALTER TABLE purchase_reminders RENAME TO purchase_reminders_old")
            connection.execute(
                """CREATE TABLE purchase_reminders (
                    purchase_number TEXT NOT NULL,
                    status TEXT NOT NULL,
                    lead_days INTEGER NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY (purchase_number, status, lead_days)
                )"""
            )
            connection.execute(
                """INSERT INTO purchase_reminders
                   (purchase_number, status, lead_days, sent_at)
                   SELECT purchase_number, 'processing', lead_days, sent_at
                   FROM purchase_reminders_old"""
            )
            connection.execute("DROP TABLE purchase_reminders_old")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS purchase_reminders (
                purchase_number TEXT NOT NULL,
                status TEXT NOT NULL,
                lead_days INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (purchase_number, status, lead_days)
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
            or "status" not in columns or "is_approved" in columns
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
                    status TEXT NOT NULL DEFAULT 'unchecked',
                    purchase_URL TEXT
                )
                """
            )
            for record in old_records:
                record.setdefault("description", None)
                record.setdefault("source_message", None)
                record.setdefault("executor", None)
                record.setdefault("executor_name", None)
                if "status" not in record:
                    record["status"] = (
                        "preapproved" if record.get("is_approved") else "unchecked"
                    )
                record.setdefault("purchase_URL", None)
                price = record.get("initial_price")
                if price is not None and column_types.get("initial_price") != "INTEGER":
                    try:
                        record["initial_price"] = int(Decimal(str(price)) * 100)
                    except InvalidOperation:
                        record["initial_price"] = None
                connection.execute(
                    """INSERT INTO purchases (
                        purchase_number, description, start_date, end_date,
                        submission_procedure, initial_price, source_message,
                        executor, executor_name, status, purchase_URL
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    tuple(record.get(name) for name in (
                        "purchase_number", "description", "start_date", "end_date",
                        "submission_procedure", "initial_price", "source_message",
                        "executor", "executor_name", "status", "purchase_URL"
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
                status TEXT NOT NULL DEFAULT 'unchecked',
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
        if "status" not in columns:
            if "is_approved" in columns:
                connection.execute(
                    "ALTER TABLE purchases ADD COLUMN status TEXT NOT NULL DEFAULT 'unchecked'"
                )
                connection.execute(
                    "UPDATE purchases SET status = 'preapproved' WHERE is_approved = 1"
                )
                connection.execute("ALTER TABLE purchases DROP COLUMN is_approved")
            else:
                connection.execute(
                    "ALTER TABLE purchases ADD COLUMN status TEXT NOT NULL DEFAULT 'unchecked'"
                )
        if "purchase_URL" not in columns:
            connection.execute("ALTER TABLE purchases ADD COLUMN purchase_URL TEXT")
    ensure_reminders_table()
    print(f"Database ready: {DB_PATH}")


if __name__ == "__main__":
    main()
