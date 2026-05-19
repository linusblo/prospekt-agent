"""
Combi-Adapter — parst paginierte Filialangebote von www.combi.de.

URL-Muster:  https://www.combi.de/alle_angebote_{store_id}.html?page={n}
Beispiel:    https://www.combi.de/alle_angebote_220012809.html?page=1

HTML-Struktur pro Produktkarte (.product-card__description):
  - .product-card__name__link         → Name + href (→ SKU)
  - .product-card__weight             → Größe / Einheit
  - .product-card__price--current strong → aktueller Preis (DE-Format)
  - .product-card__price--old strong  → alter Preis (optional)
  - .product-card__bulk-price         → Grundpreis "3,00 €/1 l"
  - .product-card__deposit            → Pfand (optional)
  - .product-card__photo              → Bild-URL
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import requests
from bs4 import BeautifulSoup

from .base import SupermarketAdapter
from ..models.offer import Offer, Supermarket
from ..models.sales_unit_parser import SalesUnitParser
from src.utils.brand_resolver import resolve_brand

log = logging.getLogger(__name__)

_BASE_URL   = "https://www.combi.de"
_PAGE_URL   = f"{_BASE_URL}/alle_angebote_{{store_id}}.html?page={{page}}"
_PAGE_DELAY = 0.5   # Sekunden Pause zwischen Seiten-Requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9",
}

_UNIT_NORM: dict[str, str] = {
    "l": "L", "liter": "L",
    "ml": "ml", "cl": "cl",
    "kg": "kg",
    "g": "g", "gr": "g",
    "stk": "Stk",
}


class CombiAdapter(SupermarketAdapter):
    """
    Adapter für Combi-Filialangebote (paginiert).

    Beispiel:
        CombiAdapter("220012809")                        # per Store-ID
        CombiAdapter("220012809", html_file="test.html") # Offline / Tests
    """

    def __init__(self, store_id: str, html_file: str | None = None) -> None:
        self._store_id  = store_id
        self._html_file = html_file
        self._su_parser = SalesUnitParser()

    @property
    def source_name(self) -> str:
        return Supermarket.COMBI.value

    # Stubs für die abstrakte Basisklasse (Combi nutzt eigene Paginierungslogik)
    def _fetch_html(self) -> str:            # pragma: no cover
        raise NotImplementedError("Combi nutzt paginierte fetch_offers()")

    def _parse_offers(self, html: str) -> list[Offer]:   # pragma: no cover
        raise NotImplementedError("Combi nutzt _parse_page()")

    # ------------------------------------------------------------------

    def fetch_offers(self) -> list[Offer]:
        now       = datetime.now(timezone.utc)
        seen_skus: set[str] = set()
        offers:    list[Offer] = []

        if self._html_file:
            # Offline-Modus: eine HTML-Datei, nur eine Seite
            log.info("Combi: Lade HTML aus Datei %s", self._html_file)
            html = Path(self._html_file).read_text(encoding="utf-8")
            soup = BeautifulSoup(html, "lxml")
            offers.extend(self._parse_page(soup, now, seen_skus))
        else:
            # Online-Modus: paginierte Seiten laden
            total_pages: int | None = None
            page = 1
            while True:
                url = _PAGE_URL.format(store_id=self._store_id, page=page)
                log.info("Combi: Lade Seite %d (von %s) …", page,
                         total_pages if total_pages else "?")
                resp = requests.get(url, headers=_HEADERS,
                                    allow_redirects=True, timeout=30)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")

                if total_pages is None:
                    total_pages = _get_total_pages(soup)
                    log.info("Combi: %d Seiten erkannt", total_pages)

                page_offers = list(self._parse_page(soup, now, seen_skus))
                if not page_offers:
                    log.info("Combi: Seite %d leer → stoppe", page)
                    break
                offers.extend(page_offers)

                if page >= total_pages:
                    break
                page += 1
                time.sleep(_PAGE_DELAY)

        log.info("Combi: %d Angebote gefunden", len(offers))
        return offers

    def _parse_page(
        self,
        soup: BeautifulSoup,
        scraped_at: datetime,
        seen_skus: set[str],
    ) -> Iterator[Offer]:
        """Parst alle Produktkarten einer Seite und gibt Offer-Objekte zurück."""
        for card in soup.select(".product-card__description"):
            try:
                offer = self._parse_card(card, scraped_at)
                if offer is None:
                    continue
                if offer.product_slug in seen_skus:
                    log.debug("Combi: Duplikat SKU %s übersprungen",
                              offer.product_slug)
                    continue
                seen_skus.add(offer.product_slug)
                yield offer
            except Exception:
                log.debug("Combi: Produktkarte übersprungen", exc_info=True)

    def _parse_card(self, card, scraped_at: datetime) -> Offer | None:
        # ── Name ──────────────────────────────────────────────────────
        name_tag = card.select_one(".product-card__name__link")
        if not name_tag:
            return None
        name = name_tag.get_text(strip=True)
        if not name:
            return None

        # ── SKU aus href ──────────────────────────────────────────────
        href = name_tag.get("href") or ""
        if not href:
            poster = card.select_one(".product-card__poster__link")
            href   = poster.get("href") or "" if poster else ""
        if not href:
            img = card.select_one(".product-card__photo")
            href = img.get("src") or "" if img else ""

        sku = _extract_sku(href)
        if not sku:
            log.debug("Combi: Kein SKU für %r – übersprungen", name)
            return None

        # ── Aktueller Preis ───────────────────────────────────────────
        price_tag = card.select_one(".product-card__price--current strong")
        if not price_tag:
            return None
        sale_price = _parse_de_price(price_tag.get_text(strip=True))
        if sale_price is None:
            return None

        # ── Alter Preis + Rabatt (optional) ──────────────────────────
        original_price   = None
        discount_percent = None
        old_tag = card.select_one(".product-card__price--old strong")
        if old_tag:
            original_price = _parse_de_price(old_tag.get_text(strip=True))
            if original_price and original_price > sale_price:
                discount_percent = round(
                    (original_price - sale_price) / original_price * 100, 1
                )

        # ── Grundpreis ────────────────────────────────────────────────
        bp_value, bp_unit = None, None
        bulk_tag = card.select_one(".product-card__bulk-price")
        if bulk_tag:
            bp_value, bp_unit = _parse_base_price(bulk_tag.get_text(strip=True))

        # ── Pfand ─────────────────────────────────────────────────────
        deposit_value = None
        is_deposit    = False
        deposit_tag = card.select_one(".product-card__deposit")
        if deposit_tag:
            deposit_value, is_deposit = _parse_deposit(
                deposit_tag.get_text(strip=True)
            )

        # ── Größe / Sales Unit ────────────────────────────────────────
        weight_tag = card.select_one(".product-card__weight")
        su_raw = weight_tag.get_text(strip=True) if weight_tag else None
        su     = self._su_parser.parse(su_raw) if su_raw else None

        # ── Bild ──────────────────────────────────────────────────────
        image_url = None
        img = card.select_one(".product-card__photo")
        if img:
            image_url = img.get("src") or None

        return Offer(
            source               = Supermarket.COMBI,
            product_slug         = sku,
            name                 = name,
            brand                = resolve_brand(name),
            short_description    = None,
            long_description     = None,
            sale_price           = sale_price,
            original_price       = original_price,
            discount_percent     = discount_percent,
            base_price_value     = bp_value,
            base_price_value_max = None,
            base_price_unit      = bp_unit,
            base_price_has_prefix = False,
            card_price               = None,
            card_base_price_value    = None,
            card_base_price_value_max= None,
            card_base_price_unit     = None,
            card_discount_percent    = None,
            sales_unit_raw  = su_raw,
            sales_unit      = su,
            is_deposit_product = is_deposit,
            deposit_value   = deposit_value,
            valid_from      = None,
            valid_until     = None,
            image_url       = image_url,
            category_ids    = ["Angebote"],
            scraped_at      = scraped_at,
        )


# ---------------------------------------------------------------------------
# Testbare Parsing-Hilfsfunktionen (Modul-Level)
# ---------------------------------------------------------------------------

def _parse_de_price(text: str) -> float | None:
    """
    Parst deutsches Preisformat '0,99 €' oder '12,14 €' → float.
    Gibt None zurück wenn nicht parsierbar.
    """
    cleaned = (
        text
        .replace("€", "")
        .replace("\xa0", "")  # non-breaking space
        .replace(",", ".")
        .strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_base_price(text: str) -> tuple[float | None, str | None]:
    """
    Parst '3,00 €/1 l' oder '13,96 €/1 kg' → (value, normalized_unit).
    """
    m = re.search(
        r"([\d,]+)\s*€\s*/\s*\d+\s*(l|kg|g|ml|cl)",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None, None
    value = float(m.group(1).replace(",", "."))
    unit  = _UNIT_NORM.get(m.group(2).lower(), m.group(2))
    return value, unit


def _parse_deposit(text: str) -> tuple[float | None, bool]:
    """
    Parst '(+ Pfand 0,25 €)' → (0.25, True).
    Gibt (None, False) zurück wenn kein Pfand vorhanden.
    """
    m = re.search(r"Pfand\s+([\d,]+)\s*€", text)
    if not m:
        return None, False
    return float(m.group(1).replace(",", ".")), True


def _extract_sku(url: str) -> str | None:
    """
    Extrahiert SKU (letzte Zahl vor .html) aus URL.
    "/coca-cola_..._4504050019.html" → "4504050019"
    """
    m = re.search(r"_(\d+)\.html", url)
    return m.group(1) if m else None


def _get_total_pages(soup: BeautifulSoup) -> int:
    """
    Extrahiert Gesamtseitenanzahl aus "Seite X von Y" auf der Seite.
    Fallback: 1.
    """
    for text_node in soup.find_all(string=re.compile(r"Seite\s+\d+\s+von\s+\d+")):
        m = re.search(r"Seite\s+\d+\s+von\s+(\d+)", text_node)
        if m:
            return int(m.group(1))
    # Fallback: Paginierungs-Links durchsuchen
    for a in soup.select(".pagination a, .pager a"):
        try:
            num = int(a.get_text(strip=True))
        except ValueError:
            continue
        # Zählt den höchsten Paginierungs-Link als Gesamtseitenanzahl
        return num   # Vereinfachung: nimm ersten gefundenen Zahlenwert
    return 1
