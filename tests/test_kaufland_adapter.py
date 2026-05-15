"""Tests für den Kaufland-Adapter: Mapping, HTML-Extraktion, Hilfsfunktionen."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.adapters.kaufland import (
    KauflandAdapter,
    _parse_price_str,
    _parse_date_str,
    _find_offers_recursive,
    _normalize_brand,
)
from src.models.offer import Supermarket


# ---------------------------------------------------------------------------
# _parse_price_str
# ---------------------------------------------------------------------------

class TestParsePriceStr:
    def test_german_comma(self):
        assert _parse_price_str("2,29 €") == 2.29

    def test_dot_decimal(self):
        assert _parse_price_str("1.11") == 1.11

    def test_asterisk_suffix(self):
        assert _parse_price_str("0.88*") == 0.88

    def test_none(self):
        assert _parse_price_str(None) is None

    def test_empty(self):
        assert _parse_price_str("") is None

    def test_no_number(self):
        assert _parse_price_str("Preis unbekannt") is None


# ---------------------------------------------------------------------------
# _parse_date_str
# ---------------------------------------------------------------------------

class TestParseDateStr:
    def test_iso_date(self):
        dt = _parse_date_str("2026-05-16")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 5
        assert dt.day == 16
        assert dt.tzinfo == timezone.utc

    def test_none(self):
        assert _parse_date_str(None) is None

    def test_empty(self):
        assert _parse_date_str("") is None

    def test_invalid_format(self):
        assert _parse_date_str("16.05.2026") is None


# ---------------------------------------------------------------------------
# _find_offers_recursive
# ---------------------------------------------------------------------------

class TestFindOffersRecursive:
    def test_flat_list(self):
        data = [{"offerId": "1", "title": "Test"}]
        assert _find_offers_recursive(data) == data

    def test_nested_in_dict(self):
        data = {"meta": {"offers": [{"offerId": "1"}]}}
        result = _find_offers_recursive(data)
        assert result[0]["offerId"] == "1"

    def test_nested_in_list(self):
        data = [{"type": "wrapper", "items": [{"offerId": "2"}]}]
        result = _find_offers_recursive(data)
        assert result[0]["offerId"] == "2"

    def test_empty_returns_empty(self):
        assert _find_offers_recursive({}) == []
        assert _find_offers_recursive([]) == []

    def test_depth_limit(self):
        deep: dict = {}
        node = deep
        for _ in range(12):
            node["child"] = {}
            node = node["child"]
        node["offers"] = [{"offerId": "deep"}]
        result = _find_offers_recursive(deep)
        assert result == []


# ---------------------------------------------------------------------------
# _normalize_brand
# ---------------------------------------------------------------------------

class TestNormalizeBrand:
    def test_strips_whitespace(self):
        assert _normalize_brand("  ARLA  ") == "ARLA"

    def test_none_returns_none(self):
        assert _normalize_brand(None) is None

    def test_empty_returns_none(self):
        assert _normalize_brand("") is None

    def test_normalizes_typographic_apostrophe(self):
        result = _normalize_brand("TRADER JOE’S")
        assert result == "TRADER JOE'S"


# ---------------------------------------------------------------------------
# _map_to_offer
# ---------------------------------------------------------------------------

_SAMPLE_RAW = {
    "offerId":                    "kl-001",
    "title":                      "PHILADELPHIA",
    "subtitle":                   "Frischkäsezubereitung",
    "price":                      1.11,
    "discount":                   51,
    "basePrice":                  "(1 kg = 5.70 - 11.10)",
    "formattedOldPrice":          "2,29 €",
    "unit":                       "200-g-Packung",
    "detailDescription":          "Verschiedene Sorten",
    "listImage":                  "https://example.com/img.jpg",
    "loyaltyFormattedPrice":      "0.88*",
    "loyaltyFormattedBasePrice":  "(1 kg = 4.52 - 8.80)",
    "loyaltyDiscount":            60,
    "dateFrom":                   "2026-05-13",
    "dateTo":                     "2026-05-16",
    "klNr":                       "001",
    "country":                    "DE",
}


class TestMapToOffer:
    @pytest.fixture
    def adapter(self) -> KauflandAdapter:
        return KauflandAdapter()

    @pytest.fixture
    def offer(self, adapter):
        return adapter._map_to_offer(_SAMPLE_RAW, datetime.now(timezone.utc))

    def test_source(self, offer):
        assert offer.source == Supermarket.KAUFLAND

    def test_product_slug(self, offer):
        assert offer.product_slug == "kl-001"

    def test_name_from_subtitle(self, offer):
        assert offer.name == "Frischkäsezubereitung"

    def test_brand_from_title(self, offer):
        assert offer.brand == "PHILADELPHIA"

    def test_sale_price(self, offer):
        assert offer.sale_price == 1.11

    def test_original_price(self, offer):
        assert offer.original_price == 2.29

    def test_discount_percent(self, offer):
        assert offer.discount_percent == 51.0

    def test_base_price_value_lower(self, offer):
        assert offer.base_price_value == 5.70

    def test_base_price_value_max(self, offer):
        assert offer.base_price_value_max == 11.10

    def test_base_price_unit(self, offer):
        assert offer.base_price_unit == "kg"

    def test_base_price_has_prefix_false(self, offer):
        assert offer.base_price_has_prefix is False

    def test_card_price(self, offer):
        assert offer.card_price == 0.88

    def test_card_base_price_value(self, offer):
        assert offer.card_base_price_value == 4.52

    def test_card_base_price_value_max(self, offer):
        assert offer.card_base_price_value_max == 8.80

    def test_card_discount_percent(self, offer):
        assert offer.card_discount_percent == 60.0

    def test_valid_dates(self, offer):
        assert offer.valid_from is not None
        assert offer.valid_until is not None
        assert offer.valid_from.day == 13
        assert offer.valid_until.day == 16

    def test_image_url(self, offer):
        assert offer.image_url == "https://example.com/img.jpg"

    def test_category_ids_default(self, offer):
        assert offer.category_ids == ["Angebote"]

    def test_title_only_when_no_subtitle(self, adapter):
        raw = {**_SAMPLE_RAW, "subtitle": ""}
        offer = adapter._map_to_offer(raw, datetime.now(timezone.utc))
        assert offer.name == "PHILADELPHIA"

    def test_ab_prefix_stored(self, adapter):
        raw = {**_SAMPLE_RAW, "basePrice": "(1 kg = ab € 5.08)"}
        offer = adapter._map_to_offer(raw, datetime.now(timezone.utc))
        assert offer.base_price_has_prefix is True
        assert offer.base_price_value == 5.08


# ---------------------------------------------------------------------------
# HTML-Extraktion mit Mock-HTML
# ---------------------------------------------------------------------------

def _make_html(embedding: str) -> str:
    return f"""<!DOCTYPE html>
