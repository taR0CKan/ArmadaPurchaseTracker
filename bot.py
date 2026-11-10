"""Telegram bot that imports zakupki.gov.ru links from chat messages."""

import asyncio
import logging
import os
import re
import sqlite3


from aiogram import Router
from aiogram.types import (
    Message,
    MessageReactionUpdated,
    ReactionTypeEmoji,
)
from requests import RequestException

from DB_tasks.add_purchase import add_purchase, update_message_reaction

from fetch_zakupki_page import fetch_purchase
from reminders import (
    check_and_send_reminders,
)



URL_PATTERN = re.compile(r"https?://(?:www\.)?zakupki\.gov\.ru/[^\s<>\]\[(){}]+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,!?;:»)]}"


messages_router = Router()

def extract_purchase_link(message_text: str) -> str | None:
    """Return the first zakupki.gov.ru URL found in a message."""
    match = URL_PATTERN.search(message_text)
    if not match:
        return None

    url = match.group(0).rstrip(TRAILING_PUNCTUATION)
    if not url:
        return None

    return url


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

    url = extract_purchase_link(text)
    if not url:
        if response_message is not None:
            await response_message.answer("В сообщении не найдена ссылка на zakupki.gov.ru.")
        return

    fields = {"source_message": str(message.message_id)}
    try:
        _html, parsed_fields = await asyncio.to_thread(fetch_purchase, url)
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





@messages_router.message_reaction()
async def process_reaction(event: MessageReactionUpdated) -> None:
    """Track 👍 executor and configured user's 👌 approval reaction."""
    logging.info("Reaction update received: message_id=%s", event.message_id)
    if event.user is None:
        logging.warning(
            "Ignoring reaction update for message_id=%s: Telegram did not provide actor user",
            event.message_id,
        )
        return

    def emoji_set(reactions: list) -> set[str]:
        return {
            reaction.emoji
            for reaction in reactions
            if isinstance(reaction, ReactionTypeEmoji)
        }

    approver_raw = os.getenv("APPROVER_TELEGRAM_USER_ID")
    try:
        approver_id = int(approver_raw) if approver_raw else None

    except ValueError:
        logging.exception("APPROVER_TELEGRAM_USER_ID must be an integer; raw=%r", approver_raw)
        return
    old_emojis = emoji_set(event.old_reaction)
    new_emojis = emoji_set(event.new_reaction)
    try:
        changed = await asyncio.to_thread(
            update_message_reaction,
            event.message_id,
            event.user.id,
            old_emojis,
            new_emojis,
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
        logging.exception(
            "Failed to save Telegram reaction: message_id=%s user_id=%s",
            event.message_id,
            event.user.id,
        )
        return
    if changed:
        try:
            await check_and_send_reminders(event.bot)
        except Exception:
            logging.exception(
                "Failed to check reminders after reaction update for message %s",
                event.message_id,
            )



