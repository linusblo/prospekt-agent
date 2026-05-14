from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .base import SupermarketAdapter
from ..models.offer import Offer, Supermarket
from ..models.sales_unit_parser import SalesUnitParser

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class AldiNordAdapter(SupermarketAdapter):
    URL = "https://www.aldi-nord.de/angebote.html"

    def __init__(self, html_file: str | None = None) -> None:
        """
        html_file: Optionaler Pfad zu einer lokal gespeicherten HTML-Datei
                   (nützlich für Offline-Tests ohne Netzwerkzugriff).
        """
        self._parser = SalesUnitParser()
        self._html_file = html_file

    @property
    def source_name(self) -> str:
        return Supermarket.ALDI_NORD.value

    def fetch_offers(self) -> list[Offer]:
        html = self._fetch_html()
        offers = self._parse_offers(html)
        log.info("AldiNord: %d Angebote gefunden", len(offers))
        return offers

    def _fetch_html(self) -> str:
        if self._html_file:
            log.info("AldiNord: Lade HTML aus Datei %s", self._html_file)
            return Path(self._html_file).read_text(encoding="utf-8")

        log.info("AldiNord: Lade %s", self.URL)
        response = requests.get(self.URL, headers=_HEADERS, timeout=30)
        response.raise_for_status()
        return response.text

    def _parse_offers(self, html: str) -> list[Offer]:
        soup = BeautifulSoup(html, "lxml")
        raw_products = self._extract_product_json(soup)

        if not raw_products:
            log.warning(
                "AldiNord: Keine Produktdaten im HTML gefunden. "
                "Möglicherweise hat sich die Seitenstruktur geändert."
            )
            return []

        now = datetime.now(timezone.utc)
        offers: list[Offer] = []
        for product in raw_products:
            try:
                offers.append(self._map_to_offer(product, now))
            except Exception:
                log.debug("Produkt übersprungen: %s", product.get("productSlug", "?"), exc_info=True)

        return offers

    def _extract_product_json(self, soup: BeautifulSoup) -> list[dict]:
        # Primär-Pfad: __NEXT_DATA__ → pageProps.apiData (JSON-String) → algoliaDataMap
        next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_data_tag and next_data_tag.string:
            try:
                outer = json.loads(next_data_tag.string)
                api_data_str = outer["props"]["pageProps"].get("apiData")
                if api_data_str:
                    api_data = json.loads(api_data_str)
                    # Struktur: list → [0] → [1] → res.algoliaDataMap (dict ID→Produkt)
                    algolia_map = api_data[0][1]["res"]["algoliaDataMap"]
                    products = list(algolia_map.values())
                    log.debug("AldiNord: %d Produkte via algoliaDataMap gefunden", len(products))
                    return products
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                log.debug("AldiNord: algoliaDataMap-Pfad fehlgeschlagen", exc_info=True)

        # Fallback: rekursive Suche in allen JSON-Script-Tags
        for script in soup.find_all("script", type="application/json"):
            content = script.string or ""
            if "productSlug" not in content:
                continue
            try:
                data = json.loads(content)
                products = _find_products_recursive(data)
                if products:
                    log.debug("AldiNord: Produkte via Fallback-Suche gefunden")
                    return products
            except json.JSONDecodeError:
                pass

        return []

    def _map_to_offer(self, product: dict, scraped_at: datetime) -> Offer:
        price_info = product.get("currentPrice") or {}

        sale_price = float(price_info.get("priceValue") or 0.0)

        strike = price_info.get("strikePrice") or {}
        original_price = strike.get("strikePriceValue")

        # Basispreis (Liter-/Kilo-Preis)
        base_prices = price_info.get("basePrice") or []
        base_price_value: float | None = None
        base_price_unit: str | None = None
        if base_prices:
            bp = base_prices[0]
            base_price_value = bp.get("basePriceValue")
            base_price_unit = bp.get("basePriceScale")

        # Verpackung
        sales_unit_raw: str = product.get("salesUnit") or ""
        sales_unit = self._parser.parse(sales_unit_raw) if sales_unit_raw else None

        # Hauptbild
        image_url: str | None = None
        for asset in product.get("assets") or []:
            if asset.get("type") == "primary":
                image_url = asset.get("url")
                break

        return Offer(
            source=Supermarket.ALDI_NORD,
            product_slug=product["productSlug"],
            name=product.get("name") or "",
            brand=_normalize_brand(product.get("brandName")),
            short_description=product.get("shortDescription") or None,
            long_description=product.get("longDescription") or None,
            sale_price=sale_price,
            original_price=float(original_price) if original_price is not None else None,
            base_price_value=float(base_price_value) if base_price_value is not None else None,
            base_price_unit=base_price_unit,
            sales_unit_raw=sales_unit_raw or None,
            sales_unit=sales_unit,
            is_deposit_product=bool(product.get("isDepositProduct", False)),
            deposit_value=float(product["depositValue"]) if product.get("depositValue") else None,
            valid_from=_parse_unix_s(price_info.get("validFrom")),
            valid_until=_parse_unix_s(price_info.get("validUntil")),
            image_url=image_url,
            category_ids=list(product.get("categoryIDs") or []),
            scraped_at=scraped_at,
        )


def _normalize_brand(raw: str | None) -> str | None:
    """Strip + typografische Apostrophe normalisieren, damit TRADER JOE'S == TRADER JOE'S."""
    if not raw:
        return None
    return raw.strip().replace("’", "'").replace("‘", "'")


def _parse_unix_s(ts: int | None) -> datetime | None:
    """Aldi Nord liefert Unix-Timestamps in Sekunden (nicht Millisekunden)."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _find_products_recursive(data: object, depth: int = 0) -> list[dict]:
    """Durchsucht rekursiv eine JSON-Struktur nach einer Liste von Produkten."""
    if depth > 12:
        return []
    if isinstance(data, list) and data:
        if isinstance(data[0], dict) and "productSlug" in data[0]:
            return data
        for item in data:
            result = _find_products_recursive(item, depth + 1)
            if result:
                return result
    elif isinstance(data, dict):
        for value in data.values():
            result = _find_products_recursive(value, depth + 1)
            if result:
                return result
    return []
