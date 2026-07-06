"""Tests für PriceRating-Logik und Repository-History-Methoden."""
from __future__ import annotations

import statistics
from datetime import datetime, timezone, timedelta

import pytest

from src.analysis.price_rating import PriceRating, rate_offer, RATING_EMOJI
from src.db.repository import OfferRepository
from src.models.offer import Offer, Supermarket


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path) -> OfferRepository:
    return OfferRepository(str(tmp_path / "test.db"))


def _offer(
    sale_price: float,
    scraped_at: datetime,
    brand: str = "ARLA",
    name: str = "Frische Milch",
    unit: str = "1-L-Packung",
    base_price: float | None = None,
    slug_suffix: str = "",
    valid_from: datetime | None = None,
) -> Offer:
    return Offer(
        source=Supermarket.ALDI_NORD,
        product_slug=f"milch-{scraped_at.day}-{slug_suffix}",
        brand=brand,
        name=name,
        sale_price=sale_price,
        base_price_value=base_price,
        base_price_unit="L" if base_price else None,
        sales_unit_raw=unit,
        category_ids=["Angebote"],
        scraped_at=scraped_at,
        valid_from=valid_from,
    )


def _add_prices(repo: OfferRepository, prices: list[float], brand="ARLA", name="Frische Milch") -> None:
    """
    Speichert N Angebote als N distinkte Angebotsperioden in price_history.
    Jeder Eintrag bekommt valid_from=scraped_at, damit der Dedup-Mechanismus
    jeden Eintrag als eigenständiges Angebot behandelt (kein tages-basiertes
    Zusammenfassen gleicher Preise).
    """
    n = len(prices)
    for i, price in enumerate(prices):
        # ältester Eintrag vor (n - 1) Tagen, neuester gestern
        dt = datetime.now(timezone.utc) - timedelta(days=(n - 1 - i))
        repo.save_price_history_entry(
            _offer(price, dt, brand=brand, name=name, slug_suffix=str(i),
                   valid_from=dt)
        )


# ---------------------------------------------------------------------------
# Ampel-Logik: no_data
# ---------------------------------------------------------------------------

class TestNoData:
    def test_no_history_gives_no_data(self, repo):
        r = rate_offer("aldi_nord", "ARLA", "Frische Milch", "1-L-Packung", 1.11, None, repo)
        assert r.level == "no_data"
        assert r.historic_count == 0

    def test_one_entry_still_no_data(self, repo):
        _add_prices(repo, [1.11])
        r = rate_offer("aldi_nord", "arla", "frische milch", "1-l-packung", 1.11, None, repo)
        assert r.level == "no_data"

    def test_two_entries_still_no_data(self, repo):
        _add_prices(repo, [1.11, 0.99])
        r = rate_offer("aldi_nord", "arla", "frische milch", "1-l-packung", 1.11, None, repo)
        assert r.level == "no_data"
        assert r.historic_count == 2

    def test_no_data_label_and_explanation(self, repo):
        r = rate_offer("aldi_nord", "ARLA", "Frische Milch", "1-L-Packung", 1.11, None, repo)
        assert r.label == "Zu wenig Daten"
        assert "0" in r.explanation


# ---------------------------------------------------------------------------
# Ampel-Logik: Tendenz (3–9 Punkte)
# ---------------------------------------------------------------------------

class TestTendenz:
    def test_three_entries_gets_tendenz_prefix(self, repo):
        _add_prices(repo, [0.99, 1.11, 1.29])
        r = rate_offer("aldi_nord", "arla", "frische milch", "1-l-packung", 0.99, None, repo)
        assert "Tendenz" in r.label
        assert r.level in ("green", "yellow", "red")

    def test_nine_entries_still_tendenz(self, repo):
        _add_prices(repo, [0.89 + i * 0.1 for i in range(9)])
        r = rate_offer("aldi_nord", "arla", "frische milch", "1-l-packung", 0.89, None, repo)
        assert "Tendenz" in r.label


# ---------------------------------------------------------------------------
# Ampel-Logik: Vollbewertung (>=10 Punkte)
# ---------------------------------------------------------------------------

