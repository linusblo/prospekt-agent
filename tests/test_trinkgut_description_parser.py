"""Tests für TrinkgutDescriptionParser."""
from __future__ import annotations

import pytest

from src.models.trinkgut_description_parser import (
    TrinkgutDescriptionParser,
    ParsedDescription,
)


@pytest.fixture
def parser() -> TrinkgutDescriptionParser:
    return TrinkgutDescriptionParser()


class TestBasePriceParsing:
    def test_simple_liter_base_price(self, parser):
        r = parser.parse("0,5 l Dose (1 l = € 1.78) zzgl.")
        assert r.base_price_value == 1.78
        assert r.base_price_unit == "L"

    def test_base_price_with_versch_sorten(self, parser):
        r = parser.parse("versch. Sorten, 0,5 l Dose (1 l = € 1.78) zzgl.")
        assert r.base_price_value == 1.78

    def test_base_price_without_euro_sign(self, parser):
        r = parser.parse("0,5 l Flasche (1 l = 1.50)")
        assert r.base_price_value == 1.50
        assert r.base_price_unit == "L"

    def test_base_price_comma_decimal(self, parser):
        r = parser.parse("0,5 l Dose (1 l = € 2,27)")
        assert r.base_price_value == 2.27

    def test_no_base_price_returns_none(self, parser):
        r = parser.parse("0,5 l Dose zzgl. Pfand")
        assert r.base_price_value is None
        assert r.base_price_unit is None

    def test_base_price_unit_normalized_to_uppercase_L(self, parser):
        r = parser.parse("(1 l = 1.50)")
        assert r.base_price_unit == "L"     # "l" → "L"

    def test_base_price_kg_unit(self, parser):
        r = parser.parse("500 g Packung (1 kg = 3.80)")
        assert r.base_price_value == 3.80
        assert r.base_price_unit == "kg"


class TestSalesUnitExtraction:
    def test_dose_simple(self, parser):
        r = parser.parse("0,5 l Dose (1 l = € 1.78) zzgl.")
        assert r.sales_unit_raw == "0,5 l Dose"

    def test_versch_sorten_prefix_removed(self, parser):
        r = parser.parse("versch. Sorten, 0,5 l Dose (1 l = € 1.78) zzgl.")
        assert r.sales_unit_raw == "0,5 l Dose"

    def test_kasten_format_reordered(self, parser):
        r = parser.parse(
            "versch. Sorten, Kasten = 20 x 0,5 l / 24 x 0,33 l (1 l = € 2.27) zzgl. 0.25 Pfand"
        )
        assert r.sales_unit_raw == "20 x 0,5 l Kasten"

    def test_multiple_variants_takes_first(self, parser):
        """Wenn "/" im Text → erste Variante nehmen."""
        r = parser.parse("Kasten = 20 x 0,5 l / 24 x 0,33 l (1 l = € 2.27)")
        assert "24" not in (r.sales_unit_raw or "")
        assert "20 x 0,5 l" in (r.sales_unit_raw or "")

    def test_pack_format_reordered(self, parser):
        r = parser.parse("Pack = 6 x 0,33 l (1 l = € 2.02) zzgl.")
        assert r.sales_unit_raw == "6 x 0,33 l Pack"


class TestEdgeCases:
    def test_none_input(self, parser):
        r = parser.parse(None)
        assert r.sales_unit_raw is None
        assert r.base_price_value is None

    def test_empty_string(self, parser):
        r = parser.parse("")
        assert r.sales_unit_raw is None
        assert r.base_price_value is None

    def test_returns_parsed_description_instance(self, parser):
        r = parser.parse("0,5 l Dose (1 l = € 1.78)")
        assert isinstance(r, ParsedDescription)

    def test_no_paren_in_description(self, parser):
        r = parser.parse("0,5 l Dose zzgl. Pfand")
        assert r.sales_unit_raw == "0,5 l Dose zzgl. Pfand"
        assert r.base_price_value is None
