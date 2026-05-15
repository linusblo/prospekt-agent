"""Tests für den Matcher: Wortgrenzen, Excludes, Dedup, Einheiten, Marken, Multi-Markt."""
from __future__ import annotations

import json
import pytest

from src.matching.matcher import Matcher, MatchedProduct
from src.matching.wishlist import Wishlist, WishlistItem


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def make_offer(
    name: str,
    brand: str | None = None,
    sale_price: float = 1.0,
    original_price: float | None = None,
    sales_unit_raw: str | None = None,
    sales_unit: dict | None = None,
    category_ids: list[str] | None = None,
    source: str = "aldi_nord",
) -> dict:
    if category_ids is None:
        category_ids = ["Angebote"]
    return {
        "source": source,
        "product_slug": f"{source}-{name.lower().replace(' ', '-')}",
        "name": name,
        "brand": brand,
        "short_description": None,
        "long_description": None,
        "sale_price": sale_price,
        "original_price": original_price,
        "discount_percent": round((original_price - sale_price) / original_price * 100, 1)
            if original_price else None,
        "base_price_value": None,
        "base_price_unit": None,
        "sales_unit_raw": sales_unit_raw,
        "sales_unit_json": json.dumps(sales_unit) if sales_unit else None,
        "is_deposit_product": 0,
        "deposit_value": None,
        "valid_from": None,
        "valid_until": None,
        "image_url": None,
        "category_ids": json.dumps(category_ids),
        "scraped_at": "2026-05-13T00:00:00+00:00",
    }


def matcher_for(item: WishlistItem, food_only: bool = False) -> Matcher:
    return Matcher(Wishlist(items=[item]), food_only=food_only)


# ---------------------------------------------------------------------------
# Wortgrenzen-Tests
# ---------------------------------------------------------------------------

class TestWordBoundaries:
    def test_milch_does_not_match_buttermilch(self):
        item = WishlistItem(name="Milch", keywords=["milch"])
        offers = [make_offer("Buttermilch")]
        assert matcher_for(item).match_item(item, offers) == []

    def test_milch_does_not_match_fruchtbuttermilch(self):
        item = WishlistItem(name="Milch", keywords=["milch"])
        offers = [make_offer("Fruchtbuttermilch")]
        assert matcher_for(item).match_item(item, offers) == []

    def test_butter_does_not_match_butternote(self):
        item = WishlistItem(name="Butter", keywords=["butter"])
        offers = [make_offer("Culinesse mit Butternote XXL")]
        assert matcher_for(item).match_item(item, offers) == []

    def test_butter_does_not_match_buttermilch(self):
        item = WishlistItem(name="Butter", keywords=["butter"])
        offers = [make_offer("Fruchtbuttermilch")]
        assert matcher_for(item).match_item(item, offers) == []

    def test_milch_matches_frische_milch(self):
        item = WishlistItem(name="Milch", keywords=["milch"])
        offers = [make_offer("Frische Milch")]
        assert len(matcher_for(item).match_item(item, offers)) == 1

    def test_butter_matches_standalone(self):
        item = WishlistItem(name="Butter", keywords=["butter"])
        offers = [make_offer("Frische Butter")]
        assert len(matcher_for(item).match_item(item, offers)) == 1

    def test_cola_matches_coca_cola(self):
        item = WishlistItem(name="Coca-Cola", keywords=["cola"])
        offers = [make_offer("Original Taste", brand="COCA-COLA")]
        assert len(matcher_for(item).match_item(item, offers)) == 1

    def test_description_not_searched(self):
        item = WishlistItem(name="Butter", keywords=["butter"])
        offers = [make_offer("Bourbon-Vanille-Waffeln")]
        assert matcher_for(item).match_item(item, offers) == []


# ---------------------------------------------------------------------------
# Exclude-Keywords-Tests
# ---------------------------------------------------------------------------

