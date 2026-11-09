"""Telegram bot commands."""

import os
import re
import sqlite3
from io import BytesIO
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message
from openpyxl import Workbook

from DB_tasks.create_database import DB_PATH


router = Router()
ENV_PATH = Path(__file__).with_name(".env")


HELP_TEXT = """
<b>Инструкция по использованию бота</b>
Бот собирает данные с каждой ссылки на закупку, отправленную во время его работы.
- Реакция 'Палец вверх' - 👍 сделает вас ответственным за задачу. Ответственным считается последний поставивший реакцию.
- Реакция 'OK' - 👌 одобряет закупку. Сработает только за закрепленным сотрудником. По умолчанию Александр.

<b>Доступные команды:</b>

/link — сохранить ID текущего чата для уведомлений. Обязательно перед началом работы.
/list — получить Excel-файл со всеми закупками.
/status "номер" — получить данные закупки по её номеру. Также можно ответить /status на сообщение с ссылкой.
/exclude "номер" — удалить закупку по её номеру. Также можно ответить /exclude на сообщение с ссылкой.
/help — показать эту инструкцию.
"""

@router.message(Command("help"))
async def send_help(message: Message) -> None:
    """Explain the available bot commands."""
    await message.answer(HELP_TEXT, parse_mode="HTML")


def _save_purchase_chat_id(chat_id: int) -> None:
    """Create or update PURCHASE_CHAT_ID while preserving other .env settings."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    setting = f"PURCHASE_CHAT_ID={chat_id}"
    pattern = re.compile(r"^\s*(?:export\s+)?PURCHASE_CHAT_ID\s*=.*$")

    for index, line in enumerate(lines):
        if pattern.match(line):
            lines[index] = setting
            break
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(setting)

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ["PURCHASE_CHAT_ID"] = str(chat_id)


@router.message(Command("link"))
async def link_active_chat(message: Message) -> None:
    """Save the current Telegram chat ID for the bot configuration."""
    if message.chat is None:
        await message.answer("Не удалось определить ID чата.")
        return

    try:
        _save_purchase_chat_id(message.chat.id)
    except OSError:
        await message.answer("Не удалось сохранить ID чата в .env.")
        return

    await message.answer(f"ID этого чата ({message.chat.id}) сохранён в PURCHASE_CHAT_ID.")


@router.message(Command("add"))
async def add_replied_purchase(message: Message, command: CommandObject) -> None:
    """Process a zakupki.gov.ru link in the message this command replies to."""
    if message.reply_to_message is None:
        await message.answer(
            "Telegram не передал цель reply для команды /add. "
            "Ответьте на исходное сообщение обычным текстом add, без слеша."
        )
        return

    # Import here to avoid a commands <-> bot module import cycle.
    from bot import process_purchase_message

    await process_purchase_message(message.reply_to_message, response_message=message)


@router.message(Command("list"))
async def send_purchases_list(message: Message) -> None:
    """Export all purchases to an Excel workbook and send it to this chat."""
    headers = (
        "Номер на ЕИС",
        "Наименование",
        "Начало подачи заявок",
        "Окончание подачи заявок",
        "Порядок подачи заявок",
        "Одобрено",
        "Исполнитель",
    )
    try:
        with sqlite3.connect(DB_PATH, timeout=30) as connection:
            rows = connection.execute(
                """SELECT purchase_number, description, start_date, end_date,
                          submission_procedure, is_approved, executor_name
                   FROM purchases
                   ORDER BY purchase_number"""
            ).fetchall()
    except sqlite3.Error:
        await message.answer("Не удалось прочитать список закупок из базы данных.")
        return

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Закупки"
    sheet.append(headers)
    for row in rows:
        values = list(row)
        values[5] = "Да" if values[5] else "Нет"
        sheet.append(values)
    for column in sheet.columns:
        column_letter = column[0].column_letter
        content_width = max(
            len(str(cell.value)) if cell.value is not None else 0
            for cell in column
        )
        sheet.column_dimensions[column_letter].width = min(content_width + 2, 60)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    output = BytesIO()
    workbook.save(output)
    document = BufferedInputFile(output.getvalue(), filename="purchases.xlsx")
    await message.answer_document(
        document,
        caption=f"Список закупок: {len(rows)} записей.",
    )


@router.message(Command("status"))
async def send_purchase_status(
    message: Message,
    command: CommandObject,
) -> None:
    """Find a purchase by number and report its fields in the chat."""
    purchase_number = (command.args or "").strip()
    if not purchase_number and message.reply_to_message is not None:
        replied_text = (
            message.reply_to_message.text or message.reply_to_message.caption or ""
        )
        match = re.search(r"=(\S+)", replied_text)
        if match:
            purchase_number = match.group(1)

    if not purchase_number:
        await message.answer(
            "Укажите номер закупки: /status <номер>, либо ответьте /status "
            "на сообщение, содержащее знак = перед номером."
        )
        return

    try:
        with sqlite3.connect(DB_PATH, timeout=30) as connection:
            row = connection.execute(
                """SELECT purchase_number, description, start_date, end_date,
                          submission_procedure, is_approved, executor_name
                   FROM purchases WHERE purchase_number = ?""",
                (purchase_number,),
            ).fetchone()
    except sqlite3.Error:
        await message.answer("Не удалось прочитать закупку из базы данных.")
        return

    if row is None:
        await message.answer(f"Закупка {purchase_number} не найдена.")
        return

    labels = (
        "Номер закупки",
        "Описание",
        "Начало подачи заявок",
        "Окончание подачи заявок",
        "Порядок подачи заявок",
        "Одобрено",
        "Исполнитель",
    )
    values = list(row)
    values[5] = "Да" if values[5] else "Нет"
    lines = [
        f"{label}: {value if value is not None else '—'}"
        for label, value in zip(labels, values)
    ]
    await message.answer("\n".join(lines))


@router.message(Command("exclude"))
async def exclude_purchase(
    message: Message,
    command: CommandObject,
) -> None:
    """Delete a purchase found by its number."""
    purchase_number = (command.args or "").strip()
    if not purchase_number and message.reply_to_message is not None:
        replied_text = (
            message.reply_to_message.text or message.reply_to_message.caption or ""
        )
        match = re.search(r"=(\S+)", replied_text)
        if match:
            purchase_number = match.group(1)

    if not purchase_number:
        await message.answer(
            "Укажите номер закупки: /exclude номер, либо ответьте /exclude "
            "на сообщение, содержащее знак = перед номером."
        )
        return

    try:
        with sqlite3.connect(DB_PATH, timeout=30) as connection:
            cursor = connection.execute(
                "DELETE FROM purchases WHERE purchase_number = ?",
                (purchase_number,),
            )
    except sqlite3.Error:
        await message.answer("Не удалось удалить закупку из базы данных.")
        return

    if cursor.rowcount:
        await message.answer(f"Закупка {purchase_number} удалена.")
    else:
        await message.answer(f"Закупка {purchase_number} не найдена.")
