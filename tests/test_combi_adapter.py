"""
Tests für den Combi-Adapter — kein Netzwerkzugriff, alles via Mock-HTML.

Getestete Bereiche:
  - _parse_de_price:   deutsches Komma-Preisformat
  - _parse_base_price: Grundpreis mit Einheit
  - _parse_deposit:    Pfand-Parsing
  - _extract_sku:      Produktnummer aus URL
  - _get_total_pages:  Paginierungs-Erkennung
  - CombiAdapter._parse_page: vollständige Produktkarte
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bs4 import BeautifulSoup

from src.adapters.combi import (
    CombiAdapter,
    _extract_sku,
    _get_total_pages,
    _parse_base_price,
    _parse_de_price,
    _parse_deposit,
)
from src.models.offer import Supermarket


# ---------------------------------------------------------------------------
# _parse_de_price
# ---------------------------------------------------------------------------

class TestParseDePrice:
    def test_standard(self):
        assert _parse_de_price("0,99 €") == 0.99

    def test_zweistellig(self):
        assert _parse_de_price("12,14 €") == 12.14

    def test_dreistellig(self):
        assert _parse_de_price("3,49 €") == 3.49

    def test_groesserer_preis(self):
        assert _parse_de_price("49,99 €") == 49.99

    def test_leer(self):
        assert _parse_de_price("") is None

    def test_kein_preis(self):
        assert _parse_de_price("kein Preis") is None

    def test_ganzzahl(self):
        assert _parse_de_price("5 €") == 5.0


# ---------------------------------------------------------------------------
# _parse_base_price
# ---------------------------------------------------------------------------

class TestParseBasePrice:
    def test_liter(self):
        val, unit = _parse_base_price("3,00 €/1 l")
        assert val  == 3.00
        assert unit == "L"   # normalisiert

    def test_kilo(self):
        val, unit = _parse_base_price("13,96 €/1 kg")
        assert val  == 13.96
        assert unit == "kg"

    def test_kilo_gross(self):
        val, unit = _parse_base_price("49,75 €/1 kg")
        assert val  == 49.75
        assert unit == "kg"

    def test_kein_grundpreis(self):
        val, unit = _parse_base_price("kein Grundpreis")
        assert val  is None
        assert unit is None

    def test_leer(self):
        val, unit = _parse_base_price("")
        assert val  is None
        assert unit is None


# ---------------------------------------------------------------------------
# _parse_deposit
# ---------------------------------------------------------------------------

class TestParseDeposit:
    def test_pfand_vorhanden(self):
        val, is_dep = _parse_deposit("(+ Pfand 0,25 €)")
        assert val    == 0.25
        assert is_dep is True

    def test_groesseres_pfand(self):
        val, is_dep = _parse_deposit("(+ Pfand 3,00 €)")
        assert val    == 3.00
        assert is_dep is True

    def test_kein_pfand(self):
        val, is_dep = _parse_deposit("ohne Pfand")
        assert val    is None
        assert is_dep is False

    def test_leer(self):
        val, is_dep = _parse_deposit("")
        assert val    is None
        assert is_dep is False


# ---------------------------------------------------------------------------
# _extract_sku
# ---------------------------------------------------------------------------

class TestExtractSku:
    def test_standard_url(self):
        assert _extract_sku("/coca-cola-zero-sugar_einweg_4504050019.html") == "4504050019"

    def test_kurze_sku(self):
        assert _extract_sku("/produkt_12345.html") == "12345"

    def test_bild_url(self):
        assert _extract_sku(
            "https://d2y99t05v0nd2u.cloudfront.net/products/images/4504050019_main.jpg"
        ) is None  # keine _SKU.html in Bild-URLs

    def test_keine_zahl(self):
        assert _extract_sku("/produkt-ohne-sku.html") is None

    def test_leer(self):
        assert _extract_sku("") is None


# ---------------------------------------------------------------------------
# _get_total_pages
# ---------------------------------------------------------------------------

class TestGetTotalPages:
    def _soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    def test_seite_x_von_y(self):
        soup = self._soup("<div>Seite 1 von 20</div>")
        assert _get_total_pages(soup) == 20

    def test_eine_seite_fallback(self):
        soup = self._soup("<div>Keine Paginierung</div>")
        assert _get_total_pages(soup) == 1

    def test_mehrseitig(self):
        soup = self._soup("<span class='pager'>Seite 3 von 15</span>")
        assert _get_total_pages(soup) == 15


# ---------------------------------------------------------------------------
# Mock-HTML Fixture
# ---------------------------------------------------------------------------

_MOCK_HTML = """<!DOCTYPE html>
<html><body>

<div>Seite 1 von 2</div>

