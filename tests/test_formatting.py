"""Tests für format_german_date."""
from datetime import datetime, date, timezone

import pytest

from src.utils.formatting import format_german_date


class TestFormatGermanDate:
    def test_iso_date_string_with_year(self):
        assert format_german_date("2026-05-27") == "27.05.2026"

    def test_iso_datetime_string_with_timezone(self):
        assert format_german_date("2026-05-27T22:00:00+00:00") == "27.05.2026"

    def test_iso_date_without_year(self):
        assert format_german_date("2026-05-27", with_year=False) == "27.05."

    def test_datetime_object(self):
        dt = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
        assert format_german_date(dt) == "27.05.2026"

    def test_date_object(self):
        assert format_german_date(date(2026, 5, 27)) == "27.05.2026"

    def test_none_returns_dash(self):
        assert format_german_date(None) == "—"

    def test_empty_string_returns_dash(self):
        assert format_german_date("") == "—"

    def test_invalid_string_returns_dash(self):
        assert format_german_date("not-a-date") == "—"

    def test_first_of_year(self):
        assert format_german_date("2026-01-01") == "01.01.2026"

    def test_december(self):
        assert format_german_date("2026-12-31") == "31.12.2026"

    def test_zero_padded_day_and_month(self):
        """Tag und Monat müssen immer zweistellig sein."""
        assert format_german_date("2026-01-03") == "03.01.2026"

    def test_without_year_trailing_dot(self):
        """with_year=False endet auf '.'"""
        result = format_german_date("2026-01-03", with_year=False)
        assert result == "03.01."
        assert result.endswith(".")
