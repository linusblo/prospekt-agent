"""Tests für KauflandBasePriceParser — alle echten Formate aus den Daten."""
from __future__ import annotations

import pytest

from src.models.kaufland_base_price_parser import KauflandBasePriceParser, ParsedBasePrice


@pytest.fixture
def parser() -> KauflandBasePriceParser:
    return KauflandBasePriceParser()


class TestSimpleFormats:
    def test_kg_single(self, parser):
        r = parser.parse("(1 kg = 5.70)")
        assert r.value == 5.70
        assert r.max_value is None
        assert r.unit == "kg"
        assert r.has_prefix is False

    def test_liter_single(self, parser):
        r = parser.parse("(1 l = 2.50)")
        assert r.value == 2.50
        assert r.unit == "L"          # normalisiert

    def test_gram_per_100(self, parser):
        r = parser.parse("(100 g = 0.59)")
        assert r.value == 0.59
        assert r.unit == "g"

    def test_ml_unit(self, parser):
        r = parser.parse("(100 ml = 0.75)")
        assert r.value == 0.75
        assert r.unit == "ml"

    def test_comma_decimal_separator(self, parser):
        r = parser.parse("(1 kg = 2,65)")
        assert r.value == 2.65
        assert r.unit == "kg"


class TestRangeFormats:
    def test_kg_range(self, parser):
        r = parser.parse("(1 kg = 5.70 - 11.10)")
        assert r.value == 5.70
        assert r.max_value == 11.10
        assert r.unit == "kg"
        assert r.has_prefix is False

    def test_range_comma_decimal(self, parser):
        r = parser.parse("(1 kg = 5,70 - 11,10)")
        assert r.value == 5.70
        assert r.max_value == 11.10

    def test_range_en_dash(self, parser):
        r = parser.parse("(1 kg = 5.70 – 11.10)")
        assert r.value == 5.70
        assert r.max_value == 11.10


class TestAbPrefix:
    def test_ab_with_euro(self, parser):
        r = parser.parse("(1 kg = ab € 5.08)")
        assert r.value == 5.08
        assert r.max_value is None
        assert r.has_prefix is True
        assert r.unit == "kg"

    def test_ab_without_euro(self, parser):
        r = parser.parse("(1 kg = ab 5.08)")
        assert r.value == 5.08
        assert r.has_prefix is True

    def test_ab_with_range(self, parser):
        r = parser.parse("(1 kg = ab 4.52 - 8.80)")
        assert r.value == 4.52
        assert r.max_value == 8.80
        assert r.has_prefix is True

    def test_ab_with_euro_and_range(self, parser):
        r = parser.parse("(1 kg = ab € 4.52 - 8.80)")
        assert r.value == 4.52
        assert r.max_value == 8.80
        assert r.has_prefix is True


class TestEdgeCases:
    def test_none_input(self, parser):
        r = parser.parse(None)
        assert r.value is None
        assert r.unit is None
        assert r.has_prefix is False

    def test_empty_string(self, parser):
        r = parser.parse("")
        assert r.value is None

    def test_unparseable_string(self, parser):
        r = parser.parse("Preis auf Anfrage")
        assert r.value is None
        assert r.unit is None

    def test_returns_parsed_base_price_instance(self, parser):
        r = parser.parse("(1 kg = 5.70)")
        assert isinstance(r, ParsedBasePrice)

    def test_no_prefix_flag_for_regular_price(self, parser):
        r = parser.parse("(1 kg = 5.70)")
        assert r.has_prefix is False

    def test_integer_price_value(self, parser):
        """Preis ohne Nachkommastellen (selten, aber möglich)."""
        r = parser.parse("(1 kg = 5)")
        assert r.value == 5.0
