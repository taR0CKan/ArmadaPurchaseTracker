"""Normalize dates and prices extracted from zakupki.gov.ru pages."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re


def normalize_datetime(value: str) -> str | None:
    """Extract only the date and optional time, dropping surrounding notes."""
    match = re.search(
        r"(?<!\d)(\d{1,2}\.\d{1,2}\.\d{4})"
        r"(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?",
        value,
    )
    if not match:
        return None

    date_text, time_text = match.groups()
    patterns = (
        ("%d.%m.%Y %H:%M:%S", f"{date_text} {time_text}") if time_text and time_text.count(":") == 2
        else ("%d.%m.%Y %H:%M", f"{date_text} {time_text}") if time_text
        else ("%d.%m.%Y", date_text)
    )
    try:
        return datetime.strptime(patterns[1], patterns[0]).isoformat(sep=" ")
    except ValueError:
        return None


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
