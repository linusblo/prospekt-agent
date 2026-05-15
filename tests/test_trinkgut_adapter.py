"""Tests für den Trinkgut-Adapter: Brand-Extraktion, Preis, HTML-Parsing."""
from __future__ import annotations

import pytest

from src.adapters.trinkgut import TrinkgutAdapter, _extract_brand, _parse_price
from src.models.offer import Supermarket


# ---------------------------------------------------------------------------
# _extract_brand
# ---------------------------------------------------------------------------

class TestExtractBrand:
    def test_bitburger_pils(self):
        assert _extract_brand("Bitburger Pils") == "BITBURGER"

    def test_veltins_pilsener(self):
        assert _extract_brand("Veltins Pilsener o. Fassbrause") == "VELTINS"

    def test_brinkhoffs_with_apostrophe(self):
        assert _extract_brand("Brinkhoff's") == "BRINKHOFF'S"

    def test_dr_oetker_abbreviation(self):
        """Erstes Wort endet auf '.' → zwei Wörter als Marke."""
        assert _extract_brand("Dr. Oetker Tiefkühlpizza") == "DR. OETKER"

    def test_short_first_word_takes_two(self):
        """Erstes Wort < 3 Zeichen → zwei Wörter."""
        assert _extract_brand("AK Racer Energy") == "AK RACER"

    def test_single_word_name(self):
        """Nur ein Wort → dieses Wort als Marke."""
        assert _extract_brand("Bitburger") == "BITBURGER"

    def test_none_input(self):
        assert _extract_brand(None) is None  # type: ignore[arg-type]

    def test_empty_string(self):
        assert _extract_brand("") is None

    def test_uppercase_result(self):
        assert _extract_brand("krombacher Pils") == "KROMBACHER"

    def test_brand_from_mixed_case(self):
        assert _extract_brand("Coca-Cola Zero Sugar") == "COCA-COLA"


# ---------------------------------------------------------------------------
# _parse_price (Hilfsfunktion)
# ---------------------------------------------------------------------------

class TestParsePrice:
    def _make_tag(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "lxml").find("p")

    def test_standard_price(self):
        tag = self._make_tag('<p class="product-price">3.<sup>99</sup></p>')
        assert _parse_price(tag) == 3.99

    def test_whole_number_with_dash(self):
        tag = self._make_tag('<p class="product-price">5.<sup>-</sup></p>')
        assert _parse_price(tag) == 5.00

    def test_higher_price(self):
        tag = self._make_tag('<p class="product-price">12.<sup>99</sup></p>')
        assert _parse_price(tag) == 12.99

    def test_comma_as_decimal(self):
        tag = self._make_tag('<p class="product-price">3,<sup>99</sup></p>')
        assert _parse_price(tag) == 3.99


# ---------------------------------------------------------------------------
# Mock-HTML Parsing (Integration)
# ---------------------------------------------------------------------------

_MOCK_HTML = """<!DOCTYPE html>
<html><body>
<div class="product-box box-boxed">
    <div class="product-image-wrapper">
        <a href="/angebote/bier/bitburger-pils-123">
            <img src="/img/bitburger.jpg" alt="Bitburger">
        </a>
    </div>
    <div class="product-info">
        <div class="product-price-wrapper">
            <p class="product-price">12.<sup>99</sup></p>
        </div>
        <p class="h4 product-name">Bitburger Pils</p>
        <p class="product-description">Kasten = 24 x 0,33 l (1 l = € 1.64) zzgl. Pfand</p>
    </div>
</div>
<div class="product-box box-boxed">
    <div class="product-image-wrapper">
        <a href="/angebote/softdrinks/coca-cola-zero-456">
            <img src="/img/cola.jpg" alt="Cola">
        </a>
    </div>
    <div class="product-info">
        <div class="product-price-wrapper">
            <p class="product-price">7.<sup>99</sup></p>
        </div>
        <p class="h4 product-name">Coca-Cola Zero Sugar</p>
        <p class="product-description">versch. Sorten, Pack = 24 x 0,33 l (1 l = € 1.01)</p>
    </div>
</div>
<div class="product-box box-boxed">
    <div class="product-image-wrapper">
        <a href="/angebote/wasser/volvic-789">
            <img src="/img/volvic.jpg">
        </a>
    </div>
    <div class="product-info">
        <div class="product-price-wrapper">
            <p class="product-price">4.<sup>49</sup></p>
        </div>
        <p class="h4 product-name">Volvic Naturelle</p>
        <p class="product-description">versch. Sorten, 0,75 l Flasche (1 l = € 1.99)</p>
    </div>
</div>
</body></html>"""


class TestMockHTMLParsing:
    @pytest.fixture
    def adapter(self) -> TrinkgutAdapter:
        return TrinkgutAdapter()

    @pytest.fixture
    def offers(self, adapter):
        return adapter._parse_offers(_MOCK_HTML)

    def test_finds_all_products(self, offers):
        assert len(offers) == 3

    def test_source_is_trinkgut(self, offers):
        assert all(o.source == Supermarket.TRINKGUT for o in offers)

    def test_bitburger_price(self, offers):
        bitu = next(o for o in offers if "Bitburger" in o.name)
        assert bitu.sale_price == 12.99

    def test_bitburger_brand(self, offers):
        bitu = next(o for o in offers if "Bitburger" in o.name)
        assert bitu.brand == "BITBURGER"

    def test_bitburger_base_price(self, offers):
        bitu = next(o for o in offers if "Bitburger" in o.name)
        assert bitu.base_price_value == 1.64
        assert bitu.base_price_unit == "L"

    def test_bitburger_sales_unit(self, offers):
        bitu = next(o for o in offers if "Bitburger" in o.name)
        assert bitu.sales_unit_raw == "24 x 0,33 l Kasten"

    def test_coca_cola_base_price(self, offers):
        cola = next(o for o in offers if "Coca" in o.name)
        assert cola.base_price_value == 1.01

    def test_volvic_sales_unit(self, offers):
        volvic = next(o for o in offers if "Volvic" in o.name)
        assert volvic.sales_unit_raw == "0,75 l Flasche"

    def test_product_slug_from_href(self, offers):
        bitu = next(o for o in offers if "Bitburger" in o.name)
        assert "bitburger" in bitu.product_slug

    def test_image_url_is_absolute(self, offers):
        bitu = next(o for o in offers if "Bitburger" in o.name)
        assert bitu.image_url is not None
        assert bitu.image_url.startswith("https://")

    def test_category_ids(self, offers):
        assert all(o.category_ids == ["Angebote"] for o in offers)

    def test_no_valid_from_valid_until(self, offers):
        """Trinkgut liefert keine Datumsinformationen."""
        assert all(o.valid_from is None for o in offers)
        assert all(o.valid_until is None for o in offers)

    def test_empty_html_returns_empty_list(self, adapter):
        result = adapter._parse_offers("<html><body></body></html>")
        assert result == []
