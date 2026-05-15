from __future__ import annotations

import json
import logging
import re
from datetime import datetime, date, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .base import SupermarketAdapter
from ..models.offer import Offer, Supermarket
from ..models.sales_unit_parser import SalesUnitParser
from ..models.kaufland_base_price_parser import KauflandBasePriceParser

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

_PRICE_NUM_RE = re.compile(r"\d+[,.]?\d*")


class KauflandAdapter(SupermarketAdapter):
    URL = "https://filiale.kaufland.de/angebote/uebersicht.html"

    def __init__(self, html_file: str | None = None) -> None:
        self._su_parser   = SalesUnitParser()
        self._bp_parser   = KauflandBasePriceParser()
        self._html_file   = html_file

    @property
    def source_name(self) -> str:
        return Supermarket.KAUFLAND.value

    def fetch_offers(self) -> list[Offer]:
        html = self._fetch_html()
        offers = self._parse_offers(html)
        log.info("Kaufland: %d Angebote gefunden", len(offers))
        return offers

    def _fetch_html(self) -> str:
        if self._html_file:
            log.info("Kaufland: Lade HTML aus Datei %s", self._html_file)
            return Path(self._html_file).read_text(encoding="utf-8")
        log.info("Kaufland: Lade %s", self.URL)
        resp = requests.get(self.URL, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.text

    def _parse_offers(self, html: str) -> list[Offer]:
        soup = BeautifulSoup(html, "lxml")
        raw_offers = self._extract_offers_json(soup)

        if not raw_offers:
            log.warning(
                "Kaufland: Keine Angebotsdaten im HTML gefunden. "
                "Möglicherweise hat sich die Seitenstruktur geändert."
            )
            return []

        now = datetime.now(timezone.utc)
        offers: list[Offer] = []
        for raw in raw_offers:
            try:
                offers.append(self._map_to_offer(raw, now))
            except Exception:
                log.debug(
                    "Kaufland: Angebot übersprungen: %s",
                    raw.get("offerId", "?"),
                    exc_info=True,
                )
        return offers

    def _extract_offers_json(self, soup: BeautifulSoup) -> list[dict]:
        decoder = json.JSONDecoder()

        for script in soup.find_all("script"):
            content = script.string or ""
            if "offerId" not in content:
                continue

            # Strategie 0: Kaufland SSR-Pattern
            # window.SSR['...'] = {"props":{"offerData":{"cycles":[{"categories":[{"offers":[...]}]}]}}}
            ssr_match = re.search(r"window\.SSR\['[^']+'\]\s*=\s*(\{)", content)
            if ssr_match:
                try:
                    ssr_obj, _ = decoder.raw_decode(content, ssr_match.start(1))
                    cycles = ssr_obj["props"]["offerData"]["cycles"]
                    seen: dict[str, dict] = {}
                    for cycle in cycles:
                        for cat in cycle.get("categories", []):
                            for offer in cat.get("offers", []):
                                oid = offer.get("offerId")
                                if oid and oid not in seen:
                                    seen[oid] = offer
                    if seen:
                        log.debug("Kaufland: %d Angebote via SSR-Pfad gefunden", len(seen))
                        return list(seen.values())
                except (json.JSONDecodeError, ValueError, KeyError, TypeError):
                    log.debug("Kaufland: SSR-Pfad fehlgeschlagen", exc_info=True)

            # Strategie 1: reines JSON-Script-Tag
            if script.get("type") == "application/json":
                try:
                    data = json.loads(content)
                    offers = _find_offers_recursive(data)
                    if offers:
                        log.debug("Kaufland: Angebote via application/json gefunden")
                        return offers
                except json.JSONDecodeError:
                    pass

            # Strategie 2: JSON-Array [{...offerId...}]
            for m in re.finditer(r"\[{", content):
                try:
                    obj, _ = decoder.raw_decode(content, m.start())
                    if (
                        isinstance(obj, list)
                        and obj
                        and isinstance(obj[0], dict)
                        and "offerId" in obj[0]
                    ):
                        log.debug("Kaufland: Angebote via Array-Scan gefunden")
                        return obj
                except (json.JSONDecodeError, ValueError):
                    pass

            # Strategie 3: rückwärts von "offerId" zum nächsten "[" suchen
            for m in re.finditer(r'"offerId"', content):
                start = content.rfind("[", 0, m.start())
                if start == -1:
                    continue
                try:
                    obj, _ = decoder.raw_decode(content, start)
                    if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "offerId" in obj[0]:
                        log.debug("Kaufland: Angebote via Rückwärts-Scan gefunden")
                        return obj
                except (json.JSONDecodeError, ValueError):
                    pass

        return []

    def _map_to_offer(self, raw: dict, scraped_at: datetime) -> Offer:
        offer_id = str(raw.get("offerId") or raw.get("klNr") or "")
        title    = (raw.get("title") or "").strip()
        subtitle = (raw.get("subtitle") or "").strip()

        name  = subtitle if subtitle else title
        brand = _normalize_brand(title) if title else None

        sale_price     = float(raw.get("price") or 0.0)
        original_price = _parse_price_str(raw.get("formattedOldPrice"))
        discount_pct   = float(raw.get("discount")) if raw.get("discount") else None

        # Regulärer Basispreis
        bp = self._bp_parser.parse(raw.get("basePrice") or raw.get("formattedBasePrice"))

        # Kaufland-Card-Preise
        card_price = _parse_price_str(raw.get("loyaltyFormattedPrice"))
        cbp = self._bp_parser.parse(
            raw.get("loyaltyFormattedBasePrice") or raw.get("loyaltyBasePrice")
        )
        card_discount = float(raw.get("loyaltyDiscount")) if raw.get("loyaltyDiscount") else None

        # Verpackung
        sales_unit_raw = (raw.get("unit") or "").strip() or None
        sales_unit     = self._su_parser.parse(sales_unit_raw) if sales_unit_raw else None

        return Offer(
            source          = Supermarket.KAUFLAND,
            product_slug    = offer_id,
            name            = name,
            brand           = brand,
            short_description  = None,
            long_description   = (raw.get("detailDescription") or "").strip() or None,
            sale_price      = sale_price,
            original_price  = original_price,
            discount_percent = discount_pct,
            # Basispreis
            base_price_value      = bp.value,
            base_price_value_max  = bp.max_value,
            base_price_unit       = bp.unit,
            base_price_has_prefix = bp.has_prefix,
            # Verpackung
            sales_unit_raw  = sales_unit_raw,
            sales_unit      = sales_unit,
            # Gültigkeit
            valid_from      = _parse_date_str(raw.get("dateFrom")),
            valid_until     = _parse_date_str(raw.get("dateTo")),
            # Bild
            image_url       = raw.get("listImage") or None,
            # Kategorien
            category_ids    = ["Angebote"],
            # Card-Preise
            card_price                = card_price,
            card_base_price_value     = cbp.value,
            card_base_price_value_max = cbp.max_value,
            card_base_price_unit      = cbp.unit,
            card_discount_percent     = card_discount,
            scraped_at      = scraped_at,
        )


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _normalize_brand(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.strip().replace("’", "'").replace("‘", "'")


def _parse_price_str(s: str | None) -> float | None:
    """Parst "2.29", "2,29 €", "0.88*" → float."""
    if not s:
        return None
    m = _PRICE_NUM_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group().replace(",", "."))
    except ValueError:
        return None


def _parse_date_str(s: str | None) -> datetime | None:
    """Parst "YYYY-MM-DD" → UTC datetime."""
    if not s:
        return None
    try:
        d = date.fromisoformat(s)
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def _find_offers_recursive(data: object, depth: int = 0) -> list[dict]:
    """Sucht rekursiv nach einer Liste von Dicts mit 'offerId'-Schlüssel."""
    if depth > 10:
        return []
    if isinstance(data, list) and data:
        if isinstance(data[0], dict) and "offerId" in data[0]:
            return data
        for item in data:
            result = _find_offers_recursive(item, depth + 1)
            if result:
                return result
    elif isinstance(data, dict):
        for value in data.values():
            result = _find_offers_recursive(value, depth + 1)
            if result:
                return result
    return []
