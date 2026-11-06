"""SQLite operations for purchase deadline reminders."""

import sqlite3
from datetime import datetime

from DB_tasks.create_database import DB_PATH


def load_reminder_data() -> tuple[list[tuple], set[tuple]]:
    """Load purchases and the reminder lead times already sent for them."""
    with sqlite3.connect(DB_PATH, timeout=30) as connection:
        purchases = connection.execute(
            """SELECT purchase_number, description, end_date, initial_price,
                      executor, executor_name, purchase_URL
               FROM purchases
               WHERE end_date IS NOT NULL"""
        ).fetchall()
        sent = set(
            connection.execute(
                "SELECT purchase_number, lead_days FROM purchase_reminders"
            ).fetchall()
        )
    return purchases, sent


def mark_reminder_sent(purchase_number: str, lead_days: int, sent_at: datetime) -> None:
    """Record a successfully delivered reminder."""
    with sqlite3.connect(DB_PATH, timeout=30) as connection:
        connection.execute(
            """INSERT OR IGNORE INTO purchase_reminders
               (purchase_number, lead_days, sent_at) VALUES (?, ?, ?)""",
            (purchase_number, lead_days, sent_at.isoformat(timespec="seconds")),
        )
