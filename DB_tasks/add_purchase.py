"""Save parsed purchase data received from fetch_zakupki_page to SQLite."""

import sqlite3

from DB_tasks.create_database import DB_PATH


def add_purchase(record: dict[str, str | None]) -> bool:
    """Insert one parsed purchase. Return True if a new row was added."""
    purchase_number = record.get("purchase_number")
    if not purchase_number:
        raise ValueError("purchase_number is missing")

    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO purchases (
                purchase_number, description, start_date, end_date,
                submission_procedure, purchase_method, initial_price,
                source_message, purchase_URL, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'unchecked')
            """,
            (
                purchase_number,
                record.get("description"),
                record.get("start_date"),
                record.get("end_date"),
                record.get("submission_procedure"),
                record.get("purchase_method"),
                record.get("initial_price"),
                str(record["source_message"]) if record.get("source_message") is not None else None,
                record.get("purchase_URL"),
            ),
        )
    return bool(cursor.rowcount)


def update_message_reaction(
    message_id: int,
    user_id: int,
    old_reactions: set[str],
    new_reactions: set[str],
    approver_user_id: int | None,
    executor_name: str | None = None,
) -> bool:
    """Apply status transitions and executor assignment from added reactions."""
    added = new_reactions - old_reactions
    with sqlite3.connect(DB_PATH) as connection:
        purchase = connection.execute(
            "SELECT status FROM purchases WHERE source_message = ?",
            (str(message_id),),
        ).fetchone()
        if purchase is None:
            return False

        status = purchase[0] or "unchecked"
        changed = False
        if "👍" in added:
            connection.execute(
                "UPDATE purchases SET executor = ?, executor_name = ? WHERE source_message = ?",
                (str(user_id), executor_name, str(message_id)),
            )
            changed = True

        new_status = status
        if user_id == approver_user_id:
            if status in {"approved", "cancelled"}:
                if "🔥" in added and status == "cancelled":
                    new_status = "approved"
                elif "👎" in added and status == "approved":
                    new_status = "cancelled"
            elif "👌" in added:
                new_status = "preapproved"
            elif "🔥" in added:
                new_status = "approved"
            elif "👎" in added:
                new_status = "cancelled"
        elif "👍" in added:
            new_status = "processing"

        if new_status != status:
            connection.execute(
                "UPDATE purchases SET status = ? WHERE source_message = ?",
                (new_status, str(message_id)),
            )
            changed = True
        return changed
