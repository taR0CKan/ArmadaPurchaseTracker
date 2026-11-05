"""Normalize dates and prices extracted from zakupki.gov.ru pages."""

from datetime import datetime
from decimal import Decimal, InvalidOperation


def normalize_datetime(value: str) -> str | None:
    """Convert Russian date/time text to SQLite-friendly ISO format."""
    value = " ".join(value.replace("(МСК)", "").split())
    for pattern in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, pattern).isoformat(sep=" ")
        except ValueError:
            pass
    return value or None


def normalize_price(value: str) -> int | None:
    """Convert a formatted Russian price to an integer number of kopecks."""
    cleaned = value.replace("\xa0", "").replace("\u202f", "")
    cleaned = "".join(cleaned.split())
    cleaned = cleaned.replace("₽", "").replace("руб.", "").replace("руб", "")
    cleaned = cleaned.strip().replace(",", ".")
    try:
        return int(Decimal(cleaned) * 100)
    except InvalidOperation:
        return None
