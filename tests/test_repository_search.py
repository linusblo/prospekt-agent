"""Tests für die Volltextsuche (OfferRepository.search_offers)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.db.repository import OfferRepository, _offer_matches_words
from src.models.offer import Offer, Supermarket


@pytest.fixture
def repo(tmp_path) -> OfferRepository:
    return OfferRepository(str(tmp_path / "test.db"))


def _offer(
    slug: str,
    name: str,
    brand: str | None = None,
    short_description: str | None = None,
    long_description: str | None = None,
    sale_price: float = 1.99,
    original_price: float | None = None,
    discount_percent: float | None = None,
    valid_until: datetime | None = None,
    source: Supermarket = Supermarket.ALDI_NORD,
) -> Offer:
    return Offer(
        source=source,
        product_slug=slug,
        name=name,
        brand=brand,
        short_description=short_description,
        long_description=long_description,
        sale_price=sale_price,
        original_price=original_price,
        discount_percent=discount_percent,
        valid_until=valid_until,
        scraped_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# _offer_matches_words — reine Funktion, kein DB-Zugriff nötig
# ---------------------------------------------------------------------------

class TestOfferMatchesWords:
    def test_single_word_matches_name(self):
        offer = {"name": "Gorbatschow Vodka", "brand": None,
                  "short_description": None, "long_description": None}
        assert _offer_matches_words(offer, ["vodka"]) is True

    def test_case_insensitive_haystack(self):
        """Haystack wird intern lowercased — Wörter müssen vom Aufrufer
        bereits lowercased übergeben werden (siehe search_offers)."""
        offer = {"name": "Gorbatschow Vodka", "brand": None,
                  "short_description": None, "long_description": None}
        assert _offer_matches_words(offer, ["vodka"]) is True

    def test_multi_word_requires_all_in_any_field(self):
        offer = {"name": "Vodka", "brand": "Gorbatschow",
                  "short_description": None, "long_description": None}
        assert _offer_matches_words(offer, ["vodka", "gorbatschow"]) is True

    def test_multi_word_fails_if_one_missing(self):
        offer = {"name": "Vodka", "brand": "Smirnoff",
                  "short_description": None, "long_description": None}
        assert _offer_matches_words(offer, ["vodka", "gorbatschow"]) is False

    def test_substring_match(self):
        offer = {"name": "Erdbeerjoghurt", "brand": None,
                  "short_description": None, "long_description": None}
        assert _offer_matches_words(offer, ["beer"]) is True

    def test_none_fields_do_not_crash(self):
        offer = {"name": "Brot", "brand": None,
                  "short_description": None, "long_description": None}
        assert _offer_matches_words(offer, ["käse"]) is False


# ---------------------------------------------------------------------------
# OfferRepository.search_offers — End-to-End über SQLite
# ---------------------------------------------------------------------------

class TestSearchOffers:
    def test_finds_match_in_name(self, repo):
        repo.upsert_offer(_offer("v1", name="Gorbatschow Vodka 0,7L"))
        results = repo.search_offers("vodka")
        assert len(results) == 1
        assert results[0]["name"] == "Gorbatschow Vodka 0,7L"

    def test_finds_match_in_brand(self, repo):
        repo.upsert_offer(_offer("v1", name="Wodka 0,7L", brand="Gorbatschow"))
        results = repo.search_offers("gorbatschow")
        assert len(results) == 1

    def test_finds_match_in_descriptions(self, repo):
        repo.upsert_offer(_offer(
            "v1", name="Schinken", short_description="Luftgetrocknet",
            long_description="Aus bayerischer Landwirtschaft",
        ))
        assert len(repo.search_offers("luftgetrocknet")) == 1
        assert len(repo.search_offers("bayerischer")) == 1

    def test_multi_word_and_logic(self, repo):
        repo.upsert_offer(_offer("v1", name="Vodka", brand="Gorbatschow"))
        repo.upsert_offer(_offer("v2", name="Vodka", brand="Smirnoff"))

        results = repo.search_offers("vodka gorbatschow")

        assert len(results) == 1
        assert results[0]["brand"] == "Gorbatschow"

    def test_no_match_returns_empty_list(self, repo):
        repo.upsert_offer(_offer("v1", name="Vodka"))
        assert repo.search_offers("whisky") == []

    def test_empty_query_returns_empty_list(self, repo):
        repo.upsert_offer(_offer("v1", name="Vodka"))
        assert repo.search_offers("") == []
        assert repo.search_offers("   ") == []

    def test_excludes_expired_offers(self, repo):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        future = datetime.now(timezone.utc) + timedelta(days=1)
        repo.upsert_offer(_offer("v1", name="Vodka Alt", valid_until=past))
        repo.upsert_offer(_offer("v2", name="Vodka Neu", valid_until=future))

        results = repo.search_offers("vodka")

        assert len(results) == 1
        assert results[0]["name"] == "Vodka Neu"

    def test_case_insensitive_search(self, repo):
        repo.upsert_offer(_offer("v1", name="Käse Gouda"))
        assert len(repo.search_offers("KÄSE")) == 1
        assert len(repo.search_offers("käse")) == 1

    def test_sorted_by_discount_desc_then_price_asc(self, repo):
        repo.upsert_offer(_offer("v1", name="Vodka A", sale_price=10.0, discount_percent=10))
        repo.upsert_offer(_offer("v2", name="Vodka B", sale_price=5.0, discount_percent=30))
        repo.upsert_offer(_offer("v3", name="Vodka C", sale_price=3.0, discount_percent=30))

        results = repo.search_offers("vodka")

        assert [r["product_slug"] for r in results] == ["v3", "v2", "v1"]

    def test_searches_across_all_sources(self, repo):
        repo.upsert_offer(_offer("v1", name="Vodka", source=Supermarket.ALDI_NORD))
        repo.upsert_offer(_offer("v1", name="Vodka", source=Supermarket.KAUFLAND))

        results = repo.search_offers("vodka")

        assert {r["source"] for r in results} == {"aldi_nord", "kaufland"}