class TestExcludeKeywords:
    def test_excludes_buttermilch(self):
        item = WishlistItem(name="Milch", keywords=["milch"],
                            exclude_keywords=["buttermilch"])
        offers = [
            make_offer("Frische Milch"),
            make_offer("Buttermilch"),
        ]
        results = matcher_for(item).match_item(item, offers)
        names = [r.primary_offer["name"] for r in results]
        assert "Frische Milch" in names
        assert "Buttermilch" not in names

    def test_exclude_uses_word_boundary(self):
        item = WishlistItem(name="Butter", keywords=["butter"],
                            exclude_keywords=["bourbon"])
        offers = [
            make_offer("Butter"),
            make_offer("Bourbon Butter"),
        ]
        results = matcher_for(item).match_item(item, offers)
        names = [r.primary_offer["name"] for r in results]
        assert "Butter" in names
        assert "Bourbon Butter" not in names

    def test_multiple_excludes_any_triggers(self):
        item = WishlistItem(name="Butter", keywords=["butter"],
                            exclude_keywords=["vanille", "brioche"])
        offers = [
            make_offer("Butter"),
            make_offer("Vanille Butter"),
            make_offer("Brioche Butter"),
        ]
        results = matcher_for(item).match_item(item, offers)
        assert len(results) == 1
        assert results[0].primary_offer["name"] == "Butter"


# ---------------------------------------------------------------------------
# Deduplizierungs-Tests (Within-Market)
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_identical_name_price_unit_deduped(self):
        """Gleicher Artikel doppelt im selben Markt → ein MatchedProduct, count=2."""
        item = WishlistItem(name="Milch", keywords=["milch"])
        su = {"quantity": 1.0, "unit": "L", "packaging": "Packung",
              "multiplier": 1, "raw": "1-L-Packung"}
        offers = [
            make_offer("Frische Milch", brand="ARLA", sale_price=1.11,
                       sales_unit_raw="1-L-Packung", sales_unit=su),
            make_offer("Frische Milch", brand="ARLA", sale_price=1.11,
                       sales_unit_raw="1-L-Packung", sales_unit=su),
        ]
        results = matcher_for(item).match_item(item, offers)
        assert len(results) == 1
        assert results[0].primary_market_count == 2
        assert results[0].alternative_offers == []

    def test_different_price_same_source_not_merged(self):
        """Gleicher Name, verschiedener Preis, selbe Source → 2 separate MatchedProducts."""
        item = WishlistItem(name="Milch", keywords=["milch"])
        offers = [
            make_offer("Frische Milch", sale_price=1.11),
            make_offer("Frische Milch", sale_price=0.99),
        ]
        results = matcher_for(item).match_item(item, offers)
        assert len(results) == 2

    def test_duplicate_count_three(self):
        """Dreifach-Duplikat → ein MatchedProduct mit count=3."""
        item = WishlistItem(name="Cola", keywords=["cola"])
        offers = [make_offer("Cola", sale_price=0.99)] * 3
        results = matcher_for(item).match_item(item, offers)
        assert len(results) == 1
        assert results[0].primary_market_count == 3


# ---------------------------------------------------------------------------
# Einheiten-Filter-Tests
# ---------------------------------------------------------------------------

class TestUnitFilter:
    def _su(self, qty, unit, packaging="Packung", mult=1):
        raw = f"{qty}-{unit}-{packaging}"
        return {"quantity": qty, "unit": unit, "packaging": packaging,
                "multiplier": mult, "raw": raw}

    def test_kg_filter_matches_g_product(self):
        item = WishlistItem(name="Butter", keywords=["butter"],
                            unit_filter="kg", min_quantity=0.25)
        su = self._su(250.0, "g")
        offers = [make_offer("Butter", sales_unit_raw="250-g-Packung", sales_unit=su)]
        assert len(matcher_for(item).match_item(item, offers)) == 1

    def test_kg_filter_rejects_too_small_g_product(self):
        item = WishlistItem(name="Butter", keywords=["butter"],
                            unit_filter="kg", min_quantity=0.5)
        su = self._su(250.0, "g")
        offers = [make_offer("Butter", sales_unit_raw="250-g-Packung", sales_unit=su)]
        assert matcher_for(item).match_item(item, offers) == []

    def test_L_filter_matches_ml_product(self):
        item = WishlistItem(name="Milch", keywords=["milch"],
                            unit_filter="L", min_quantity=0.5)
        su = self._su(500.0, "ml")
        offers = [make_offer("Frische Milch", sales_unit_raw="500-ml-Packung", sales_unit=su)]
        assert len(matcher_for(item).match_item(item, offers)) == 1

    def test_L_filter_rejects_small_ml_product(self):
        item = WishlistItem(name="Milch", keywords=["milch"],
                            unit_filter="L", min_quantity=1.0)
        su = self._su(500.0, "ml")
        offers = [make_offer("Frische Milch", sales_unit_raw="500-ml-Packung", sales_unit=su)]
        assert matcher_for(item).match_item(item, offers) == []

    def test_unit_cross_family_rejected(self):
        item = WishlistItem(name="Produkt", keywords=["produkt"], unit_filter="kg")
        su = self._su(500.0, "ml")
        offers = [make_offer("Produkt", sales_unit=su)]
        assert matcher_for(item).match_item(item, offers) == []

    def test_multipack_total_quantity(self):
        item = WishlistItem(name="Cola", keywords=["cola"],
                            unit_filter="L", min_quantity=1.0)
        su = {"quantity": 1.5, "unit": "L", "packaging": "Flasche",
              "multiplier": 6, "raw": "6x1,5-L-Flasche"}
        offers = [make_offer("Cola", sales_unit=su)]
        assert len(matcher_for(item).match_item(item, offers)) == 1

    def test_g_filter_same_family_as_kg(self):
        item = WishlistItem(name="Butter", keywords=["butter"],
                            unit_filter="g", min_quantity=250)
        su = self._su(0.25, "kg")
        offers = [make_offer("Butter", sales_unit=su)]
        assert len(matcher_for(item).match_item(item, offers)) == 1


