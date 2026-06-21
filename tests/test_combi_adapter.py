"""
Tests für den Combi-Adapter (Bonial-API) — kein Netzwerkzugriff, alles
über konstruierte Raw-Dicts wie sie die Bonial-API liefert.

Getestete Bereiche:
  - _deal_amount:            Preis-Extraktion nach Deal-Typ
  - _parse_price_by_base_unit: uneinheitliche Grundpreis-Formate
  - _parse_iso:              ISO-Datum mit Offset ohne Doppelpunkt
  - _map_offer:               vollständiges Offer-Mapping inkl. Edge Cases
  - _parse_offer_list:        Liste roher Offers → Offer-Objekte (fehlertolerant)
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.adapters.combi import (
    CombiAdapter,
    _deal_amount,
    _map_offer,
    _parse_iso,
    _parse_offer_list,
    _parse_price_by_base_unit,
)
from src.models.offer import Supermarket

_NOW = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# _deal_amount
# ---------------------------------------------------------------------------

class TestDealAmount:
    def test_findet_sales_price(self):
        deals = [{"type": "SALES_PRICE", "minAmount": 1.79}]
        assert _deal_amount(deals, "SALES_PRICE") == 1.79

    def test_ignoriert_anderen_typ(self):
        deals = [{"type": "REGULAR_PRICE", "minAmount": 3.49}]
        assert _deal_amount(deals, "SALES_PRICE") is None

    def test_ignoriert_null_preis(self):
        """OTHER-Deals (Deko-Banner) haben minAmount 0 → kein echter Preis."""
        deals = [{"type": "OTHER", "minAmount": 0.0}]
        assert _deal_amount(deals, "OTHER") is None

    def test_leere_liste(self):
        assert _deal_amount([], "SALES_PRICE") is None


# ---------------------------------------------------------------------------
# _parse_price_by_base_unit
# ---------------------------------------------------------------------------

class TestParsePriceByBaseUnit:
    def test_gleichheitszeichen_format(self):
        deals = [{"type": "SALES_PRICE", "priceByBaseUnit": "1 kg = 6.90"}]
        val, unit = _parse_price_by_base_unit(deals)
        assert val == 6.90
        assert unit == "kg"

    def test_ab_format(self):
        deals = [{"type": "SALES_PRICE", "priceByBaseUnit": "1 l ab 7.52"}]
        val, unit = _parse_price_by_base_unit(deals)
        assert val == 7.52
        assert unit == "L"

    def test_geklammertes_format(self):
        deals = [{"type": "SALES_PRICE", "priceByBaseUnit": "(1 kg = 12.90)"}]
        val, unit = _parse_price_by_base_unit(deals)
        assert val == 12.90
        assert unit == "kg"

    def test_fallback_auf_special_price(self):
        deals = [
            {"type": "SALES_PRICE", "priceByBaseUnit": ""},
            {"type": "SPECIAL_PRICE", "priceByBaseUnit": "1 kg = 5.56"},
        ]
        val, unit = _parse_price_by_base_unit(deals)
        assert val == 5.56
        assert unit == "kg"

    def test_kein_grundpreis(self):
        deals = [{"type": "SALES_PRICE", "priceByBaseUnit": ""}]
        val, unit = _parse_price_by_base_unit(deals)
        assert val is None
        assert unit is None


# ---------------------------------------------------------------------------
# _parse_iso
# ---------------------------------------------------------------------------

class TestParseIso:
    def test_standard_format(self):
        dt = _parse_iso("2026-06-21T22:00:00.000+0000")
        assert dt is not None
        assert dt.year == 2026 and dt.month == 6 and dt.day == 21

    def test_none_input(self):
        assert _parse_iso(None) is None

    def test_leerer_string(self):
        assert _parse_iso("") is None

    def test_ungueltiges_format(self):
        assert _parse_iso("nicht-ein-datum") is None


# ---------------------------------------------------------------------------
# _map_offer
# ---------------------------------------------------------------------------

def _raw_offer(**overrides) -> dict:
    """Baut ein realistisches Bonial-Raw-Offer (Philadelphia-Beispiel)."""
    base = {
        "id": "43778de7-6978-455d-bd11-aff2d292c6b0",
        "products": [{
            "brandName": "Philadelphia",
            "name": "Frischkäsezubereitung",
            "description": ["versch. Sorten \n175/195-g-Becher"],
            "images": ["https://content-media.bonial.biz/abc/main.jpg"],
        }],
        "deals": [
            {"type": "REGULAR_PRICE", "minAmount": 3.49},
            {"type": "SALES_PRICE", "minAmount": 1.79},
            {
                "type": "SPECIAL_PRICE",
                "minAmount": 1.39,
                "conditions": [{"other": "MOIN CARD"}],
                "priceByBaseUnit": "1 kg = 5.56",
            },
        ],
        "validFrom": "2026-06-21T22:00:00.000+0000",
        "validUntil": "2026-06-27T20:00:00.000+0000",
        "image": "https://content-media.bonial.biz/abc/main.jpg",
    }
    base.update(overrides)
    return base


class TestMapOffer:
    def test_titel_mit_marke(self):
        offer = _map_offer(_raw_offer(), _NOW)
        assert offer.name == "Philadelphia Frischkäsezubereitung"

    def test_titel_ohne_marke(self):
        raw = _raw_offer()
        raw["products"][0]["brandName"] = None
        offer = _map_offer(raw, _NOW)
        assert offer.name == "Frischkäsezubereitung"

    def test_brand_feld(self):
        offer = _map_offer(_raw_offer(), _NOW)
        assert offer.brand == "Philadelphia"

    def test_sale_price_aus_sales_price(self):
        offer = _map_offer(_raw_offer(), _NOW)
        assert offer.sale_price == 1.79

    def test_original_price_aus_regular_price(self):
        offer = _map_offer(_raw_offer(), _NOW)
        assert offer.original_price == 3.49

    def test_card_price_aus_special_price(self):
        """SPECIAL_PRICE neben SALES_PRICE → Karten-Preis."""
        offer = _map_offer(_raw_offer(), _NOW)
        assert offer.card_price == 1.39

    def test_special_price_allein_wird_hauptpreis(self):
        """Ohne SALES_PRICE wird SPECIAL_PRICE zum Hauptpreis, kein card_price."""
        raw = _raw_offer(deals=[
            {"type": "REGULAR_PRICE", "minAmount": 3.99},
            {"type": "SPECIAL_PRICE", "minAmount": 2.99},
        ])
        offer = _map_offer(raw, _NOW)
        assert offer.sale_price == 2.99
        assert offer.card_price is None

    def test_description_bereinigt(self):
        offer = _map_offer(_raw_offer(), _NOW)
        assert offer.short_description == "versch. Sorten  175/195-g-Becher"

    def test_base_price(self):
        offer = _map_offer(_raw_offer(), _NOW)
        assert offer.base_price_value == 5.56
        assert offer.base_price_unit == "kg"

    def test_image_aus_products(self):
        offer = _map_offer(_raw_offer(), _NOW)
        assert offer.image_url == "https://content-media.bonial.biz/abc/main.jpg"

    def test_image_fallback_auf_top_level(self):
        raw = _raw_offer()
        raw["products"][0]["images"] = []
        offer = _map_offer(raw, _NOW)
        assert offer.image_url == "https://content-media.bonial.biz/abc/main.jpg"

    def test_valid_from_until(self):
        offer = _map_offer(_raw_offer(), _NOW)
        assert offer.valid_from.day == 21
        assert offer.valid_until.day == 27

    def test_source_ist_combi(self):
        offer = _map_offer(_raw_offer(), _NOW)
        assert offer.source == Supermarket.COMBI

    def test_product_slug_ist_offer_id(self):
        offer = _map_offer(_raw_offer(), _NOW)
        assert offer.product_slug == "43778de7-6978-455d-bd11-aff2d292c6b0"

    def test_category_ids(self):
        offer = _map_offer(_raw_offer(), _NOW)
        assert offer.category_ids == ["Angebote"]

    # ── Edge Cases ──────────────────────────────────────────────────────

    def test_keine_id_wird_uebersprungen(self):
        raw = _raw_offer(id=None)
        assert _map_offer(raw, _NOW) is None

    def test_keine_products_wird_uebersprungen(self):
        raw = _raw_offer(products=[])
        assert _map_offer(raw, _NOW) is None

    def test_leerer_name_wird_uebersprungen(self):
        raw = _raw_offer()
        raw["products"][0]["name"] = ""
        assert _map_offer(raw, _NOW) is None

    def test_deko_banner_ohne_preis_wird_uebersprungen(self):
        """OTHER-Deal-Typ mit minAmount 0 (Rubrik-Banner) → kein Offer."""
        raw = _raw_offer(
            deals=[{"type": "OTHER", "minAmount": 0.0, "priceByBaseUnit": ""}],
        )
        assert _map_offer(raw, _NOW) is None

    def test_recommended_retail_price_als_fallback(self):
        raw = _raw_offer(deals=[
            {"type": "SALES_PRICE", "minAmount": 17.99},
            {"type": "RECOMMENDED_RETAIL_PRICE", "minAmount": 39.99},
        ])
        offer = _map_offer(raw, _NOW)
        assert offer.original_price == 39.99


# ---------------------------------------------------------------------------
# _parse_offer_list
# ---------------------------------------------------------------------------

class TestParseOfferList:
    def test_filtert_ungueltige_offers(self):
        raw_list = [
            _raw_offer(),
            {"id": "deko-1", "products": [], "deals": []},  # kein Produkt
            {"id": None, "products": [{"name": "x"}], "deals": []},  # keine ID
        ]
        offers = _parse_offer_list(raw_list, _NOW)
        assert len(offers) == 1

    def test_fehlerhafter_eintrag_bricht_nicht_ab(self):
        """Ein kaputter Eintrag (kein dict-Zugriff möglich) darf andere nicht stoppen."""
        raw_list = [None, _raw_offer()]
        offers = _parse_offer_list(raw_list, _NOW)
        assert len(offers) == 1

    def test_leere_liste(self):
        assert _parse_offer_list([], _NOW) == []


# ---------------------------------------------------------------------------
# CombiAdapter
# ---------------------------------------------------------------------------

class TestCombiAdapter:
    def test_source_name(self):
        adapter = CombiAdapter()
        assert adapter.source_name == "combi"
        assert adapter.source_name == Supermarket.COMBI.value

    def test_default_ids(self):
        adapter = CombiAdapter()
        assert adapter._store_id == "DE-1031632951"
        assert adapter._publisher_id == "DE-42265682"

    def test_custom_ids(self):
        adapter = CombiAdapter("DE-9999999999", "DE-1111111111")
        assert adapter._store_id == "DE-9999999999"
        assert adapter._publisher_id == "DE-1111111111"
