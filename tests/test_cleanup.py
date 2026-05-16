"""Tests für cleanup_expired_offers."""
from datetime import datetime, timezone, timedelta

import pytest

from src.db.repository import OfferRepository
from src.models.offer import Offer, Supermarket


@pytest.fixture
def repo(tmp_path) -> OfferRepository:
    return OfferRepository(str(tmp_path / "test.db"))


def _offer(
    slug: str,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> Offer:
    return Offer(
        source=Supermarket.ALDI_NORD,
        product_slug=slug,
        name="Testartikel",
        sale_price=1.99,
        valid_from=valid_from,
        valid_until=valid_until,
        category_ids=["Angebote"],
        scraped_at=datetime.now(timezone.utc),
    )


class TestCleanupExpiredOffers:
    def test_expired_offer_is_deleted(self, repo):
        """valid_until in der Vergangenheit → wird gelöscht."""
        past = datetime(2026, 1, 7, tzinfo=timezone.utc)
        repo.upsert_offer(_offer("slug-expired", valid_until=past))
        assert repo.count() == 1

        deleted = repo.cleanup_expired_offers()

        assert deleted == 1
        assert repo.count() == 0

    def test_active_offer_is_kept(self, repo):
        """valid_until in der Zukunft → bleibt erhalten."""
        future = datetime.now(timezone.utc) + timedelta(days=3)
        repo.upsert_offer(_offer("slug-active", valid_until=future))

        deleted = repo.cleanup_expired_offers()

        assert deleted == 0
        assert repo.count() == 1

    def test_future_offer_is_kept(self, repo):
        """valid_from UND valid_until in der Zukunft → bleibt erhalten."""
        start = datetime.now(timezone.utc) + timedelta(days=5)
        end   = datetime.now(timezone.utc) + timedelta(days=12)
        repo.upsert_offer(_offer("slug-future", valid_from=start, valid_until=end))

        deleted = repo.cleanup_expired_offers()

        assert deleted == 0
        assert repo.count() == 1

    def test_undated_offer_is_not_deleted(self, repo):
        """Kein valid_until (z.B. Trinkgut) → nie löschen."""
        repo.upsert_offer(_offer("slug-nodates"))

        deleted = repo.cleanup_expired_offers()

        assert deleted == 0
        assert repo.count() == 1

    def test_returns_count_of_deleted_rows(self, repo):
        """Rückgabewert = Anzahl gelöschter Zeilen."""
        past = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(3):
            repo.upsert_offer(_offer(f"slug-{i}", valid_until=past))

        deleted = repo.cleanup_expired_offers()

        assert deleted == 3

    def test_price_history_untouched(self, repo):
        """
        Wichtigster Test: Auch wenn das Angebot aus offers gelöscht wird,
        bleibt der Eintrag in price_history erhalten.
        """
        past    = datetime(2026, 1, 7, tzinfo=timezone.utc)
        expired = _offer("slug-expired", valid_until=past)

        repo.upsert_offer(expired)
        repo.save_price_history_entry(expired)

        assert repo.count_price_history() == 1

        deleted = repo.cleanup_expired_offers()

        assert deleted == 1
        assert repo.count() == 0
        assert repo.count_price_history() == 1  # ← unverändert!

    def test_only_expired_are_deleted(self, repo):
        """Nur abgelaufene werden gelöscht, aktive bleiben."""
        past   = datetime(2026, 1, 1, tzinfo=timezone.utc)
        future = datetime.now(timezone.utc) + timedelta(days=5)

        repo.upsert_offer(_offer("slug-past",   valid_until=past))
        repo.upsert_offer(_offer("slug-future", valid_until=future))

        deleted = repo.cleanup_expired_offers()

        assert deleted == 1
        assert repo.count() == 1
