"""Fetch a purchase card and extract its required fields."""


import sqlite3
import sys

import requests
from bs4 import BeautifulSoup
from DB_tasks.add_purchase import add_purchase

from certs import certificate_prep
from data_preprocessing import normalize_datetime, normalize_price





FIELDS = {
    "Дата начала срока подачи заявок": "start_date",
    "Дата и время окончания срока подачи заявок (по местному времени заказчика)": "end_date",
    "Порядок подачи заявок": "submission_procedure",
    "Начальная цена": "initial_price",
}





def extract_fields(html: str) -> dict[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    result = {
        "purchase_number": None,
        "description": None,
        **{key: None for key in FIELDS.values()},
    }

    number = soup.select_one(".registry-entry__header-mid__number a")
    if number:
        result["purchase_number"] = number.get_text(" ", strip=True).removeprefix("№").strip()

    for block in soup.select(".registry-entry__body-block"):
        title = block.select_one(".registry-entry__body-title")
        if title and title.get_text(" ", strip=True) == "Объект закупки":
            description = block.select_one(".registry-entry__body-value")
            if description:
                result["description"] = description.get_text(" ", strip=True) or None
            break

    # The three procedure fields are represented by title/value pairs.
    for title in soup.select(".common-text__title"):
        label = title.get_text(" ", strip=True)
        key = FIELDS.get(label)
        if key:
            value = title.find_next_sibling(class_="common-text__value")
            if value:
                text = value.get_text(" ", strip=True).replace("(МСК)", "").strip()
                if key in {"start_date", "end_date"}:
                    result[key] = normalize_datetime(text)
                else:
                    result[key] = text or None

    # Initial price has its own price block on this page.
    price_title = soup.select_one(".price-block__title")
    if price_title and price_title.get_text(" ", strip=True) == "Начальная цена":
        price = price_title.find_next(class_="price-block__value")
        if price:
            result["initial_price"] = normalize_price(price.get_text(" ", strip=True))

    return result


def fetch_purchase(url: str) -> tuple[str, dict[str, str | None]]:
    """Fetch a card URL and extract its purchase fields."""
    ca_bundle = certificate_prep.prepare_ca_bundle()
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; PurchasePageCheck/1.0)"},
        timeout=30,
        verify=str(ca_bundle),
    )
    response.raise_for_status()

    # requests normally detects the encoding; fall back to UTF-8 if the
    # server omitted it so Cyrillic text remains readable.
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"

    fields = extract_fields(response.text)
    fields["purchase_URL"] = url
    return response.text, fields


def get_purchase_data(url: str) -> dict[str, str | None]:
    """Return the extracted purchase data for use by other scripts."""
    _html, fields = fetch_purchase(url)
    return fields


def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: python fetch_zakupki_page.py "<page_url>"')
        return 2

    page_url = sys.argv[1]


    try:
        html, fields = fetch_purchase(page_url)
    except (requests.RequestException, OSError) as exc:
        print(f"Request failed: {exc}")
        return 1



    soup = BeautifulSoup(html, "html.parser")
    print(soup.title.get_text(" ", strip=True) if soup.title else "(no title)")
    print("\nИзвлечённые поля:")
    for key, value in fields.items():
        print(f"{key}: {value or '(не найдено)'}")

    try:
        added = add_purchase(fields)
    except (sqlite3.Error, ValueError) as exc:
        print(f"Database save failed: {exc}")
        return 1
    if added:
        print(f"Запись {fields['purchase_number']} добавлена в БД.")
    else:
        print(f"Запись {fields['purchase_number']} уже есть в БД; изменений нет.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
