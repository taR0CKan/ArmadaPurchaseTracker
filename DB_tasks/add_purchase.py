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
                submission_procedure, initial_price, source_message, purchase_URL
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                purchase_number,
                record.get("description"),
                record.get("start_date"),
                record.get("end_date"),
                record.get("submission_procedure"),
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
) -> bool:
    """Update executor/approval for a Telegram reaction change."""
    old_thumb = "👍" in old_reactions
    new_thumb = "👍" in new_reactions
    old_ok = "👌" in old_reactions
    new_ok = "👌" in new_reactions

    with sqlite3.connect(DB_PATH) as connection:
        if new_thumb and not old_thumb:
            connection.execute(
                "UPDATE purchases SET executor = ? WHERE source_message = ?",
                (str(user_id), str(message_id)),
            )
        elif old_thumb and not new_thumb:
            connection.execute(
                "UPDATE purchases SET executor = NULL "
                "WHERE source_message = ? AND executor = ?",
                (str(message_id), str(user_id)),
            )

        if user_id == approver_user_id and old_ok != new_ok:
            connection.execute(
                "UPDATE purchases SET is_approved = ? WHERE source_message = ?",
                (int(new_ok), str(message_id)),
            )

        return connection.total_changes > 0
