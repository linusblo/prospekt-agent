"""Tests für resolve_brand — mindestens 20 Fälle aus echten Trinkgut-Daten."""
from __future__ import annotations

import pytest
from src.utils.brand_resolver import resolve_brand


class TestKnownBrandsMatch:
    """Treffer aus KNOWN_BRANDS → korrekte Marke."""

    def test_bitburger(self):
        assert resolve_brand("Bitburger Pils") == "BITBURGER"

    def test_krombacher(self):
        assert resolve_brand("Krombacher Pils Frische Fässchen") == "KROMBACHER"

    def test_veltins(self):
        assert resolve_brand("Veltins Pilsener") == "VELTINS"

    def test_brinkhoffs_with_apostrophe(self):
        # Brinkhoff's hat typografischen Apostroph → normalisiert
        assert resolve_brand("Brinkhoff's") == "BRINKHOFF'S"

    def test_bacardi(self):
        assert resolve_brand("Bacardi Rum") == "BACARDI"

    def test_monster(self):
        assert resolve_brand("Monster Energy Drink") == "MONSTER"

    def test_gerolsteiner(self):
        assert resolve_brand("Gerolsteiner Mineralwasser") == "GEROLSTEINER"

    def test_chivas_regal_multi_word(self):
        assert resolve_brand("Chivas Regal") == "CHIVAS REGAL"

    def test_glenfiddich(self):
        assert resolve_brand("Glenfiddich") == "GLENFIDDICH"

    def test_freixenet_with_trailing_comma(self):
        """Trinkgut schreibt manchmal 'Freixenet, Mionetto o. ...' — Komma direkt nach Marke."""
        assert resolve_brand("Freixenet, Mionetto o. Fürst von Metternich Chardonnay") == "FREIXENET"


class TestBrandNameOverrides:
    """Multi-Wort-Marken aus BRAND_NAME_OVERRIDES."""

    def test_jules_mumm(self):
        assert resolve_brand("Jules Mumm Sekt") == "JULES MUMM"

    def test_don_simon(self):
        assert resolve_brand("Don Simon Sangria Premium o. Saluti Vino Frizzante") == "DON SIMON"

    def test_thomas_henry(self):
        assert resolve_brand("Thomas Henry Bittergetränke") == "THOMAS HENRY"

    def test_three_sixty_vodka(self):
        assert resolve_brand("Three Sixty Vodka") == "THREE SIXTY"

    def test_the_real_cola(self):
        assert resolve_brand("The Real Cola o. Limonaden") == "THE REAL COLA"

    def test_hb_muenchen(self):
        assert resolve_brand("HB München Maibock") == "HB MÜNCHEN"

    def test_wodka_gorbatschow_override(self):
        """'Wodka' ist Skip-Wort, Gorbatschow ist die echte Marke."""
        assert resolve_brand("Wodka Gorbatschow") == "GORBATSCHOW"

    def test_9_mile(self):
        assert resolve_brand("9 Mile Vodka") == "9 MILE"


class TestFallbackHeuristic:
    """Fallback wenn kein KNOWN_BRANDS-Treffer → erstes nicht-skipbares Wort."""

    def test_deutschland_skipped(self):
        """'Deutschland' ist geografisch → überspringen, nächstes Wort nehmen."""
        result = resolve_brand("Deutschland - Rheinhessen - Weingenuss Dornfelder Rotwein")
        assert result is not None
        assert result != "DEUTSCHLAND"
        assert result != ""

    def test_italien_skipped(self):
        """'Italien' ist geografisch → überspringen."""
        result = resolve_brand("Italien - Leonardi")
        assert result is not None
        assert result != "ITALIEN"

    def test_schofferhofer(self):
        """Schöfferhofer ist bekannte Marke."""
        assert resolve_brand("Schöfferhofer Hefeweizen o. Weizen-Mix") == "SCHÖFFERHOFER"

    def test_boente_with_apostrophe(self):
        assert resolve_brand("Boente's Waldgeist") == "BOENTE'S"


class TestEdgeCases:
    def test_empty_string_returns_none(self):
        assert resolve_brand("") is None

    def test_none_like_whitespace_returns_none(self):
        assert resolve_brand("   ") is None

    def test_result_is_always_uppercase(self):
        result = resolve_brand("Bitburger Pils")
        assert result == result.upper()

    def test_single_word_brand(self):
        assert resolve_brand("Glenfiddich") == "GLENFIDDICH"

    def test_multiple_alternative_products_comma_separated(self):
        """Trinkgut listet oft 'Marke A o. Marke B' — erste Marke nehmen."""
        result = resolve_brand("Bacardi Rum o. Captain Morgan Spiced")
        assert result == "BACARDI"
