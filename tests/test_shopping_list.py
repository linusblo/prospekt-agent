"""Tests für die Shopping-List-Persistierung."""
from __future__ import annotations

import pytest
from src.db.repository import OfferRepository


@pytest.fixture
def repo(tmp_path) -> OfferRepository:
    return OfferRepository(str(tmp_path / "test.db"))


def _offer(name: str = "Testprodukt", source: str = "aldi_nord", slug: str = "test-001") -> dict:
    return {
        "offer_source":    source,
        "offer_slug":      slug,
        "product_name":    name,
        "brand":           "TESTMARKE",
        "sale_price":      1.99,
        "original_price":  2.49,
        "base_price_text": "1.99 €/kg",
        "sales_unit":      "500 g",
        "market_name":     "Aldi Nord",
    }


class TestAddToShoppingList:
    def test_add_returns_id(self, repo):
        item_id = repo.add_to_shopping_list(_offer())
        assert isinstance(item_id, int)
        assert item_id > 0

    def test_add_persists_fields(self, repo):
        repo.add_to_shopping_list(_offer("Nutella", "kaufland", "nutella-001"))
        items = repo.get_shopping_list()
        assert len(items) == 1
        assert items[0]["product_name"] == "Nutella"
        assert items[0]["offer_source"] == "kaufland"
        assert items[0]["market_name"] == "Aldi Nord"

    def test_duplicate_ignored(self, repo):
        """Gleiche source+slug zweimal → nur ein Eintrag."""
        repo.add_to_shopping_list(_offer())
        repo.add_to_shopping_list(_offer())
        assert len(repo.get_shopping_list()) == 1

    def test_different_slugs_both_stored(self, repo):
        repo.add_to_shopping_list(_offer(slug="slug-a"))
        repo.add_to_shopping_list(_offer(slug="slug-b"))
        assert len(repo.get_shopping_list()) == 2


class TestRemoveFromShoppingList:
    def test_remove_by_id(self, repo):
        item_id = repo.add_to_shopping_list(_offer())
        repo.remove_from_shopping_list(item_id)
        assert repo.get_shopping_list() == []

    def test_remove_nonexistent_does_not_raise(self, repo):
        repo.remove_from_shopping_list(999)

    def test_remove_only_target(self, repo):
        id1 = repo.add_to_shopping_list(_offer(slug="a"))
        repo.add_to_shopping_list(_offer(slug="b"))
        repo.remove_from_shopping_list(id1)
        items = repo.get_shopping_list()
        assert len(items) == 1
        assert items[0]["offer_slug"] == "b"


class TestToggleChecked:
    def test_unchecked_becomes_checked(self, repo):
        item_id = repo.add_to_shopping_list(_offer())
        repo.toggle_checked(item_id)
        assert repo.get_shopping_list()[0]["checked"] == 1

    def test_checked_becomes_unchecked(self, repo):
        item_id = repo.add_to_shopping_list(_offer())
        repo.toggle_checked(item_id)
        repo.toggle_checked(item_id)
        assert repo.get_shopping_list()[0]["checked"] == 0


class TestClear:
    def test_clear_all(self, repo):
        repo.add_to_shopping_list(_offer(slug="a"))
        repo.add_to_shopping_list(_offer(slug="b"))
        repo.clear_shopping_list()
        assert repo.get_shopping_list() == []

    def test_clear_checked_only(self, repo):
        id1 = repo.add_to_shopping_list(_offer(slug="a"))
        repo.add_to_shopping_list(_offer(slug="b"))
        repo.toggle_checked(id1)          # mark "a" as checked
        repo.clear_checked_items()
        items = repo.get_shopping_list()
        assert len(items) == 1
        assert items[0]["offer_slug"] == "b"

    def test_clear_checked_empty_does_not_raise(self, repo):
        repo.clear_checked_items()


class TestIsOnShoppingList:
    def test_present(self, repo):
        repo.add_to_shopping_list(_offer(source="edeka", slug="xyz"))
        assert repo.is_on_shopping_list("edeka", "xyz") is True

    def test_absent(self, repo):
        assert repo.is_on_shopping_list("edeka", "xyz") is False

    def test_wrong_source(self, repo):
        repo.add_to_shopping_list(_offer(source="aldi_nord", slug="abc"))
        assert repo.is_on_shopping_list("kaufland", "abc") is False


class TestGetShoppingList:
    def test_sorted_by_market_then_name(self, repo):
        repo.add_to_shopping_list({**_offer("Zucker",  "aldi_nord",  "s1"), "market_name": "Aldi Nord"})
        repo.add_to_shopping_list({**_offer("Apfel",   "kaufland",   "s2"), "market_name": "Kaufland"})
        repo.add_to_shopping_list({**_offer("Banane",  "aldi_nord",  "s3"), "market_name": "Aldi Nord"})
        items = repo.get_shopping_list()
        names = [i["product_name"] for i in items]
        assert names == ["Banane", "Zucker", "Apfel"]  # Aldi A→Z, dann Kaufland
