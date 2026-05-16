from __future__ import annotations

from datetime import datetime, date


def format_german_date(
    value: str | datetime | date | None,
    with_year: bool = True,
) -> str:
    """
    Konvertiert ein Datum in deutsches Format.

    "2026-05-27"                 → "27.05.2026"
    "2026-05-27T22:00:00+00:00"  → "27.05.2026"
    with_year=False               → "27.05."
    datetime / date Objekt        → entsprechend formatiert
    None / leer / ungültig        → "—"
    """
    if value is None:
        return "—"

    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return "—"
        try:
            d = date.fromisoformat(s[:10])
        except ValueError:
            return "—"
    else:
        return "—"

    return d.strftime("%d.%m.%Y") if with_year else d.strftime("%d.%m.")
