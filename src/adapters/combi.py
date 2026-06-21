"""
Combi-Adapter — nutzt die Bonial-API für den gedruckten Wochenprospekt.

Der bisherige Adapter scrapte combi.de/alle_angebote_{store_id}.html, das
ist aber der Online-Lieferservice, nicht der Wochenprospekt. Bonial liefert
exakt den Print-Prospekt als strukturierte JSON-Daten (CORS-offen, kein Auth
nötig).

Workflow:
  1. Aktuelle Broschüre ermitteln (ID + Seitenanzahl):
     GET {BONIAL_BASE}/stores/{store_id}/brochures
         ?storeId={store_id}&publisherId={publisher_id}&limit=100&hasOffers=true
  2. Pro Seite (0..pageCount-1) Angebote laden:
     GET {BONIAL_BASE}/v2/offers/{brochure_id}?pages={n}

Deal-Typen pro Angebot (deals[]):
  SALES_PRICE             reguläres Angebot
  SPECIAL_PRICE           Karten-/Bonus-Preis (z.B. "MOIN CARD")
                          steht manchmal allein (ohne SALES_PRICE)
  REGULAR_PRICE           Vorheriger Preis / UVP
  RECOMMENDED_RETAIL_PRICE  alternative UVP-Variante
  OTHER                   reine Deko-/Rubrik-Banner ohne echten Preis
                          (minAmount 0) → wird übersprungen

priceByBaseUnit-Format ist uneinheitlich, z.B.:
  "1 kg = 6.90"   "1 l ab 7.52"   "(1 kg = 12.90)"
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

from .base import SupermarketAdapter
from ..models.offer import Offer, Supermarket
from src.utils.brand_resolver import resolve_brand

log = logging.getLogger(__name__)

BONIAL_BASE = "https://www.bonialserviceswidget.de/de"

_DEFAULT_STORE_ID     = "DE-1031632951"   # Combi Bergheim
_DEFAULT_PUBLISHER_ID = "DE-42265682"

_PAGE_DELAY = 0.3   # Sekunden Pause zwischen Seiten-Requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_UNIT_NORM: dict[str, str] = {
    "l": "L", "liter": "L",
    "ml": "ml", "cl": "cl",
    "kg": "kg",
    "g": "g", "gr": "g",
    "stk": "Stk",
}

_BASE_UNIT_RE = re.compile(
    r"\(?\s*[\d.,]+\s*(\w+)\s*(?:=|ab)\s*([\d.,]+)\s*\)?",
    re.IGNORECASE,
)


class CombiAdapter(SupermarketAdapter):
    """
    Combi-Adapter (Bonial-API, Wochenprospekt).

    Beispiel:
        CombiAdapter("DE-1031632951", "DE-42265682")
    """

    def __init__(
        self,
        store_id: str = _DEFAULT_STORE_ID,
        publisher_id: str = _DEFAULT_PUBLISHER_ID,
    ) -> None:
        self._store_id = store_id
        self._publisher_id = publisher_id

    @property
    def source_name(self) -> str:
        return Supermarket.COMBI.value

    # Stubs für die abstrakte Basisklasse (Combi nutzt eigene JSON-API-Logik)
    def _fetch_html(self) -> str:            # pragma: no cover
        raise NotImplementedError("Combi nutzt die Bonial-JSON-API, kein HTML")

    def _parse_offers(self, html: str) -> list[Offer]:   # pragma: no cover
        raise NotImplementedError("Combi nutzt _parse_offer_list()")

    # ------------------------------------------------------------------

    def fetch_offers(self) -> list[Offer]:
        now = datetime.now(timezone.utc)

        try:
            brochure_id, page_count = self._fetch_brochure_info()
        except Exception:
            log.error("Combi: Broschüren-Liste konnte nicht geladen werden", exc_info=True)
            return []

        if brochure_id is None:
            log.warning("Combi: Keine aktive Broschüre mit Angeboten gefunden")
            return []

        log.info("Combi: Broschüre %s mit %d Seiten gefunden", brochure_id, page_count)

        seen_ids: set[str] = set()
        offers: list[Offer] = []
        for page in range(page_count):
            try:
                raw_offers = self._fetch_page(brochure_id, page)
            except Exception:
                log.error("Combi: Seite %d konnte nicht geladen werden", page, exc_info=True)
                continue

            for offer in _parse_offer_list(raw_offers, now):
                if offer.product_slug in seen_ids:
                    log.debug("Combi: Duplikat-ID %s übersprungen", offer.product_slug)
                    continue
                seen_ids.add(offer.product_slug)
                offers.append(offer)

            if page < page_count - 1:
                time.sleep(_PAGE_DELAY)

        log.info("Combi: %d Angebote gefunden", len(offers))
        return offers

    def _fetch_brochure_info(self) -> tuple[str | None, int]:
        url = f"{BONIAL_BASE}/stores/{self._store_id}/brochures"
        params = {
            "storeId": self._store_id,
            "publisherId": self._publisher_id,
            "limit": 100,
            "hasOffers": "true",
        }
        log.info("Combi: Lade Broschüren-Liste …")
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        brochures = resp.json().get("brochures") or []
        if not brochures:
            return None, 0
        brochure = brochures[0]
        return brochure.get("id"), int(brochure.get("pageCount") or 0)

    def _fetch_page(self, brochure_id: str, page: int) -> list[dict]:
        url = f"{BONIAL_BASE}/v2/offers/{brochure_id}"
        log.info("Combi: Lade Seite %d …", page)
        resp = requests.get(
            url, headers=_HEADERS, params={"pages": page}, timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# Testbare Parsing-Hilfsfunktionen (Modul-Level)
# ---------------------------------------------------------------------------

def _parse_offer_list(raw_offers: list[dict], scraped_at: datetime) -> list[Offer]:
    """Mappt eine Liste roher Bonial-Offers auf Offer-Objekte (Fehler pro Eintrag toleriert)."""
    offers: list[Offer] = []
    for raw in raw_offers:
        try:
            offer = _map_offer(raw, scraped_at)
        except Exception:
            log.debug("Combi: Angebot übersprungen", exc_info=True)
            continue
        if offer is not None:
            offers.append(offer)
    return offers


def _map_offer(raw: dict[str, Any], scraped_at: datetime) -> Offer | None:
    offer_id = raw.get("id")
    if not offer_id:
        return None

    products = raw.get("products") or []
    if not products:
        return None
    product = products[0]

    name = (product.get("name") or "").strip()
    if not name:
        return None

    deals = raw.get("deals") or []
    sale_price    = _deal_amount(deals, "SALES_PRICE")
    special_price = _deal_amount(deals, "SPECIAL_PRICE")
    price = sale_price if sale_price is not None else special_price
    if price is None:
        # z.B. reine Deko-/Rubrik-Banner (Deal-Typ OTHER, minAmount 0)
        return None

    # SPECIAL_PRICE neben SALES_PRICE → Karten-/Bonus-Preis; allein → Hauptpreis
    card_price = special_price if (sale_price is not None and special_price is not None) else None

    original_price = _deal_amount(deals, "REGULAR_PRICE")
    if original_price is None:
        original_price = _deal_amount(deals, "RECOMMENDED_RETAIL_PRICE")

    brand_name = (product.get("brandName") or "").strip() or None
    title = f"{brand_name} {name}".strip() if brand_name else name

    description = None
    desc_list = product.get("description") or []
    if desc_list and desc_list[0]:
        description = desc_list[0].replace("\n", " ").strip() or None

    images = product.get("images") or []
    image_url = images[0] if images else (raw.get("image") or None)

    base_price_value, base_price_unit = _parse_price_by_base_unit(deals)

    return Offer(
        source               = Supermarket.COMBI,
        product_slug         = offer_id,
        name                 = title,
        brand                = brand_name or resolve_brand(title),
        short_description    = description,
        long_description     = None,
        sale_price           = price,
        original_price       = original_price,
        base_price_value     = base_price_value,
        base_price_value_max = None,
        base_price_unit      = base_price_unit,
        base_price_has_prefix = False,
        card_price               = card_price,
        card_base_price_value    = None,
        card_base_price_value_max= None,
        card_base_price_unit     = None,
        card_discount_percent    = None,
        sales_unit_raw  = None,
        sales_unit      = None,
        is_deposit_product = False,
        deposit_value   = None,
        valid_from      = _parse_iso(raw.get("validFrom")),
        valid_until     = _parse_iso(raw.get("validUntil")),
        image_url       = image_url,
        category_ids    = ["Angebote"],
        scraped_at      = scraped_at,
    )


def _deal_amount(deals: list[dict], deal_type: str) -> float | None:
    """Sucht den ersten Deal vom gegebenen Typ mit einem echten Preis (> 0)."""
    for d in deals:
        if d.get("type") == deal_type:
            amount = d.get("minAmount")
            if amount is not None and amount > 0:
                return float(amount)
    return None


def _parse_price_by_base_unit(deals: list[dict]) -> tuple[float | None, str | None]:
    """
    Parst priceByBaseUnit von SALES_PRICE oder SPECIAL_PRICE.
    Formate: "1 kg = 6.90", "1 l ab 7.52", "(1 kg = 12.90)".
    """
    for deal_type in ("SALES_PRICE", "SPECIAL_PRICE"):
        for d in deals:
            if d.get("type") != deal_type:
                continue
            text = d.get("priceByBaseUnit") or ""
            if not text:
                continue
            m = _BASE_UNIT_RE.search(text)
            if m:
                unit = _UNIT_NORM.get(m.group(1).lower(), m.group(1))
                value = float(m.group(2).replace(",", "."))
                return value, unit
    return None, None


def _parse_iso(text: str | None) -> datetime | None:
    """Parst '2026-06-21T22:00:00.000+0000' → datetime mit Zeitzone."""
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
