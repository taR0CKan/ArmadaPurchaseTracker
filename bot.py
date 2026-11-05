"""Telegram bot that imports zakupki.gov.ru links from chat messages."""

import asyncio
import logging
import os
import re
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.types import Message, MessageReactionUpdated, ReactionTypeEmoji
from requests import RequestException

from DB_tasks.add_purchase import add_purchase, update_message_reaction
from fetch_zakupki_page import fetch_purchase

from dotenv import load_dotenv

URL_PATTERN = re.compile(r"https?://(?:www\.)?zakupki\.gov\.ru/[^\s<>\]\[(){}]+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,!?;:»)]}"

dispatcher = Dispatcher()


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


@dispatcher.message()
async def process_message(message: Message) -> None:
    text = message.text or message.caption
    if not text:
        return

    extracted = extract_link_and_description(text)
    if not extracted:
        return

    url, description = extracted
    fields = {"source_message": str(message.message_id)}
    try:
        _html, parsed_fields = await asyncio.to_thread(fetch_purchase, url, description)
        fields.update(parsed_fields)
        added = await asyncio.to_thread(add_purchase, fields)
    except (RequestException, OSError, sqlite3.Error, ValueError) as exc:
        logging.exception("Failed to process zakupki.gov.ru link")
        await message.reply(f"Не удалось обработать закупку: {exc}")
        return

    number = fields.get("purchase_number") or "неизвестен"
    if added:
        await message.reply(f"Закупка {number} сохранена в базу данных.")
    else:
        await message.reply(f"Закупка {number} уже есть в базе данных.")


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

    async with Bot(token=token) as bot:
        await dispatcher.start_polling(
            bot,
            allowed_updates=["message", "message_reaction"],
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
