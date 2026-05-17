"""Tests für den Alert-Checker — kein echter E-Mail-Versand."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.db.repository import OfferRepository
from src.matching.matcher import MatchedProduct
from src.matching.wishlist import WishlistItem
from src.analysis.price_rating import PriceRating
from src.notifications.alert_checker import check_and_send_alerts


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path) -> OfferRepository:
    return OfferRepository(str(tmp_path / "test.db"))


@pytest.fixture
def mock_sender() -> MagicMock:
    sender = MagicMock()
    sender.send_alert.return_value = True
    return sender


def _mp(
    item_name: str = "Cola",
    alert_enabled: bool = True,
    alert_max_base_price: float | None = 0.70,
    alert_max_total_price: float | None = None,
    alert_only_green: bool = False,
    alert_recipients: list[str] | None = None,
    sale_price: float = 0.99,
    base_price_value: float | None = 0.65,
    price_rating_level: str = "green",
    source: str = "aldi_nord",
    slug: str = "cola-123",
    valid_from: str = "2026-05-13T00:00:00+00:00",
) -> MatchedProduct:
    item = WishlistItem(
        name=item_name,
        keywords=[item_name.lower()],
        alert_enabled=alert_enabled,
        alert_max_base_price=alert_max_base_price,
        alert_max_total_price=alert_max_total_price,
        alert_only_green=alert_only_green,
        alert_recipients=alert_recipients if alert_recipients is not None else ["test@example.com"],
    )
    offer = {
        "source":          source,
        "product_slug":    slug,
        "name":            item_name,
        "brand":           "TEST",
        "sale_price":      sale_price,
        "base_price_value": base_price_value,
        "base_price_unit": "L",
        "valid_from":      valid_from,
        "valid_until":     "2026-05-16T22:00:00+00:00",
    }
    rating = PriceRating(
        level=price_rating_level,
        label="Sehr gut" if price_rating_level == "green" else "Mittelmäßig",
        explanation="Test",
        historic_count=10,
    )
    return MatchedProduct(wishlist_item=item, primary_offer=offer, price_rating=rating)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAlertChecker:
    def test_alert_fires_when_base_price_below_threshold(self, repo, mock_sender):
        mp = _mp(alert_max_base_price=0.70, base_price_value=0.65)
        sent = check_and_send_alerts([mp], repo, mock_sender, ["default@example.com"])

        assert sent == 1
        mock_sender.send_alert.assert_called_once()

    def test_no_alert_when_base_price_above_threshold(self, repo, mock_sender):
        mp = _mp(alert_max_base_price=0.70, base_price_value=0.80)
        sent = check_and_send_alerts([mp], repo, mock_sender, ["default@example.com"])

        assert sent == 0
        mock_sender.send_alert.assert_not_called()

    def test_no_alert_when_disabled(self, repo, mock_sender):
        mp = _mp(alert_enabled=False, base_price_value=0.50)
        sent = check_and_send_alerts([mp], repo, mock_sender, ["default@example.com"])

        assert sent == 0

    def test_no_duplicate_alert_same_offer(self, repo, mock_sender):
        """Zweiter Aufruf mit identischem Angebot → kein erneuter Versand."""
        mp = _mp(base_price_value=0.65)

        sent1 = check_and_send_alerts([mp], repo, mock_sender, ["test@example.com"])
        assert sent1 == 1

        sent2 = check_and_send_alerts([mp], repo, mock_sender, ["test@example.com"])
        assert sent2 == 0
        assert mock_sender.send_alert.call_count == 1   # nur einmal gesendet

    def test_only_green_blocks_yellow(self, repo, mock_sender):
        mp = _mp(
            alert_only_green=True,
            price_rating_level="yellow",
            base_price_value=0.65,
        )
        sent = check_and_send_alerts([mp], repo, mock_sender, ["test@example.com"])

        assert sent == 0

    def test_only_green_allows_green(self, repo, mock_sender):
        mp = _mp(
            alert_only_green=True,
            price_rating_level="green",
            base_price_value=0.65,
        )
        sent = check_and_send_alerts([mp], repo, mock_sender, ["test@example.com"])

        assert sent == 1

    def test_total_price_threshold(self, repo, mock_sender):
        mp = _mp(
            alert_max_base_price=None,
            alert_max_total_price=1.50,
            base_price_value=None,
            sale_price=0.99,
        )
        sent = check_and_send_alerts([mp], repo, mock_sender, ["test@example.com"])

        assert sent == 1

    def test_uses_item_recipients_over_default(self, repo, mock_sender):
        """Wenn item.alert_recipients gesetzt → diese nutzen, nicht default."""
        mp = _mp(
            alert_recipients=["mama@example.com"],
            base_price_value=0.65,
        )
        check_and_send_alerts([mp], repo, mock_sender, ["default@example.com"])

        call_args = mock_sender.send_alert.call_args
        assert call_args is not None
        recipients_used = call_args[0][0]   # first positional arg
        assert recipients_used == ["mama@example.com"]

    def test_no_alert_when_no_recipients(self, repo, mock_sender):
        """Weder item-Empfänger noch default → kein Versand."""
        mp = _mp(alert_recipients=[], base_price_value=0.65)
        sent = check_and_send_alerts([mp], repo, mock_sender, default_recipients=[])

        assert sent == 0

    def test_count_alerts_sent_today_increments(self, repo, mock_sender):
        mp = _mp(base_price_value=0.65)
        assert repo.count_alerts_sent_today() == 0

        check_and_send_alerts([mp], repo, mock_sender, ["test@example.com"])
        assert repo.count_alerts_sent_today() == 1
