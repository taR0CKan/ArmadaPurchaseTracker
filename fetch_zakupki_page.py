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
    result = {"purchase_number": None, **{key: None for key in FIELDS.values()}}

    number = soup.select_one(".registry-entry__header-mid__number a")
    if number:
        result["purchase_number"] = number.get_text(" ", strip=True).removeprefix("№").strip()

    # The three procedure fields are represented by title/value pairs.
    for title in soup.select(".common-text__title"):
        label = title.get_text(" ", strip=True)
        key = FIELDS.get(label)
        if key:
            value = title.find_next_sibling(class_="common-text__value")
            if value:
                text = value.get_text(" ", strip=True).replace("(МСК)", "").strip()
                result[key] = normalize_datetime(text)

    # Initial price has its own price block on this page.
    price_title = soup.select_one(".price-block__title")
    if price_title and price_title.get_text(" ", strip=True) == "Начальная цена":
        price = price_title.find_next(class_="price-block__value")
        if price:
            result["initial_price"] = normalize_price(price.get_text(" ", strip=True))

    return result


def fetch_purchase(url: str, text_parameter: str) -> tuple[str, dict[str, str | None]]:
    """Fetch a card URL, extract fields, and attach the supplied description."""
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
    fields["description"] = text_parameter
    fields["purchase_URL"] = url
    return response.text, fields


def get_purchase_data(url: str, text_parameter: str) -> dict[str, str | None]:
    """Return the extracted purchase data for use by other scripts."""
    _html, fields = fetch_purchase(url, text_parameter)
    return fields


def main() -> int:
    if len(sys.argv) != 3:
        print('Usage: python fetch_zakupki_page.py "<page_url>" "<text_parameter>"')
        return 2

    page_url, text_parameter = sys.argv[1:3]
    reg_number = page_url.split("regNumber=")[-1].split("&")[0] or "purchase"


    try:
        html, fields = fetch_purchase(page_url, text_parameter)
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
