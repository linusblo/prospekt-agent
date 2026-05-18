"""
Tests für den Edeka-Adapter — kein Netzwerkzugriff, alles via Mock-HTML.

Getestete Bereiche:
  - _parse_price_text: alle 3 Preisformate + Edge Cases
  - _parse_german_date: DE-Datum → UTC datetime
  - EdekaAdapter._parse_offers: Mock-HTML mit Dedup, Überspringen ohne Preis
  - brand_resolver für Edeka-typische Produktnamen
"""
from __future__ import annotations

from datetime import timezone, timedelta, datetime

import pytest

from src.adapters.edeka import (
    EdekaAdapter,
    _parse_price_text,
    _parse_german_date,
)
from src.models.offer import Supermarket
from src.utils.brand_resolver import resolve_brand


# ---------------------------------------------------------------------------
# _parse_price_text
# ---------------------------------------------------------------------------

class TestParsePriceText:
    def test_festpreis(self):
        sp, disc, ap = _parse_price_text("Festpreis von 1.11 €")
        assert sp   == 1.11
        assert disc is None
        assert ap   is None

    def test_festpreis_zweistellig(self):
        sp, disc, ap = _parse_price_text("Festpreis von 12.99 €")
        assert sp == 12.99

    def test_rabattierter_preis(self):
        sp, disc, ap = _parse_price_text(
            "Rabattierter Preis von 0.79 € (Insgesamt -34 % Rabatt)"
        )
        assert sp   == 0.79
        assert disc == 34.0
        assert ap   is None

    def test_rabatt_100_prozent_range(self):
        sp, disc, ap = _parse_price_text(
            "Rabattierter Preis von 2.99 € (Insgesamt -28 % Rabatt)"
        )
        assert sp   == 2.99
        assert disc == 28.0

    def test_app_preis(self):
        sp, disc, ap = _parse_price_text("App-Preis von 0.39 €")
        assert sp is None
        assert ap == 0.39

    def test_app_preis_hoeher(self):
        sp, disc, ap = _parse_price_text("App-Preis von 3.99 €")
        assert ap == 3.99

    def test_kein_preis(self):
        sp, disc, ap = _parse_price_text("Kein Preis angegeben")
        assert sp   is None
        assert disc is None
        assert ap   is None

    def test_leerer_string(self):
        sp, disc, ap = _parse_price_text("")
        assert all(x is None for x in (sp, disc, ap))

    def test_festpreis_ganzzahl(self):
        # [\d.]+ matched auch Ganzzahlen ohne Dezimalpunkt
        sp, disc, ap = _parse_price_text("Festpreis von 5 €")
        assert sp == 5.0

    def test_rabatt_dreistelig(self):
        sp, disc, ap = _parse_price_text(
            "Rabattierter Preis von 4.99 € (Insgesamt -100 % Rabatt)"
        )
        assert disc == 100.0

    def test_grosser_festpreis(self):
        sp, disc, ap = _parse_price_text("Festpreis von 29.99 €")
        assert sp == 29.99


# ---------------------------------------------------------------------------
# _parse_german_date
# ---------------------------------------------------------------------------

class TestParseGermanDate:
    def test_standard_datum(self):
        dt = _parse_german_date("Gültig ab 17.05.2026")
        assert dt is not None
        assert dt.year  == 2026
        assert dt.month == 5
        assert dt.day   == 17
        assert dt.tzinfo == timezone.utc

    def test_datum_einstellig(self):
        dt = _parse_german_date("Gültig ab 7.5.2026")
        assert dt is not None
        assert dt.day   == 7
        assert dt.month == 5

    def test_datum_18_mai(self):
        dt = _parse_german_date("Gültig ab 18.05.2026")
        assert dt is not None
        assert dt.day == 18

    def test_valid_until_plus_6(self):
        """valid_until = valid_from + 6 Tage (Edeka Mo–Sa)."""
        valid_from = _parse_german_date("Gültig ab 19.05.2026")
        assert valid_from is not None
        valid_until = valid_from + timedelta(days=6)
        assert valid_until.day == 25

    def test_kein_datum(self):
        assert _parse_german_date("Kein Datum") is None

    def test_leerer_string(self):
        assert _parse_german_date("") is None


# ---------------------------------------------------------------------------
# Mock-HTML Fixture
# ---------------------------------------------------------------------------

_MOCK_HTML = """<!DOCTYPE html>
<html><body>

<!-- Produkt 1: Festpreis (UUID kommt 2× vor → Dedup) -->
<a href="#angebot-uuid-001" class="product-link">
  <span class="sr-only">Angebot:</span>
  Weihenstephan Tafelbutter
</a>

<dialog id="dialog-angebot-uuid-001">
  <h3>Weihenstephan Tafelbutter</h3>
  <strong class="text-sm text-grey">Gültig ab 19.05.2026</strong>
  <div class="sr-only">Festpreis von 1.89 €</div>
  <span class="inline-block">250 g Packung</span>
  <img src="https://offer-images.api.edeka/uuid-001_main.png">
</dialog>

<!-- Gleiche UUID nochmal (Übersicht + Dialog = 2×) → darf nur 1× vorkommen -->
<a href="#angebot-uuid-001">
  <span class="sr-only">Angebot:</span>
  Weihenstephan Tafelbutter
</a>

<!-- Produkt 2: Rabattierter Preis + App-Preis -->
<a href="#angebot-uuid-002">
  <span class="sr-only">Angebot:</span>
  Dallmayr Prodomo
</a>

<dialog id="dialog-angebot-uuid-002">
  <h3>Dallmayr Prodomo</h3>
  <strong class="text-sm text-grey">Gültig ab 19.05.2026</strong>
  <div class="sr-only">Rabattierter Preis von 4.99 € (Insgesamt -28 % Rabatt)</div>
  <div class="sr-only">App-Preis von 3.99 €</div>
  <img src="https://offer-images.api.edeka/uuid-002_main.png">
</dialog>

<!-- Produkt 3: Kein Preis → wird übersprungen -->
<a href="#angebot-uuid-003">
  <span class="sr-only">Angebot:</span>
  Produkt ohne Preis
</a>
<dialog id="dialog-angebot-uuid-003">
  <h3>Produkt ohne Preis</h3>
  <strong class="text-grey">Gültig ab 19.05.2026</strong>
  <!-- kein sr-only mit Preis -->
</dialog>

<!-- Produkt 4: Kein Dialog → wird übersprungen -->
<a href="#angebot-uuid-004">
  <span class="sr-only">Angebot:</span>
  Produkt ohne Dialog
</a>

</body></html>
"""


