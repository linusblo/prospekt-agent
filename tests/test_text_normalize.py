"""Tests für normalize_for_matching."""
from src.utils.text_normalize import normalize_for_matching


class TestNormalizeForMatching:
    def test_hyphen_to_space(self):
        assert normalize_for_matching("COCA-COLA") == "coca cola"

    def test_comma_separated_brands(self):
        assert normalize_for_matching("COCA-COLA, FANTA, SPRITE") == "coca cola fanta sprite"

    def test_buttermilch_unchanged_no_hyphen(self):
        """Kompositum ohne Bindestrich bleibt ein Wort."""
        assert normalize_for_matching("Buttermilch") == "buttermilch"

    def test_empty_string(self):
        assert normalize_for_matching("") == ""

    def test_slash_to_space(self):
        assert normalize_for_matching("Light/Zero") == "light zero"

    def test_period_to_space(self):
        assert normalize_for_matching("Dr. Oetker") == "dr oetker"

    def test_multiple_spaces_collapsed(self):
        assert normalize_for_matching("Cola  Zero") == "cola zero"

    def test_lowercase_conversion(self):
        assert normalize_for_matching("ARLA") == "arla"

    def test_mixed_separators(self):
        assert normalize_for_matching("Three-Sixty, Vodka/Gin") == "three sixty vodka gin"

    def test_frische_milch_unchanged(self):
        """Einfacher Produktname ohne Sonderzeichen."""
        assert normalize_for_matching("Frische Milch") == "frische milch"

    def test_trailing_whitespace_stripped(self):
        assert normalize_for_matching("  cola  ") == "cola"
