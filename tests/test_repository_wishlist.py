"""Tests für Wishlist-CRUD-Operationen im OfferRepository."""
from __future__ import annotations

import pytest
import sqlite3

from src.db.repository import OfferRepository
from src.matching.wishlist import WishlistItem


@pytest.fixture
def repo(tmp_path) -> OfferRepository:
    return OfferRepository(str(tmp_path / "test.db"))


@pytest.fixture
def item_a() -> WishlistItem:
    return WishlistItem(
        name="Coca-Cola",
        allowed_brands=["COCA-COLA"],
        keywords=["cola"],
        max_price=2.00,
        unit_filter="L",
        active=True,
    )


@pytest.fixture
def item_b() -> WishlistItem:
    return WishlistItem(
        name="Butter",
        keywords=["butter"],
        max_price=2.50,
        active=False,
    )


# ---------------------------------------------------------------------------
# add_wishlist_item
# ---------------------------------------------------------------------------

class TestAddWishlistItem:
    def test_returns_int_id(self, repo, item_a):
        item_id = repo.add_wishlist_item(item_a)
        assert isinstance(item_id, int)
        assert item_id >= 1

    def test_item_retrievable_after_add(self, repo, item_a):
        repo.add_wishlist_item(item_a)
        items = repo.get_wishlist_items()
        assert len(items) == 1
        assert items[0].name == "Coca-Cola"
        assert items[0].allowed_brands == ["COCA-COLA"]
        assert items[0].max_price == 2.00

    def test_duplicate_name_raises_integrity_error(self, repo, item_a):
        repo.add_wishlist_item(item_a)
        with pytest.raises(sqlite3.IntegrityError):
            repo.add_wishlist_item(item_a)

    def test_inactive_item_stored_correctly(self, repo, item_b):
        repo.add_wishlist_item(item_b)
        items = repo.get_wishlist_items()
        assert items[0].active is False


# ---------------------------------------------------------------------------
# update_wishlist_item
# ---------------------------------------------------------------------------

class TestUpdateWishlistItem:
    def test_updates_all_fields(self, repo, item_a):
        item_id = repo.add_wishlist_item(item_a)
        updated = WishlistItem(
            name="Pepsi",
            allowed_brands=["PEPSI"],
            keywords=["pepsi"],
            max_price=1.50,
            active=False,
        )
        repo.update_wishlist_item(item_id, updated)

        items = repo.get_wishlist_items()
        assert len(items) == 1
        assert items[0].name == "Pepsi"
        assert items[0].allowed_brands == ["PEPSI"]
        assert items[0].max_price == 1.50
        assert items[0].active is False

    def test_update_preserves_other_items(self, repo, item_a, item_b):
        id_a = repo.add_wishlist_item(item_a)
        repo.add_wishlist_item(item_b)

        repo.update_wishlist_item(id_a, WishlistItem(name="Cola-Zero", keywords=["zero"]))

        items = repo.get_wishlist_items()
        names = {i.name for i in items}
        assert "Cola-Zero" in names
        assert "Butter" in names

    def test_update_nonexistent_id_does_not_raise(self, repo, item_a):
        # Stilles Update auf ID die nicht existiert — kein Fehler, 0 Zeilen betroffen
        repo.update_wishlist_item(999, item_a)  # must not raise

    def test_name_conflict_raises_integrity_error(self, repo, item_a, item_b):
        id_a = repo.add_wishlist_item(item_a)
        repo.add_wishlist_item(item_b)
        # item_a auf item_b's Namen umbenennen → UNIQUE-Konflikt
        conflict = WishlistItem(name=item_b.name, keywords=["conflict"])
        with pytest.raises(sqlite3.IntegrityError):
            repo.update_wishlist_item(id_a, conflict)


# ---------------------------------------------------------------------------
# delete_wishlist_item
# ---------------------------------------------------------------------------

class TestDeleteWishlistItem:
    def test_deletes_correct_item(self, repo, item_a, item_b):
        id_a = repo.add_wishlist_item(item_a)
        repo.add_wishlist_item(item_b)

        repo.delete_wishlist_item(id_a)

        items = repo.get_wishlist_items()
        assert len(items) == 1
        assert items[0].name == "Butter"

    def test_delete_nonexistent_id_does_not_raise(self, repo):
        repo.delete_wishlist_item(999)  # must not raise

    def test_delete_only_where_id_matches(self, repo, item_a, item_b):
        repo.add_wishlist_item(item_a)
        id_b = repo.add_wishlist_item(item_b)

        repo.delete_wishlist_item(id_b)

        items = repo.get_wishlist_items()
        assert len(items) == 1
        assert items[0].name == "Coca-Cola"


# ---------------------------------------------------------------------------
# toggle_wishlist_item_active
# ---------------------------------------------------------------------------

class TestToggleWishlistItemActive:
    def test_true_becomes_false(self, repo, item_a):
        item_id = repo.add_wishlist_item(item_a)  # active=True
        repo.toggle_wishlist_item_active(item_id)
        assert repo.get_wishlist_items()[0].active is False

    def test_false_becomes_true(self, repo, item_b):
        item_id = repo.add_wishlist_item(item_b)  # active=False
        repo.toggle_wishlist_item_active(item_id)
        assert repo.get_wishlist_items()[0].active is True

    def test_double_toggle_restores_original(self, repo, item_a):
        item_id = repo.add_wishlist_item(item_a)
        repo.toggle_wishlist_item_active(item_id)
        repo.toggle_wishlist_item_active(item_id)
        assert repo.get_wishlist_items()[0].active is True

    def test_toggle_only_affects_target_item(self, repo, item_a, item_b):
        id_a = repo.add_wishlist_item(item_a)  # active=True
        repo.add_wishlist_item(item_b)          # active=False

        repo.toggle_wishlist_item_active(id_a)

        items = {i.name: i for i in repo.get_wishlist_items()}
        assert items["Coca-Cola"].active is False  # getoggelt
        assert items["Butter"].active is False     # unverändert


# ---------------------------------------------------------------------------
# get_wishlist_rows
# ---------------------------------------------------------------------------

class TestGetWishlistRows:
    def test_includes_id(self, repo, item_a):
        repo.add_wishlist_item(item_a)
        rows = repo.get_wishlist_rows()
        assert len(rows) == 1
        assert "id" in rows[0]
        assert rows[0]["name"] == "Coca-Cola"

    def test_includes_created_at_and_updated_at(self, repo, item_a):
        repo.add_wishlist_item(item_a)
        rows = repo.get_wishlist_rows()
        assert rows[0]["created_at"]
        assert rows[0]["updated_at"]

    def test_ordered_by_id(self, repo, item_a, item_b):
        id_a = repo.add_wishlist_item(item_a)
        id_b = repo.add_wishlist_item(item_b)
        rows = repo.get_wishlist_rows()
        assert rows[0]["id"] == id_a
        assert rows[1]["id"] == id_b


# ---------------------------------------------------------------------------
# get_wishlist_item_by_id
# ---------------------------------------------------------------------------

class TestGetWishlistItemById:
    def test_returns_correct_item(self, repo, item_a):
        item_id = repo.add_wishlist_item(item_a)
        fetched = repo.get_wishlist_item_by_id(item_id)
        assert fetched is not None
        assert fetched.name == "Coca-Cola"

    def test_returns_none_for_missing_id(self, repo):
        assert repo.get_wishlist_item_by_id(999) is None