# ---------------------------------------------------------------------------
# Marken-Tests
# ---------------------------------------------------------------------------

class TestBrandMatching:
    def test_brand_case_insensitive(self):
        item = WishlistItem(name="Cola", keywords=["cola"], brand="coca-cola")
        offers = [
            make_offer("Original Taste", brand="COCA-COLA"),
            make_offer("Original Taste", brand="Pepsi"),
        ]
        results = matcher_for(item).match_item(item, offers)
        assert len(results) == 1
        assert results[0].primary_offer["brand"] == "COCA-COLA"

    def test_allowed_brands_or_logic(self):
        item = WishlistItem(name="Wasser", keywords=["wasser"],
                            allowed_brands=["VOLVIC", "EVIAN", "GEROLSTEINER"])
        offers = [
            make_offer("Stilles Wasser", brand="VOLVIC"),
            make_offer("Stilles Wasser", brand="EVIAN"),
            make_offer("Stilles Wasser", brand="REWE"),
        ]
        results = matcher_for(item).match_item(item, offers)
        assert len(results) == 2
        brands = {r.primary_offer["brand"] for r in results}
        assert brands == {"VOLVIC", "EVIAN"}

    def test_brand_and_allowed_brands_brand_takes_priority(self):
        item = WishlistItem(name="Cola", keywords=["cola"],
                            brand="COCA-COLA",
                            allowed_brands=["PEPSI"])
        offers = [
            make_offer("Cola", brand="COCA-COLA"),
            make_offer("Cola", brand="PEPSI"),
        ]
        results = matcher_for(item).match_item(item, offers)
        assert len(results) == 1
        assert results[0].primary_offer["brand"] == "COCA-COLA"


# ---------------------------------------------------------------------------
# Preis-/Rabatt-Tests
# ---------------------------------------------------------------------------

class TestPriceFilters:
    def test_max_price_filter(self):
        item = WishlistItem(name="Butter", keywords=["butter"], max_price=2.00)
        offers = [
            make_offer("Butter", sale_price=1.99),
            make_offer("Butter Premium", sale_price=2.50),
        ]
        results = matcher_for(item).match_item(item, offers)
        assert len(results) == 1
        assert results[0].primary_offer["sale_price"] == 1.99

    def test_min_discount_filter(self):
        item = WishlistItem(name="Cola", keywords=["cola"], min_discount_percent=20.0)
        offers = [
            make_offer("Cola 1", sale_price=0.99, original_price=1.59),   # ~37.7%
            make_offer("Cola 2", sale_price=1.39, original_price=1.59),   # ~12.6%
        ]
        results = matcher_for(item).match_item(item, offers)
        assert len(results) == 1
        assert results[0].primary_offer["name"] == "Cola 1"


# ---------------------------------------------------------------------------
# Food-Filter-Tests
# ---------------------------------------------------------------------------

