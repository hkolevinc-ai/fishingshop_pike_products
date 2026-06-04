#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub-ready scraper за fishingshop-pike.com.

Извлича:
- номер/код на продукт
- име на продукт
- категория
- описание
- URL на продукта
- всички URL-и на изображенията в отделни CSV колони: image_1, image_2, ...
- цена
- тегло
- наличност

Експорт: CSV и JSONL.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional
from urllib.parse import parse_qsl, urljoin, urlparse, urlunparse, urlencode

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://fishingshop-pike.com/"
PRODUCT_RE = re.compile(r"/product/\d+/.+\.html(?:\?.*)?$")
CATEGORY_RE = re.compile(r"/category/\d+/.+\.html(?:\?.*)?$")
PRICE_RE = re.compile(r"Цена:\s*(?:€\s*)?([\d.,]+).*?([\d.,]+)\s*лв", re.S | re.I)
CODE_RE = re.compile(r"Код:\s*([\w\-\.\/]+)", re.I)
WEIGHT_LABEL_RE = re.compile(r"(?:Тегло|Тегло на продукта|Weight)\s*:?\s*([0-9]+(?:[,.][0-9]+)?\s*(?:кг|kg|гр\.?|грама|g))", re.I)
WEIGHT_VALUE_RE = re.compile(r"(?<![\w/])([0-9]+(?:[,.][0-9]+)?\s*(?:кг|kg|гр\.?|грама|g))(?![\w/])", re.I)
IMAGE_EXT_RE = re.compile(r"\.(?:jpg|jpeg|png|webp)(?:\?.*)?$", re.I)

# Думи/пътища, които почти винаги са UI елементи, а не продуктови снимки.
NON_PRODUCT_IMAGE_MARKERS = (
    "/skins/",
    "/design/",
    "/icons/",
    "/flags/",
    "logo",
    "facebook",
    "twitter",
    "visa",
    "paypal",
    "mastercard",
    "speedy",
    "econt",
    "evrouput",
    "gdpr",
    "close_video",
)

PRODUCT_IMAGE_MARKERS = (
    "/productlargeimages/",
    "/productimages/",
    "/products/",
    "/product/",
    "/userfiles/product",
)


@dataclass
class Product:
    product_number: str = ""
    product_name: str = ""
    category: str = ""
    description: str = ""
    product_url: str = ""
    price_eur: str = ""
    price_bgn: str = ""
    weight: str = ""
    availability: str = ""
    image_urls: list[str] = field(default_factory=list)


