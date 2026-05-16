"""Tests für die Price-History-Persistierung."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from src.db.repository import OfferRepository
from src.models.offer import Offer, Supermarket


@pytest.fixture
def repo(tmp_path) -> OfferRepository:
    return OfferRepository(str(tmp_path / "test.db"))


def _make_offer(
    product_slug: str = "test-001",
    name: str = "Testprodukt",
    sale_price: float = 1.99,
    scraped_at: datetime | None = None,
) -> Offer:
    return Offer(
        source=Supermarket.ALDI_NORD,
        product_slug=product_slug,
        name=name,
        sale_price=sale_price,
        category_ids=["Angebote"],
        scraped_at=scraped_at or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tabellen-Grundfunktionen
# ---------------------------------------------------------------------------

class TestPriceHistoryBasics:
    def test_table_exists_after_init(self, repo):
        """price_history wird automatisch in _init_db() angelegt."""
        assert repo.count_price_history() == 0

    def test_save_entry_creates_one_row(self, repo):
        repo.save_price_history_entry(_make_offer())
        assert repo.count_price_history() == 1

    def test_save_batch_creates_multiple_rows(self, repo):
        offers = [
            _make_offer("slug-1", "Produkt A"),
            _make_offer("slug-2", "Produkt B"),
            _make_offer("slug-3", "Produkt C"),
        ]
        count = repo.save_price_history_batch(offers)
        assert count == 3
        assert repo.count_price_history() == 3


# ---------------------------------------------------------------------------
# Zwei-Scrape-Regel: jeder Lauf erzeugt neue Einträge
# ---------------------------------------------------------------------------

class TestTwoScrapesProducesTwoEntries:
    def test_same_offer_different_scraped_at_makes_two_rows(self, repo):
        """
        Gleicher Artikel, verschiedene scraped_at-Zeitpunkte
        → zwei Einträge in price_history (kein UPSERT!).
        """
        now = datetime.now(timezone.utc)
        offer_run1 = _make_offer(scraped_at=now)
        offer_run2 = _make_offer(scraped_at=now + timedelta(hours=1))

        repo.save_price_history_entry(offer_run1)
        repo.save_price_history_entry(offer_run2)

        assert repo.count_price_history() == 2

    def test_same_scraped_at_does_not_duplicate(self, repo):
        """
        Gleicher Artikel, gleiche scraped_at (same run, doppelt aufgerufen)
        → INSERT OR IGNORE verhindert Duplikat.
        """
        now = datetime.now(timezone.utc)
        offer = _make_offer(scraped_at=now)

        repo.save_price_history_entry(offer)
        repo.save_price_history_entry(offer)  # zweiter Aufruf mit identischem offer

        assert repo.count_price_history() == 1


# ---------------------------------------------------------------------------
# offers-Tabelle bleibt von History unberührt
# ---------------------------------------------------------------------------

class TestOffersTableUnaffected:
    def test_upsert_twice_still_one_row_in_offers(self, repo):
        """offers-Tabelle nutzt UPSERT — zweifaches Speichern = 1 Zeile."""
        offer = _make_offer()
        repo.upsert_offer(offer)
        repo.upsert_offer(offer)

        assert repo.count() == 1

    def test_history_and_offers_count_independently(self, repo):
        """History wächst bei jedem Scrape, offers bleibt konstant."""
        now = datetime.now(timezone.utc)
        offer = _make_offer()

        # Scrape 1
        repo.upsert_offer(offer)
        repo.save_price_history_entry(offer)

        # Scrape 2 (neues scraped_at)
        offer2 = _make_offer(scraped_at=now + timedelta(hours=1))
        repo.upsert_offer(offer2)
        repo.save_price_history_entry(offer2)

        assert repo.count() == 1           # offers: UPSERT → immer 1
        assert repo.count_price_history() == 2  # history: 2 Scrapes


# ---------------------------------------------------------------------------
# cleanup_old_history (vorbereitet, nicht aktiv)
# ---------------------------------------------------------------------------

class TestCleanupOldHistory:
    def test_cleanup_removes_old_entries(self, repo):
        """Alte Einträge werden gelöscht, neue bleiben erhalten."""
        old_offer    = _make_offer(scraped_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
        recent_offer = _make_offer(scraped_at=datetime.now(timezone.utc),
                                   product_slug="recent-001")

        repo.save_price_history_entry(old_offer)
        repo.save_price_history_entry(recent_offer)

        removed = repo.cleanup_old_history(days=365)

        assert removed == 1
        assert repo.count_price_history() == 1

    def test_cleanup_returns_count_of_deleted(self, repo):
        for i in range(3):
            old = _make_offer(
                product_slug=f"old-{i}",
                scraped_at=datetime(2019, 1, 1, tzinfo=timezone.utc),
            )
            repo.save_price_history_entry(old)

        removed = repo.cleanup_old_history(days=365)
        assert removed == 3