# ---------------------------------------------------------------------------
# EdekaAdapter Integration (kein Netzwerk)
# ---------------------------------------------------------------------------

class TestEdekaAdapterParsing:
    @pytest.fixture
    def adapter(self) -> EdekaAdapter:
        return EdekaAdapter("071115")

    def test_adapter_instanziierbar(self, adapter):
        assert adapter.source_name == "edeka"
        assert adapter.source_name == Supermarket.EDEKA.value

    def test_url_aus_market_id(self, adapter):
        assert "071115" in adapter._url
        assert adapter._url.startswith("https://www.edeka.de")

    def test_zwei_gueltige_angebote(self, adapter):
        """3 Produkte mit Dialog, 1 ohne Dialog → 2 Angebote (eines ohne Preis übersprungen)."""
        offers = adapter._parse_offers(_MOCK_HTML)
        assert len(offers) == 2

    def test_source_ist_edeka(self, adapter):
        offers = adapter._parse_offers(_MOCK_HTML)
        assert all(o.source == Supermarket.EDEKA for o in offers)

    def test_keine_duplikate(self, adapter):
        """UUID uuid-001 kommt 2× im HTML vor → darf nur 1× im Ergebnis sein."""
        offers = adapter._parse_offers(_MOCK_HTML)
        slugs = [o.product_slug for o in offers]
        assert len(slugs) == len(set(slugs))

    def test_butter_festpreis(self, adapter):
        offers = adapter._parse_offers(_MOCK_HTML)
        butter = next(o for o in offers if "Tafelbutter" in o.name)
        assert butter.sale_price      == 1.89
        assert butter.discount_percent is None
        assert butter.card_price       is None

    def test_butter_valid_from(self, adapter):
        offers = adapter._parse_offers(_MOCK_HTML)
        butter = next(o for o in offers if "Tafelbutter" in o.name)
        assert butter.valid_from is not None
        assert butter.valid_from.day == 19

    def test_butter_valid_until_plus_6_tage(self, adapter):
        offers = adapter._parse_offers(_MOCK_HTML)
        butter = next(o for o in offers if "Tafelbutter" in o.name)
        assert butter.valid_until is not None
        assert butter.valid_until == butter.valid_from + timedelta(days=6)

    def test_kaffee_rabatt_und_app_preis(self, adapter):
        offers = adapter._parse_offers(_MOCK_HTML)
        kaffee = next(o for o in offers if "Dallmayr" in o.name)
        assert kaffee.sale_price       == 4.99
        assert kaffee.discount_percent == 28.0
        assert kaffee.card_price       == 3.99

    def test_kaffee_bild_url(self, adapter):
        offers = adapter._parse_offers(_MOCK_HTML)
        kaffee = next(o for o in offers if "Dallmayr" in o.name)
        assert kaffee.image_url is not None
        assert "edeka" in kaffee.image_url

    def test_product_slug_ist_uuid(self, adapter):
        offers = adapter._parse_offers(_MOCK_HTML)
        slugs = {o.product_slug for o in offers}
        assert "uuid-001" in slugs
        assert "uuid-002" in slugs

    def test_butter_sales_unit(self, adapter):
        offers = adapter._parse_offers(_MOCK_HTML)
        butter = next(o for o in offers if "Tafelbutter" in o.name)
        assert butter.sales_unit_raw == "250 g Packung"

    def test_category_ids_default(self, adapter):
        offers = adapter._parse_offers(_MOCK_HTML)
        assert all(o.category_ids == ["Angebote"] for o in offers)


# ---------------------------------------------------------------------------
# Brand-Resolver für Edeka-typische Produkte
# ---------------------------------------------------------------------------

class TestBrandResolverEdeka:
    def test_weihenstephan(self):
        assert resolve_brand("Weihenstephan Tafelbutter") == "WEIHENSTEPHAN"

    def test_dallmayr(self):
        assert resolve_brand("Dallmayr Prodomo") == "DALLMAYR"

    def test_haribo(self):
        assert resolve_brand("Haribo Fruchtgummi") == "HARIBO"

    def test_mueller_lowercase(self):
        """'müller' startet mit Kleinbuchstaben → trotzdem korrekte Marke."""
        result = resolve_brand("müller Milchreis")
        assert result is not None
        assert result.upper() == "MÜLLER"

    def test_deutschland_fallback(self):
        """'Deutschland -' → 'Deutschland' ist Skip-Wort, nächstes Wort wird Marke."""
        result = resolve_brand("Deutschland - Tafeläpfel")
        assert result is not None
        assert result != "DEUTSCHLAND"