class TestFullRating:
    def _setup_10_prices(self, repo: OfferRepository, prices: list[float]) -> None:
        assert len(prices) >= 10
        _add_prices(repo, prices)

    def test_10_entries_no_tendenz_prefix(self, repo):
        prices = [1.0] * 10
        self._setup_10_prices(repo, prices)
        r = rate_offer("aldi_nord", "arla", "frische milch", "1-l-packung", 1.0, None, repo)
        assert "Tendenz" not in r.label

    def test_min_price_is_green(self, repo):
        """Günstigster Preis aller Zeitpunkte → grün."""
        prices = [0.69, 0.79, 0.89, 0.99, 0.99, 1.09, 1.11, 1.19, 1.29, 1.39, 1.49, 1.59]
        self._setup_10_prices(repo, prices)
        min_p = min(prices)
        r = rate_offer("aldi_nord", "arla", "frische milch", "1-l-packung", min_p, None, repo)
        assert r.level == "green"
        assert r.min_price == min_p

    def test_max_price_is_red(self, repo):
        """Teuerster Preis aller Zeitpunkte → rot."""
        prices = [0.69, 0.79, 0.89, 0.99, 0.99, 1.09, 1.11, 1.19, 1.29, 1.39, 1.49, 1.59]
        self._setup_10_prices(repo, prices)
        max_p = max(prices)
        r = rate_offer("aldi_nord", "arla", "frische milch", "1-l-packung", max_p, None, repo)
        assert r.level == "red"

    def test_median_available(self, repo):
        prices = [1.0] * 10
        self._setup_10_prices(repo, prices)
        r = rate_offer("aldi_nord", "arla", "frische milch", "1-l-packung", 1.0, None, repo)
        assert r.median_price is not None
        assert r.historic_count == 10


# ---------------------------------------------------------------------------
# Edge Case: alle Preise identisch
# ---------------------------------------------------------------------------

class TestIdenticalPrices:
    def test_all_same_price_is_green(self, repo):
        """Alle historischen Preise identisch → P20 = P60 = Preis → grün."""
        _add_prices(repo, [1.99] * 10)
        r = rate_offer("aldi_nord", "arla", "frische milch", "1-l-packung", 1.99, None, repo)
        assert r.level == "green"

    def test_higher_than_all_is_red(self, repo):
        """Aktueller Preis höher als alle historischen → rot."""
        _add_prices(repo, [1.99] * 10)
        r = rate_offer("aldi_nord", "arla", "frische milch", "1-l-packung", 2.49, None, repo)
        assert r.level == "red"


# ---------------------------------------------------------------------------
# Repository: case-insensitive Matching
# ---------------------------------------------------------------------------

class TestRepositoryHistoryMethods:
    def test_case_insensitive_brand(self, repo):
        """brand "ARLA" in DB, Abfrage mit "arla" → Match."""
        _add_prices(repo, [1.11, 0.99, 0.89], brand="ARLA")
        results = repo.get_price_history_for_product(
            source="aldi_nord",
            brand_lower="arla",
            name_lower="frische milch",
            sales_unit_raw="1-L-Packung",
        )
        assert len(results) == 3

    def test_no_match_wrong_source(self, repo):
        _add_prices(repo, [1.11, 0.99, 0.89])
        results = repo.get_price_history_for_product(
            source="kaufland",          # wrong source
            brand_lower="arla",
            name_lower="frische milch",
            sales_unit_raw="1-L-Packung",
        )
        assert len(results) == 0

    def test_days_filter(self, repo):
        """Einträge die älter als days sind, werden nicht zurückgegeben."""
        old = _offer(0.79, datetime(2020, 1, 1, tzinfo=timezone.utc), slug_suffix="old")
        recent = _offer(1.11, datetime.now(timezone.utc), slug_suffix="recent")
        repo.save_price_history_entry(old)
        repo.save_price_history_entry(recent)

        results = repo.get_price_history_for_product(
            source="aldi_nord",
            brand_lower="arla",
            name_lower="frische milch",
            sales_unit_raw="1-l-packung",
            days=90,
        )
        # Nur der aktuelle Eintrag sollte zurückkommen
        assert len(results) == 1
        assert results[0]["sale_price"] == 1.11

    def test_chart_data_aggregates_by_day(self, repo):
        """Mehrere Scrapes am gleichen Tag → ein Eintrag im Chart."""
        today = datetime.now(timezone.utc)
        for i, price in enumerate([1.00, 1.10]):
            repo.save_price_history_entry(
                _offer(price, today, slug_suffix=f"same-day-{i}")
            )
        chart = repo.get_price_history_for_chart(
            source="aldi_nord",
            brand_lower="arla",
            name_lower="frische milch",
            sales_unit_raw="1-l-packung",
        )
        # Beide Scrapes am gleichen Tag → 1 Punkt im Chart
        assert len(chart) == 1
        day, avg = chart[0]
        assert abs(avg - 1.05) < 0.01   # Durchschnitt von 1.00 und 1.10


