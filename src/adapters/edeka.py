"""
Edeka-Adapter — parst Filialangebote von www.edeka.de.

Alle Angebotsdaten befinden sich im initialen HTML (≈ 1.3 MB).
Kein JavaScript-Rendering nötig.

HTML-Struktur:
  Übersicht:   <a href="#angebot-{UUID}">
  Detaildialog: <dialog id="dialog-angebot-{UUID}">
    - <h3>                      Produktname
    - <strong>Gültig ab …</strong>
    - <div class="sr-only">     maschinenlesbare Preise
    - <img src="…">             Produktbild

Preisformate (sr-only Divs):
  "Festpreis von 1.11 €"
  "Rabattierter Preis von 0.79 € (Insgesamt -34 % Rabatt)"
  "App-Preis von 0.39 €"       → card_price-Feld
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .base import SupermarketAdapter
from ..models.offer import Offer, Supermarket
from ..models.sales_unit_parser import SalesUnitParser
from src.utils.brand_resolver import resolve_brand

log = logging.getLogger(__name__)

_BASE_URL   = "https://www.edeka.de"
_MARKET_URL = f"{_BASE_URL}/maerkte/{{market_id}}/angebote/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_UUID_RE = re.compile(r"^#angebot-(.+)$")


class EdekaAdapter(SupermarketAdapter):
    """
    Edeka-Adapter (filialspezifisch).

    Beispiel:
        EdekaAdapter("071115")                  # per Filial-ID
        EdekaAdapter("071115", html_file="x.html")  # Offline / Tests
    """

    def __init__(self, market_id: str, html_file: str | None = None) -> None:
        self._url       = _MARKET_URL.format(market_id=market_id)
        self._html_file = html_file
        self._su_parser = SalesUnitParser()

    @property
    def source_name(self) -> str:
        return Supermarket.EDEKA.value

    # ------------------------------------------------------------------

    def fetch_offers(self) -> list[Offer]:
        html   = self._fetch_html()
        offers = self._parse_offers(html)
        log.info("Edeka: %d Angebote gefunden", len(offers))
        return offers

    def _fetch_html(self) -> str:
        if self._html_file:
            log.info("Edeka: Lade HTML aus Datei %s", self._html_file)
            return Path(self._html_file).read_text(encoding="utf-8")

        log.info("Edeka: Lade %s", self._url)
        resp = requests.get(
            self._url,
            headers=_HEADERS,
            allow_redirects=True,
            timeout=30,
        )
        resp.raise_for_status()
        size_kb = len(resp.content) / 1024
        log.info("Edeka: %.0f KB HTML geladen", size_kb)
        return resp.text

    def _parse_offers(self, html: str) -> list[Offer]:
        soup = BeautifulSoup(html, "lxml")
        now  = datetime.now(timezone.utc)

        # Alle eindeutigen UUIDs aus Angebots-Links sammeln (jede kommt 2× vor)
        seen: set[str] = set()
        for a_tag in soup.find_all("a", href=True):
            m = _UUID_RE.match(a_tag["href"])
            if m:
                seen.add(m.group(1))

        log.info("Edeka: %d Angebots-UUIDs gefunden (nach Dedup)", len(seen))

        offers: list[Offer] = []
        for uuid in seen:
            try:
                dialog = soup.find(id=f"dialog-angebot-{uuid}")
                if dialog is None:
                    log.debug("Edeka: Kein Dialog für %s", uuid)
                    continue
                offer = self._map_dialog(dialog, uuid, now)
                if offer is not None:
                    offers.append(offer)
            except Exception:
                log.debug("Edeka: UUID %s übersprungen", uuid, exc_info=True)

        return offers

    def _map_dialog(self, dialog, uuid: str, scraped_at: datetime) -> Offer | None:
        # Produktname aus <h3>
        h3   = dialog.find("h3")
        name = h3.get_text(strip=True) if h3 else ""
        if not name:
            return None

        # Preise aus allen <div class="sr-only">
        sale_price       = None
        discount_percent = None
        card_price       = None

        for div in dialog.find_all("div"):
            if "sr-only" not in (div.get("class") or []):
                continue
            text = div.get_text(strip=True)
            sp, disc, ap = _parse_price_text(text)
            if sp is not None:
                sale_price       = sp
                discount_percent = disc
            if ap is not None:
                card_price = ap

        if sale_price is None:
            log.debug("Edeka: Kein Verkaufspreis für %r (%s)", name, uuid)
            return None

        # Gültigkeitsdatum aus <strong> mit "Gültig ab"
        valid_from  = None
        valid_until = None
        for strong in dialog.find_all(["strong", "span"]):
            text = strong.get_text(strip=True)
            if "ltig ab" in text or "ltig" in text.lower():
                valid_from = _parse_german_date(text)
                if valid_from:
                    # Edeka-Angebote laufen typischerweise Mo–Sa (6 Tage)
                    valid_until = valid_from + timedelta(days=6)
                break

        # Bild aus <img> mit Edeka-CDN-URL
        image_url = None
        for img in dialog.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if src and ("edeka" in src.lower() or src.startswith("http")):
                image_url = src
                break

        # Sales Unit aus <span class="inline-block"> (wenn vorhanden)
        su_raw = None
        for span in dialog.find_all("span"):
            if "inline-block" in (span.get("class") or []):
                text = span.get_text(strip=True)
                if text:
                    su_raw = text
                    break
        su = self._su_parser.parse(su_raw) if su_raw else None

        return Offer(
            source               = Supermarket.EDEKA,
            product_slug         = uuid,
            name                 = name,
            brand                = resolve_brand(name),
            short_description    = None,
            long_description     = None,
            sale_price           = sale_price,
            original_price       = None,
            discount_percent     = discount_percent,
            base_price_value     = None,
            base_price_value_max = None,
            base_price_unit      = None,
            base_price_has_prefix = False,
            card_price               = card_price,
            card_base_price_value    = None,
            card_base_price_value_max= None,
            card_base_price_unit     = None,
            card_discount_percent    = None,
            sales_unit_raw  = su_raw,
            sales_unit      = su,
            is_deposit_product = False,
            deposit_value   = None,
            valid_from      = valid_from,
            valid_until     = valid_until,
            image_url       = image_url,
            category_ids    = ["Angebote"],
            scraped_at      = scraped_at,
        )


# ---------------------------------------------------------------------------
# Testbare Parsing-Hilfsfunktionen (Modul-Level, direkt importierbar)
# ---------------------------------------------------------------------------

def _parse_price_text(text: str) -> tuple[float | None, float | None, float | None]:
    """
    Parst Preis-Texte aus sr-only Divs.
    Gibt (sale_price, discount_percent, app_price) zurück.

    Formate:
      "Festpreis von 1.11 €"                                → (1.11, None, None)
      "Rabattierter Preis von 0.79 € (Insgesamt -34 % Rabatt)" → (0.79, 34.0, None)
      "App-Preis von 0.39 €"                                → (None, None, 0.39)
    """
    # Festpreis
    m = re.search(r"Festpreis von ([\d.]+)\s*€", text)
    if m:
        return float(m.group(1)), None, None

    # Rabattierter Preis
    m = re.search(
        r"Rabattierter Preis von ([\d.]+)\s*€\s*\(Insgesamt -(\d+)\s*%\s*Rabatt\)",
        text,
    )
    if m:
        return float(m.group(1)), float(m.group(2)), None

    # App-Preis
    m = re.search(r"App-Preis von ([\d.]+)\s*€", text)
    if m:
        return None, None, float(m.group(1))

    return None, None, None


def _parse_german_date(text: str) -> datetime | None:
    """
    Parst "Gültig ab 17.05.2026" → datetime(2026, 5, 17, tzinfo=UTC).
    """
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if not m:
        return None
    try:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None
