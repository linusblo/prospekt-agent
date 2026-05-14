import pytest
from src.models.sales_unit_parser import SalesUnitParser


@pytest.fixture
def parser() -> SalesUnitParser:
    return SalesUnitParser()


class TestBasicParsing:
    def test_liter_flasche(self, parser):
        r = parser.parse("1,25-L-Flasche")
        assert r.quantity == 1.25
        assert r.unit == "L"
        assert r.packaging == "Flasche"
        assert r.multiplier == 1
        assert r.raw == "1,25-L-Flasche"

    def test_ml_dose(self, parser):
        r = parser.parse("500-ml-Dose")
        assert r.quantity == 500.0
        assert r.unit == "ml"
        assert r.packaging == "Dose"

    def test_kg_beutel(self, parser):
        r = parser.parse("2-kg-Beutel")
        assert r.quantity == 2.0
        assert r.unit == "kg"
        assert r.packaging == "Beutel"

    def test_liter_long_form(self, parser):
        r = parser.parse("1-Liter-Packung")
        assert r.quantity == 1.0
        assert r.unit == "L"

    def test_decimal_with_dot(self, parser):
        r = parser.parse("1.5-L-Flasche")
        assert r.quantity == 1.5
        assert r.unit == "L"

    def test_gramm(self, parser):
        r = parser.parse("250-g-Glas")
        assert r.quantity == 250.0
        assert r.unit == "g"
        assert r.packaging == "Glas"


class TestMultipack:
    def test_sixpack_flasche(self, parser):
        r = parser.parse("6x1,5-L-Flasche")
        assert r.multiplier == 6
        assert r.quantity == 1.5
        assert r.unit == "L"
        assert r.packaging == "Flasche"

    def test_uppercase_x(self, parser):
        r = parser.parse("4X500-ml-Dose")
        assert r.multiplier == 4
        assert r.quantity == 500.0
        assert r.unit == "ml"


class TestEdgeCases:
    def test_empty_string(self, parser):
        r = parser.parse("")
        assert r.raw == ""
        assert r.quantity is None
        assert r.unit is None

    def test_unknown_input_does_not_raise(self, parser):
        r = parser.parse("irgendwas komisches")
        assert r.raw == "irgendwas komisches"

    def test_raw_always_preserved(self, parser):
        raw = "3x0,33-L-Dose"
        r = parser.parse(raw)
        assert r.raw == raw