<!-- Produkt 1: Coca-Cola mit Rabatt + Pfand -->
<div class="product-card__description">
  <a href="/coca-cola-zero-sugar_einweg_4504050019.html"
     class="product-card__poster__link">
    <img class="product-card__photo"
         src="https://d2y99t05v0nd2u.cloudfront.net/products/images/4504050019_main.jpg"
         alt="Coca-Cola Zero Sugar (Einweg)" />
  </a>
  <span class="product-card__name">
    <a class="product-card__name__link"
       href="/coca-cola-zero-sugar_einweg_4504050019.html">
      Coca-Cola Zero Sugar (Einweg)
    </a>
  </span>
  <small class="product-card__weight">330 ml</small>
  <div class="product-card__price--current"><strong>0,99 €</strong></div>
  <del class="product-card__price--old"><strong>1,19 €</strong></del>
  <div class="product-card__bulk-price">3,00 €/1 l</div>
  <div class="product-card__deposit">(+ Pfand 0,25 €)</div>
</div>

<!-- Produkt 2: Kaffee ohne Rabatt, ohne Pfand -->
<div class="product-card__description">
  <a href="/dallmayr-prodomo_500g_1234567890.html"
     class="product-card__poster__link">
    <img class="product-card__photo"
         src="https://d2y99t05v0nd2u.cloudfront.net/products/images/1234567890_main.jpg"
         alt="Dallmayr Prodomo" />
  </a>
  <span class="product-card__name">
    <a class="product-card__name__link"
       href="/dallmayr-prodomo_500g_1234567890.html">
      Dallmayr Prodomo
    </a>
  </span>
  <small class="product-card__weight">500 g</small>
  <div class="product-card__price--current"><strong>4,99 €</strong></div>
  <div class="product-card__bulk-price">9,98 €/1 kg</div>
</div>

<!-- Produkt 3: Ohne SKU → wird übersprungen -->
<div class="product-card__description">
  <span class="product-card__name">
    <a class="product-card__name__link" href="/produkt-ohne-sku.html">
      Produkt ohne SKU
    </a>
  </span>
  <div class="product-card__price--current"><strong>1,99 €</strong></div>
</div>

</body></html>
"""


# ---------------------------------------------------------------------------
# CombiAdapter Integration (kein Netzwerk)
# ---------------------------------------------------------------------------

class TestCombiAdapterParsing:
    @pytest.fixture
    def adapter(self) -> CombiAdapter:
        return CombiAdapter("220012809")

    @pytest.fixture
    def offers(self, adapter):
        soup = BeautifulSoup(_MOCK_HTML, "lxml")
        now  = datetime.now(timezone.utc)
        return list(adapter._parse_page(soup, now, set()))

    def test_adapter_instanziierbar(self, adapter):
        assert adapter.source_name == "combi"
        assert adapter.source_name == Supermarket.COMBI.value

    def test_zwei_gueltige_angebote(self, offers):
        """3 Karten im HTML, 1 ohne SKU → 2 Angebote."""
        assert len(offers) == 2

    def test_source_ist_combi(self, offers):
        assert all(o.source == Supermarket.COMBI for o in offers)

    def test_cola_preis(self, offers):
        cola = next(o for o in offers if "Coca" in o.name)
        assert cola.sale_price == 0.99

    def test_cola_alter_preis(self, offers):
        cola = next(o for o in offers if "Coca" in o.name)
        assert cola.original_price == 1.19

    def test_cola_rabatt(self, offers):
        cola = next(o for o in offers if "Coca" in o.name)
        assert cola.discount_percent is not None
        assert abs(cola.discount_percent - 16.8) < 0.5

    def test_cola_grundpreis(self, offers):
        cola = next(o for o in offers if "Coca" in o.name)
        assert cola.base_price_value == 3.00
        assert cola.base_price_unit  == "L"

    def test_cola_pfand(self, offers):
        cola = next(o for o in offers if "Coca" in o.name)
        assert cola.is_deposit_product is True
        assert cola.deposit_value == 0.25

    def test_cola_slug(self, offers):
        cola = next(o for o in offers if "Coca" in o.name)
        assert cola.product_slug == "4504050019"

    def test_kaffee_kein_pfand(self, offers):
        kaffee = next(o for o in offers if "Dallmayr" in o.name)
        assert kaffee.is_deposit_product is False
        assert kaffee.deposit_value is None

    def test_kaffee_grundpreis_kg(self, offers):
        kaffee = next(o for o in offers if "Dallmayr" in o.name)
        assert kaffee.base_price_value == 9.98
        assert kaffee.base_price_unit  == "kg"

    def test_kaffee_sales_unit(self, offers):
        kaffee = next(o for o in offers if "Dallmayr" in o.name)
        assert kaffee.sales_unit_raw == "500 g"

    def test_category_ids(self, offers):
        assert all(o.category_ids == ["Angebote"] for o in offers)

    def test_dedup_verhindert_doppelten_eintrag(self, adapter):
        """Gleiche SKU auf zwei Seiten: nur einmal im Ergebnis."""
        soup     = BeautifulSoup(_MOCK_HTML, "lxml")
        now      = datetime.now(timezone.utc)
        seen     = set()
        offers1  = list(adapter._parse_page(soup, now, seen))
        # Zweite Runde mit gleichen seen-SKUs → 0 neue Angebote
        offers2  = list(adapter._parse_page(soup, now, seen))
        assert len(offers1) == 2
        assert len(offers2) == 0

    def test_pagination_erkannt(self):
        soup = BeautifulSoup(_MOCK_HTML, "lxml")
        assert _get_total_pages(soup) == 2