class TestFoodFilter:
    def test_non_food_category_excluded(self):
        item = WishlistItem(name="Batterie", keywords=["batterie"])
        offers = [
            make_offer("Batterien AA", category_ids=["batterien-akkus-feuerzeuge"]),
        ]
        results = matcher_for(item, food_only=True).match_item(item, offers)
        assert results == []

    def test_food_category_passes(self):
        item = WishlistItem(name="Cola", keywords=["cola"])
        offers = [
            make_offer("Cola", category_ids=["Angebote", "cola-limo-schorlen"]),
        ]
        results = matcher_for(item, food_only=True).match_item(item, offers)
        assert len(results) == 1

    def test_explicit_categories_bypass_food_filter(self):
        item = WishlistItem(name="Schraube", keywords=["schraube"],
                            categories=["werkzeug"])
        offers = [
            make_offer("Schraube M8", category_ids=["werkzeug"]),
        ]
        results = matcher_for(item, food_only=True).match_item(item, offers)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Multi-Markt-Tests (Cross-Market-Grouping) — NEU
# ---------------------------------------------------------------------------

class TestCrossMarketGrouping:
    def test_same_product_two_markets_primary_is_cheaper(self):
        """
        Nutella: Aldi 2.99€ und Kaufland 3.19€
        → ein MatchedProduct, primary = Aldi (günstiger), Kaufland als Alternative
        """
        item = WishlistItem(name="Nutella", keywords=["nutella"])
        aldi    = make_offer("Nutella", brand="FERRERO", sale_price=2.99,
                             sales_unit_raw="450-g-Glas", source="aldi_nord")
        kaufland = make_offer("Nutella", brand="FERRERO", sale_price=3.19,
                              sales_unit_raw="450-g-Glas", source="kaufland")

        results = matcher_for(item).match_item(item, [aldi, kaufland])

        assert len(results) == 1
        assert results[0].primary_offer["sale_price"] == 2.99
        assert results[0].primary_offer["source"] == "aldi_nord"
        assert len(results[0].alternative_offers) == 1
        assert results[0].alternative_offers[0]["source"] == "kaufland"
        assert results[0].alternative_offers[0]["sale_price"] == 3.19

    def test_same_product_one_market_no_alternatives(self):
        """
        Butter nur bei Aldi → ein MatchedProduct ohne Alternativen.
        """
        item = WishlistItem(name="Butter", keywords=["butter"])
        offers = [make_offer("Frische Butter", brand="ARLA", sale_price=1.99)]

        results = matcher_for(item).match_item(item, offers)

        assert len(results) == 1
        assert results[0].alternative_offers == []
        assert results[0].primary_market_count == 1

    def test_three_different_products_three_matched_products(self):
        """
        Cola (Aldi), Milch (Kaufland), Butter (Aldi) — alle verschiedene Produkte
        → drei separate MatchedProducts, keins mit Cross-Market-Alternative.
        """
        item = WishlistItem(name="Lebensmittel", keywords=["cola", "milch", "butter"])
        offers = [
            make_offer("Cola",         brand="COCA-COLA", sale_price=0.99, source="aldi_nord"),
            make_offer("Frische Milch",brand="ARLA",      sale_price=1.11, source="kaufland"),
            make_offer("Frische Butter",brand="ARLA",     sale_price=1.99, source="aldi_nord"),
        ]

        results = matcher_for(item).match_item(item, offers)

        assert len(results) == 3
        # Alle ohne Cross-Market-Alternativen (jedes Produkt nur bei einem Markt)
        for r in results:
            assert r.alternative_offers == []

    def test_tied_price_any_is_primary(self):
        """
        Gleicher Preis bei beiden Märkten → irgendeiner wird primary,
        der andere alternative — keine Exception, stabile Ausgabe.
        """
        item = WishlistItem(name="Wasser", keywords=["wasser"])
        aldi     = make_offer("Stilles Wasser", sale_price=0.59,
                              sales_unit_raw="1-L-Flasche", source="aldi_nord")
        kaufland = make_offer("Stilles Wasser", sale_price=0.59,
                              sales_unit_raw="1-L-Flasche", source="kaufland")

        results = matcher_for(item).match_item(item, [aldi, kaufland])

        assert len(results) == 1
        assert results[0].primary_offer["sale_price"] == 0.59
        assert len(results[0].alternative_offers) == 1
        # Sicherstellen dass beide Sources vertreten sind
        all_sources = {results[0].primary_offer["source"],
                       results[0].alternative_offers[0]["source"]}
        assert all_sources == {"aldi_nord", "kaufland"}

    def test_return_type_is_matched_product(self):
        item = WishlistItem(name="Cola", keywords=["cola"])
        offers = [make_offer("Cola")]
        results = matcher_for(item).match_item(item, offers)
        assert all(isinstance(r, MatchedProduct) for r in results)
