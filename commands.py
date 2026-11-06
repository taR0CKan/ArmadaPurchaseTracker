"""Telegram bot commands."""

import os
import re
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message


router = Router()
ENV_PATH = Path(__file__).with_name(".env")


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
