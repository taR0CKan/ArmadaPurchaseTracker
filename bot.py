"""Telegram bot that imports zakupki.gov.ru links from chat messages."""

import asyncio
import logging
import os
import re
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, MessageReactionUpdated, ReactionTypeEmoji
from requests import RequestException

from DB_tasks.add_purchase import add_purchase, update_message_reaction
from commands import router as commands_router
from fetch_zakupki_page import fetch_purchase
from reminders import (
    check_and_send_reminders,
    reminder_chat_id,
    reminders_enabled,
    run_daily_reminders,
)

from dotenv import load_dotenv

URL_PATTERN = re.compile(r"https?://(?:www\.)?zakupki\.gov\.ru/[^\s<>\]\[(){}]+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,!?;:»)]}"

dispatcher = Dispatcher()
dispatcher.include_router(commands_router)
messages_router = Router()
dispatcher.include_router(messages_router)


def extract_link_and_description(message_text: str) -> tuple[str, str] | None:
    """Return the first zakupki.gov.ru URL and surrounding message text."""
    match = URL_PATTERN.search(message_text)
    if not match:
        return None

    url = match.group(0).rstrip(TRAILING_PUNCTUATION)
    if not url:
        return None

    # Put punctuation stripped from the URL back into the description.
    end = match.start() + len(url)
    description = f"{message_text[:match.start()]} {message_text[end:]}"
    description = " ".join(description.split()).strip()
    return url, description


async def process_purchase_message(
    message: Message,
    response_message: Message | None = None,
) -> None:
    """Parse and save a purchase link from a message, reporting on a chosen message."""
    text = message.text or message.caption
    if not text:
        if response_message is not None:
            await response_message.answer("В сообщении нет текста или подписи со ссылкой на закупку.")
        return

    extracted = extract_link_and_description(text)
    if not extracted:
        if response_message is not None:
            await response_message.answer("В сообщении не найдена ссылка на zakupki.gov.ru.")
        return

    url, description = extracted
    fields = {"source_message": str(message.message_id)}
    try:
        _html, parsed_fields = await asyncio.to_thread(fetch_purchase, url, description)
        fields.update(parsed_fields)
        added = await asyncio.to_thread(add_purchase, fields)
    except (RequestException, OSError, sqlite3.Error, ValueError) as exc:
        logging.exception("Failed to process zakupki.gov.ru link")
        target = response_message or message
        await target.answer(f"Не удалось обработать закупку: {exc}")
        return

    number = fields.get("purchase_number") or "неизвестен"
    target = response_message or message
    if added:
        await target.answer(f"Закупка {number} сохранена в базу данных.")
        try:
            await check_and_send_reminders(message.bot)
        except Exception:
            logging.exception("Failed to check reminders for newly added purchase %s", number)
    else:
        await target.answer(f"Закупка {number} уже есть в базе данных.")


@messages_router.message()
async def process_message(message: Message) -> None:
    if (message.text or "").strip().casefold() == "add":
        if message.reply_to_message is None:
            await message.answer("Ответьте текстом add на сообщение со ссылкой на закупку.")
            return
        await process_purchase_message(
            message.reply_to_message,
            response_message=message,
        )
        return

    await process_purchase_message(message)





@dispatcher.message_reaction()
async def process_reaction(event: MessageReactionUpdated) -> None:
    """Track 👍 executor and configured user's 👌 approval reaction."""
    if event.user is None:
        return

    def emoji_set(reactions: list) -> set[str]:
        return {
            reaction.emoji
            for reaction in reactions
            if isinstance(reaction, ReactionTypeEmoji)
        }

    approver_raw = os.getenv("APPROVER_TELEGRAM_USER_ID")
    approver_id = int(approver_raw) if approver_raw else None
    try:
        changed = await asyncio.to_thread(
            update_message_reaction,
            event.message_id,
            event.user.id,
            emoji_set(event.old_reaction),
            emoji_set(event.new_reaction),
            approver_id,
            " ".join(
                part
                for part in (
                    event.user.full_name,
                    f"(@{event.user.username})" if event.user.username else None,
                )
                if part
            ),
        )
    except sqlite3.Error:
        logging.exception("Failed to save Telegram reaction")
        return
    if changed:
        logging.info("Updated reactions for Telegram message %s", event.message_id)


async def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Set TELEGRAM_BOT_TOKEN in the process environment or in the project .env file"
        )
    if reminders_enabled():
        reminder_chat_id()

    async with Bot(token=token) as bot:
        reminder_task = (
            asyncio.create_task(run_daily_reminders(bot))
            if reminders_enabled()
            else None
        )
        if reminder_task is None:
            logging.info("Purchase deadline reminders are disabled")
        try:
            await dispatcher.start_polling(
                bot,

                handle_as_tasks=False,
                drop_pending_updates=False,
            )
        finally:
            if reminder_task is not None:
                reminder_task.cancel()
                try:
                    await reminder_task
                except asyncio.CancelledError:
                    pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