class PikeScraper:
    def __init__(self, delay: float = 1.0, timeout: int = 25):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; PikeScraper/1.1; "
                    "+https://github.com/; respectful scraping)"
                ),
                "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.7",
            }
        )

    def get(self, url: str) -> BeautifulSoup:
        time.sleep(self.delay + random.uniform(0, max(self.delay / 2, 0.01)))
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return BeautifulSoup(response.text, "lxml")

    @staticmethod
    def clean(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def with_page(url: str, page: int) -> str:
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if page <= 1:
            query.pop("page", None)
        else:
            query["page"] = str(page)
        return urlunparse(parsed._replace(query=urlencode(query)))

    @staticmethod
    def _strip_fragment(url: str) -> str:
        return urlunparse(urlparse(url)._replace(fragment=""))

    @staticmethod
    def _same_host(url: str) -> bool:
        return urlparse(url).netloc.endswith("fishingshop-pike.com")

    @staticmethod
    def _has_next_page(soup: BeautifulSoup, current_page: int) -> bool:
        expected = f"page={current_page + 1}"
        return any(expected in a.get("href", "") for a in soup.select("a[href]"))

    def discover_category_urls(self, start_url: str = BASE_URL) -> list[str]:
        soup = self.get(start_url)
        urls: set[str] = set()
        for a in soup.select("a[href]"):
            href = urljoin(start_url, a.get("href", ""))
            if self._same_host(href) and CATEGORY_RE.search(urlparse(href).path):
                urls.add(self._strip_fragment(href))
        return sorted(urls)

    def collect_product_urls_from_category(
        self, category_url: str, max_pages: Optional[int] = None
    ) -> list[str]:
        product_urls: list[str] = []
        seen: set[str] = set()
        page = 1

        while True:
            page_url = self.with_page(category_url, page)
            soup = self.get(page_url)
            found_on_page = 0

            for a in soup.select("a[href]"):
                href = urljoin(page_url, a.get("href", ""))
                if self._same_host(href) and PRODUCT_RE.search(urlparse(href).path):
                    href = self._strip_fragment(href)
                    if href not in seen:
                        seen.add(href)
                        product_urls.append(href)
                        found_on_page += 1

            if found_on_page == 0 and page > 1:
                break
            if max_pages and page >= max_pages:
                break
            if not self._has_next_page(soup, page):
                break
            page += 1

        return product_urls

    def parse_product(self, url: str) -> Product:
        soup = self.get(url)
        text = self.clean(soup.get_text(" "))

        product = Product(product_url=url)
        product.product_name = self._extract_name(soup)
        product.product_number = self._extract_product_number(text)
        product.price_eur, product.price_bgn = self._extract_prices(text)
        product.weight = self._extract_weight(text, product.product_name)
        product.availability = self._extract_availability(text)
        product.category = self._extract_category(soup, product.product_name)
        product.description = self._extract_description(soup, text)
        product.image_urls = self._extract_image_urls(soup, url, product.product_name)

        return product

    def _extract_name(self, soup: BeautifulSoup) -> str:
        h1 = soup.find("h1")
        return self.clean(h1.get_text(" ")) if h1 else ""

    def _extract_product_number(self, text: str) -> str:
        match = CODE_RE.search(text)
        return match.group(1).strip() if match else ""

    def _extract_prices(self, text: str) -> tuple[str, str]:
        match = PRICE_RE.search(text)
        if not match:
            return "", ""
        return match.group(1).replace(",", "."), match.group(2).replace(",", ".")

    def _extract_weight(self, text: str, product_name: str) -> str:
        """
        Извлича тегло в отделна колона.

        Приоритет:
        1) явно поле от типа „Тегло: 70 гр“ / „Weight: 0.5 kg“;
        2) тегло, изписано в името на продукта, напр. „... 70 гр“;
        3) първа разумна стойност в описанието/текста.

        Забележка: при риболовни продукти „гр“ понякога е част от акция/размер
        в категорията или описанието. Затова първо се търси етикет или име на продукта.
        """
        label_match = WEIGHT_LABEL_RE.search(text)
        if label_match:
            return self.clean(label_match.group(1)).replace(",", ".")

        name_match = WEIGHT_VALUE_RE.search(product_name or "")
        if name_match:
            return self.clean(name_match.group(1)).replace(",", ".")

        # Fallback: търсим тегло близо до думи като „тежест“, „олово“, „тегло“.
        context_match = re.search(
            r"(?:тегло|тежест|олово|weight)[^.!?]{0,80}?([0-9]+(?:[,.][0-9]+)?\s*(?:кг|kg|гр\.?|грама|g))",
            text,
            re.I,
        )
        if context_match:
            return self.clean(context_match.group(1)).replace(",", ".")

        return ""

    def _extract_availability(self, text: str) -> str:
        if "В наличност" in text:
            return "В наличност"
        if any(marker in text for marker in ("Изчерпан", "Няма наличност", "Не е наличен")):
            return "Няма наличност"
        return ""

    def _extract_category(self, soup: BeautifulSoup, product_name: str) -> str:
        # На този SELITON сайт breadcrumb-ът е: Начало > Категория > Име на продукт.
        # Взимаме само линковете към категории от зоната преди H1.
        h1 = soup.find("h1")
        category_labels: list[str] = []

        if h1:
            for element in h1.find_all_previous("a", href=True):
                href = element.get("href", "")
                label = self.clean(element.get_text(" "))
                if label and "category/" in href:
                    category_labels.append(label)
            category_labels.reverse()

        if not category_labels:
            for a in soup.select("a[href*='/category/']"):
                label = self.clean(a.get_text(" "))
                if label and label != product_name:
                    category_labels.append(label)

        # Премахване на дублирания, запазвайки реда.
        seen: set[str] = set()
        unique = [x for x in category_labels if not (x in seen or seen.add(x))]
        return " > ".join(unique)

    def _extract_description(self, soup: BeautifulSoup, full_text: str) -> str:
        header = soup.find(string=re.compile(r"^\s*Описание\s*$", re.I))
        if header:
            parent = header.find_parent()
            # Често реалното описание е в следващ контейнер/таб след заглавието.
            candidates = []
            if parent:
                candidates.extend(parent.find_all_next(limit=8))
            for candidate in candidates:
                candidate_text = self.clean(candidate.get_text(" "))
                if (
                    candidate_text
                    and "Бързи връзки:" not in candidate_text
                    and candidate_text.lower() != "описание"
                    and len(candidate_text) > 30
                ):
                    return candidate_text

        # Fallback от целия текст: от "Описание" до footer-а.
        parts = full_text.split("Описание", 1)
        if len(parts) == 2:
            return parts[1].split("Бързи връзки:", 1)[0].strip()
        return ""

    def _extract_image_urls(self, soup: BeautifulSoup, product_url: str, product_name: str) -> list[str]:
        urls: list[str] = []

        def add(candidate: str) -> None:
            if not candidate:
                return
            # srcset: взимаме URL частта преди ширината, примерно "image.jpg 800w".
            candidate = candidate.strip().split(" ")[0]
            absolute = self._strip_fragment(urljoin(product_url, candidate))
            lowered = absolute.lower()

            if not IMAGE_EXT_RE.search(lowered):
                return
            if any(marker in lowered for marker in NON_PRODUCT_IMAGE_MARKERS):
                return

            # Приоритетно приемаме продуктови директории. Ако липсват, приемаме снимки,
            # чийто alt/title съвпада с продукта чрез проверката при img/link обхода.
            if absolute not in urls:
                urls.append(absolute)

        # 1) Големите продуктови снимки често са в <a href="/userfiles/productlargeimages/...">.
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            lowered = href.lower()
            if any(marker in lowered for marker in PRODUCT_IMAGE_MARKERS) or IMAGE_EXT_RE.search(lowered):
                add(href)

        # 2) Взимаме и img атрибути: src, data-src, data-original, data-large, data-zoom-image, srcset.
        for img in soup.select("img"):
            alt_title = self.clean(" ".join([img.get("alt", ""), img.get("title", "")])).lower()
            looks_like_product = (
                product_name and product_name[:25].lower() in alt_title
            ) or any(
                marker in " ".join(str(img.get(attr, "")).lower() for attr in img.attrs)
                for marker in PRODUCT_IMAGE_MARKERS
            )

            for attr in ("src", "data-src", "data-original", "data-large", "data-zoom-image"):
                value = img.get(attr)
                if value and looks_like_product:
                    add(value)

            srcset = img.get("srcset")
            if srcset and looks_like_product:
                for item in srcset.split(","):
                    add(item)

        # Поставяме големите изображения първи, после thumbnail-и/други.
        urls = sorted(
            urls,
            key=lambda u: (
                0 if "/productlargeimages/" in u.lower() else 1,
                u,
            ),
        )
        return urls

    def scrape(self, start_urls: Iterable[str], max_pages: Optional[int] = None) -> list[Product]:
        all_product_urls: list[str] = []
        seen: set[str] = set()

        for start_url in start_urls:
            if PRODUCT_RE.search(urlparse(start_url).path):
                urls = [start_url]
            else:
                urls = self.collect_product_urls_from_category(start_url, max_pages=max_pages)

            for product_url in urls:
                if product_url not in seen:
                    seen.add(product_url)
                    all_product_urls.append(product_url)

        products: list[Product] = []
        for index, product_url in enumerate(all_product_urls, 1):
            print(f"[{index}/{len(all_product_urls)}] {product_url}")
            try:
                products.append(self.parse_product(product_url))
            except Exception as exc:  # noqa: BLE001 - useful for long scraping runs
                print(f"  ! error: {exc}")
        return products


def product_to_csv_row(product: Product, max_images: int) -> dict[str, str]:
    row = {
        "product_number": product.product_number,
        "product_name": product.product_name,
        "category": product.category,
        "description": product.description,
        "product_url": product.product_url,
        "price_eur": product.price_eur,
        "price_bgn": product.price_bgn,
        "weight": product.weight,
        "availability": product.availability,
    }
    for index in range(1, max_images + 1):
        row[f"image_{index}"] = product.image_urls[index - 1] if index <= len(product.image_urls) else ""
    return row


def save_csv(products: list[Product], path: str) -> None:
    max_images = max((len(product.image_urls) for product in products), default=0)
    fields = [
        "product_number",
        "product_name",
        "category",
        "description",
        "product_url",
        "price_eur",
        "price_bgn",
        "weight",
        "availability",
    ] + [f"image_{index}" for index in range(1, max_images + 1)]

    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for product in products:
            writer.writerow(product_to_csv_row(product, max_images))


def save_jsonl(products: list[Product], path: str) -> None:
    with open(path, "w", encoding="utf-8") as file:
        for product in products:
            file.write(json.dumps(asdict(product), ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scraper за fishingshop-pike.com")
    parser.add_argument("--start", nargs="+", default=[BASE_URL], help="Категория или продуктов URL")
    parser.add_argument(
        "--discover-categories",
        action="store_true",
        help="Открий категориите от началната страница и обходи всяка категория",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="Максимум страници на категория. Увеличи за повече продукти.",
    )
    parser.add_argument("--delay", type=float, default=1.0, help="Пауза между requests")
    parser.add_argument("--csv", default="fishingshop_pike_products.csv")
    parser.add_argument("--jsonl", default="fishingshop_pike_products.jsonl")
    args = parser.parse_args()

    scraper = PikeScraper(delay=args.delay)

    if args.discover_categories:
        categories = scraper.discover_category_urls(BASE_URL)
        print(f"Found {len(categories)} categories")
        start_urls = categories
    else:
        start_urls = args.start

    products = scraper.scrape(start_urls, max_pages=args.max_pages)
    save_csv(products, args.csv)
    save_jsonl(products, args.jsonl)
    print(f"Saved {len(products)} products to {args.csv} and {args.jsonl}")


if __name__ == "__main__":
    main()
