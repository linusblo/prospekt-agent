from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from .base import SupermarketAdapter
from ..models.offer import Offer, Supermarket
from ..models.trinkgut_description_parser import TrinkgutDescriptionParser

log = logging.getLogger(__name__)

_BASE_URL = "https://www.trinkgut.de"
_OFFERS_URL = f"{_BASE_URL}/angebote"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class TrinkgutAdapter(SupermarketAdapter):
    def __init__(self, html_file: str | None = None) -> None:
        self._desc_parser = TrinkgutDescriptionParser()
        self._html_file   = html_file

    @property
    def source_name(self) -> str:
        return Supermarket.TRINKGUT.value

    def fetch_offers(self) -> list[Offer]:
        html = self._fetch_html()
        offers = self._parse_offers(html)
        log.info("Trinkgut: %d Angebote gefunden", len(offers))
        return offers

    def _fetch_html(self) -> str:
        if self._html_file:
            log.info("Trinkgut: Lade HTML aus Datei %s", self._html_file)
            return Path(self._html_file).read_text(encoding="utf-8")
        log.info("Trinkgut: Lade %s", _OFFERS_URL)
        resp = requests.get(_OFFERS_URL, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.text

    def _parse_offers(self, html: str) -> list[Offer]:
        soup = BeautifulSoup(html, "lxml")
        containers = soup.select("div.product-box.box-boxed")

        if not containers:
            log.warning(
                "Trinkgut: Keine Produkt-Container (.product-box.box-boxed) gefunden. "
                "Möglicherweise hat sich die Seitenstruktur geändert."
            )
            return []

        now = datetime.now(timezone.utc)
        offers: list[Offer] = []
        for box in containers:
            try:
                offer = self._map_to_offer(box, now)
                if offer:
                    offers.append(offer)
            except Exception:
                log.debug("Trinkgut: Box übersprungen", exc_info=True)
        return offers

    def _map_to_offer(self, box: Tag, scraped_at: datetime) -> Offer | None:
        # Name
        name_tag = box.select_one(".product-name")
        name = name_tag.get_text(strip=True) if name_tag else ""
        if not name:
            return None

        # Preis
        price_tag = box.select_one(".product-price")
        sale_price = _parse_price(price_tag) if price_tag else None
        if sale_price is None:
            log.debug("Trinkgut: Kein Preis für %r – übersprungen", name)
            return None

        # Bild + Link
        img_tag  = box.select_one(".product-image-wrapper img")
        link_tag = box.select_one(".product-image-wrapper a")

        image_url = None
        if img_tag:
            src = img_tag.get("src") or img_tag.get("data-src") or ""
            image_url = _absolute_url(src)

        href = (link_tag.get("href") or "") if link_tag else ""
        product_slug = href.strip("/").replace("/", "-") or re.sub(r"[^\w-]", "-", name.lower())

        # Beschreibung
        desc_tag = box.select_one(".product-description")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # Beschreibung parsen → Größe + Basispreis
        parsed = self._desc_parser.parse(description)

        return Offer(
            source          = Supermarket.TRINKGUT,
            product_slug    = product_slug,
            name            = name,
            brand           = _extract_brand(name),
            short_description = description or None,
            sale_price      = sale_price,
            base_price_value = parsed.base_price_value,
            base_price_unit  = parsed.base_price_unit,
            sales_unit_raw   = parsed.sales_unit_raw,
            category_ids     = ["Angebote"],
            image_url        = image_url,
            scraped_at       = scraped_at,
        )


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _parse_price(price_tag: Tag) -> float | None:
    """
    Parst <p class="product-price">3.<sup>99</sup></p> → 3.99.
    Behandelt auch "5.-" (ganzzahlig) und Whitespace.
    """
    raw = re.sub(r"\s+", "", price_tag.get_text())
    # "3.99", "3,99", "3.-", "5.–" usw.
    m = re.search(r"(\d+)[.,](\d{2}|[-–])", raw)
    if m:
        euros = m.group(1)
        cents = m.group(2)
        if cents in ("-", "–"):
            cents = "00"
        try:
            return float(f"{euros}.{cents}")
        except ValueError:
            pass
    # Fallback: ganze Zahl
    m = re.search(r"(\d+)", raw)
    if m:
        return float(m.group(1))
    return None


def _extract_brand(name: str) -> str | None:
    """
    Leitet die Marke aus dem Produktnamen ab.

    Regel:
    - Erstes Wort → Marke (UPPERCASE)
    - Ausnahmen (zwei Wörter als Marke):
        * Erstes Wort < 3 Zeichen (z.B. "AK Racer" → "AK RACER")
        * Erstes Wort endet auf "." (Abkürzung, z.B. "Dr. Oetker" → "DR. OETKER")
    """
    if not name:
        return None
    words = name.split()
    if not words:
        return None
    first = words[0]
    take_two = len(words) > 1 and (len(first) < 3 or first.endswith("."))
    brand = (f"{first} {words[1]}" if take_two else first).upper().strip()
    return brand or None


def _absolute_url(url: str) -> str | None:
    if not url:
        return None
    if url.startswith("http"):
        return url
    return urljoin(_BASE_URL, url)
