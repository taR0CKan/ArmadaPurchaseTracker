"""Send one-time purchase deadline reminders to the configured Telegram chat."""

import asyncio
import html
import logging
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from DB_tasks.create_database import ensure_reminders_table
from DB_tasks.reminder_store import load_reminder_data, mark_reminder_sent
from data_preprocessing import format_price, parse_date

REMINDER_TIMEZONE = os.getenv("REMINDER_TIMEZONE", "Asia/Novosibirsk")
DAILY_CHECK_TIME = time(9, 0)
_check_lock = asyncio.Lock()


def reminder_chat_id() -> int:
    """Return the configured common chat ID or fail with a useful message."""
    raw_chat_id = os.getenv("PURCHASE_CHAT_ID")
    if not raw_chat_id:
        raise RuntimeError("Set PURCHASE_CHAT_ID in the environment or project .env file")
    try:
        return int(raw_chat_id)
    except ValueError as exc:
        raise RuntimeError("PURCHASE_CHAT_ID must be an integer") from exc


def reminders_enabled() -> bool:
    """Return whether purchase deadline reminders are enabled by configuration."""
    return os.getenv("PURCHASE_REMINDERS_ENABLED", "true").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _threshold_lead_days(initial_price: int | None) -> int | None:
    if initial_price is None:
        return None
    if initial_price < 150_000_000_000:
        return 3
    if initial_price <= 300_000_000_000:
        return 4
    return 7


def _leads_for_status(status: str, initial_price: int | None) -> set[int]:
    """Resolve status-specific lead days, with existing price rules as defaults."""
    if status not in {"processing", "approved"}:
        return set()

    env_name = f"REMINDER_LEAD_DAYS_{status.upper()}"
    configured = os.getenv(env_name)
    if configured is not None:
        try:
            return {
                days
                for value in configured.split(",")
                if value.strip()
                for days in [int(value.strip())]
                if days > 0
            }
        except ValueError:
            logging.warning("Ignoring invalid %s value: %r", env_name, configured)

    leads = {1}
    price_lead = _threshold_lead_days(initial_price)
    if price_lead is not None:
        leads.add(price_lead)
    return leads


def _message(row: tuple, lead_days: int) -> str:
    number, description, end_date_raw, initial_price, executor, executor_name, purchase_url, status = row
    end_date = parse_date(end_date_raw)
    due = end_date.strftime("%d.%m.%Y") if end_date else html.escape(str(end_date_raw))
    executor_text = "не назначен"
    if executor:
        executor_id = str(executor)
        if executor_id.isdigit():
            visible_name = html.escape(executor_name or f"Telegram ID {executor_id}")
            executor_text = f'<a href="tg://user?id={executor_id}">{visible_name}</a>'
        else:
            executor_text = html.escape(executor_id)
    link = html.escape(str(purchase_url), quote=True) if purchase_url else ""
    url_line = f'\n<a href="{link}">Открыть закупку</a>' if link else ""
    description_text = html.escape(str(description)) if description else "не указано"
    if lead_days == 1:
        reminder_label = "до окончания срока остался 1 день"
    else:
        reminder_label = f"напоминание за {lead_days} дн. до окончания срока"
    text = (
        f"⏰ <b>{reminder_label}</b>\n"
        f"Закупка: <code>{html.escape(str(number))}</code>\n"
        f"Описание: {description_text}\n"
        f"Дедлайн: <b>{due}</b>\n"
        f"Стоимость: {html.escape(format_price(initial_price))}"
    )
    if status == "processing":
        text += f"\nОтветственный: {executor_text}"
    return text + url_line


async def check_and_send_reminders(bot: Bot) -> None:
    """Send due one-time reminders, including the universal one-day reminder."""
    if not reminders_enabled():
        return
    async with _check_lock:
        chat_id = reminder_chat_id()
        today = datetime.now(ZoneInfo(REMINDER_TIMEZONE)).date()
        ensure_reminders_table()
        purchases, sent = load_reminder_data()

        for row in purchases:
            number, _description, end_date_raw, initial_price, _executor, _executor_name, _url, status = row
            end_date = parse_date(end_date_raw)
            if end_date is None or today > end_date:
                continue

            leads = _leads_for_status(status, initial_price)

            for lead_days in sorted(leads):
                if (number, status, lead_days) in sent or today < end_date - timedelta(days=lead_days):
                    continue
                # If a later reminder is already due, it supersedes any older
                # reminder whose trigger date was missed (for example, send
                # the one-day reminder instead of both one-day and three-day).
                if any(
                    today >= end_date - timedelta(days=closer_lead)
                    for closer_lead in leads
                    if closer_lead < lead_days
                ):
                    continue
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=_message(row, lead_days),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception:
                    logging.exception(
                        "Failed to send %s-day reminder for purchase %s",
                        lead_days,
                        number,
                    )
                    continue

                sent_at = datetime.now(ZoneInfo(REMINDER_TIMEZONE))
                mark_reminder_sent(number, status, lead_days, sent_at)
                sent.add((number, status, lead_days))


async def run_daily_reminders(bot: Bot) -> None:
    """Check once at startup, then every day at 09:00 in the configured timezone."""
    timezone = ZoneInfo(REMINDER_TIMEZONE)
    while True:
        try:
            await check_and_send_reminders(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Daily purchase reminder check failed")

        now = datetime.now(timezone)
        next_check = datetime.combine(now.date(), DAILY_CHECK_TIME, tzinfo=timezone)
        if next_check <= now:
            next_check += timedelta(days=1)
        await asyncio.sleep((next_check - now).total_seconds())