<html><head></head><body>
{embedding}
</body></html>"""


_OFFERS_LIST = json.dumps([
    {"offerId": "kl-001", "title": "ARLA", "subtitle": "Butter", "price": 1.99,
     "discount": 20, "basePrice": "(1 kg = 7.96)", "unit": "250-g-Packung",
     "dateFrom": "2026-05-13", "dateTo": "2026-05-16"},
    {"offerId": "kl-002", "title": "MILSANI", "subtitle": "Vollmilch", "price": 0.99,
     "discount": 10, "basePrice": "(1 l = 0.99)", "unit": "1-L-Packung",
     "dateFrom": "2026-05-13", "dateTo": "2026-05-16"},
])


class TestExtractOffersJson:
    @pytest.fixture
    def adapter(self) -> KauflandAdapter:
        return KauflandAdapter()

    def test_pure_json_script_tag(self, adapter):
        html = _make_html(f'<script type="application/json">{_OFFERS_LIST}</script>')
        result = adapter._parse_offers(html)
        assert len(result) == 2
        assert result[0].name == "Butter"

    def test_json_in_wrapper_object(self, adapter):
        wrapped = json.dumps({"version": 1, "offers": json.loads(_OFFERS_LIST)})
        html = _make_html(f'<script type="application/json">{wrapped}</script>')
        result = adapter._parse_offers(html)
        assert len(result) == 2

    def test_inline_js_variable(self, adapter):
        html = _make_html(f'<script>window.OFFERS_DATA = {_OFFERS_LIST};</script>')
        result = adapter._parse_offers(html)
        assert len(result) == 2

    def test_no_offers_returns_empty(self, adapter):
        html = _make_html("<script>var x = 1;</script>")
        result = adapter._parse_offers(html)
        assert result == []

    def test_fields_mapped_correctly(self, adapter):
        html = _make_html(f'<script type="application/json">{_OFFERS_LIST}</script>')
        offers = adapter._parse_offers(html)
        butter = next(o for o in offers if o.name == "Butter")
        assert butter.brand == "ARLA"
        assert butter.sale_price == 1.99
        assert butter.discount_percent == 20.0
        assert butter.base_price_value == 7.96
        assert butter.base_price_unit == "kg"
        assert butter.base_price_value_max is None