# ---------------------------------------------------------------------------
# RATING_EMOJI Konstante
# ---------------------------------------------------------------------------

class TestRatingEmoji:
    def test_all_levels_have_emoji(self):
        for level in ("green", "yellow", "red", "no_data"):
            assert level in RATING_EMOJI
            assert RATING_EMOJI[level]


# ---------------------------------------------------------------------------
# Dedup: Angebots-Ebene statt Tages-Ebene
# ---------------------------------------------------------------------------

class TestDedup:
    def test_seven_daily_scrapes_same_price_count_as_one(self, repo):
        """7 Tageseinträge desselben Angebots (kein valid_from) → 1 Datenpunkt."""
        for i in range(7):
            dt = datetime.now(timezone.utc) - timedelta(days=6 - i)
            repo.save_price_history_entry(
                _offer(1.99, dt, slug_suffix=str(i))  # kein valid_from
            )
        results = repo.get_price_history_for_product(
            source="aldi_nord", brand_lower="arla",
            name_lower="frische milch", sales_unit_raw="1-L-Packung",
        )
        assert len(results) == 1

    def test_same_price_two_weeks_apart_counts_as_two(self, repo):
        """Selber Preis in zwei Wochen mit >3-Tage-Lücke → 2 Datenpunkte."""
        # Woche 1: Tage 20-26 zurück
        for i in range(7):
            dt = datetime.now(timezone.utc) - timedelta(days=26 - i)
            repo.save_price_history_entry(_offer(1.99, dt, slug_suffix=f"w1-{i}"))
        # Woche 2: Tage 6-12 zurück (Lücke ≥ 8 Tage zur letzten Woche-1-Erfassung)
        for i in range(7):
            dt = datetime.now(timezone.utc) - timedelta(days=12 - i)
            repo.save_price_history_entry(_offer(1.99, dt, slug_suffix=f"w2-{i}"))
        results = repo.get_price_history_for_product(
            source="aldi_nord", brand_lower="arla",
            name_lower="frische milch", sales_unit_raw="1-L-Packung",
        )
        assert len(results) == 2

    def test_one_offer_seven_daily_scrapes_gives_no_data(self, repo):
        """1 laufendes Angebot (7 Tagespunkte) → no_data, nicht fälschlich Tendenz."""
        for i in range(7):
            dt = datetime.now(timezone.utc) - timedelta(days=6 - i)
            repo.save_price_history_entry(_offer(1.99, dt, slug_suffix=str(i)))
        r = rate_offer(
            "aldi_nord", "arla", "frische milch", "1-L-Packung", 1.99, None, repo
        )
        assert r.level == "no_data"
        assert r.historic_count == 1

    def test_valid_from_deduplicates_daily_scrapes(self, repo):
        """Gleiche (sale_price, valid_from) über 7 Tage → 1 Datenpunkt."""
        vf = datetime.now(timezone.utc) - timedelta(days=10)
        for i in range(7):
            dt = vf + timedelta(days=i)
            repo.save_price_history_entry(_offer(2.49, dt, slug_suffix=str(i), valid_from=vf))
        results = repo.get_price_history_for_product(
            source="aldi_nord", brand_lower="arla",
            name_lower="frische milch", sales_unit_raw="1-L-Packung",
        )
        assert len(results) == 1

    def test_thresholds_apply_to_offer_count(self, repo):
        """Schwellen (_NO_DATA_THRESHOLD=3, _FULL_RATING_THRESHOLD=10) gelten
        für Angebots-Datenpunkte, nicht für Tages-Einträge."""
        # 2 Angebote (je 7 Tagespunkte): n=2 → no_data
        for offer_week in [20, 6]:
            for day in range(7):
                dt = datetime.now(timezone.utc) - timedelta(days=offer_week - day)
                repo.save_price_history_entry(
                    _offer(1.99, dt, slug_suffix=f"w{offer_week}-{day}")
                )
        r = rate_offer(
            "aldi_nord", "arla", "frische milch", "1-L-Packung", 1.99, None, repo
        )
        assert r.historic_count == 2
        assert r.level == "no_data"
