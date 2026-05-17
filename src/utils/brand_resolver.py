from __future__ import annotations

import re

from src.config.known_brands import KNOWN_BRANDS, BRAND_NAME_OVERRIDES

# Geografische/generische Wörter die KEINE Marke sind
_SKIP_WORDS: frozenset[str] = frozenset({
    # Geografie
    "deutschland", "italien", "frankreich", "spanien", "österreich",
    "belgien", "griechenland", "portugal", "russland", "schottland",
    "irland", "mexiko", "schweiz",
    # Englische Artikel
    "the", "a", "an",
    # Deutsche Artikel / Präpositionen
    "der", "die", "das", "des", "dem", "den",
    "von", "vom", "aus", "mit", "für", "bei",
    # Generische Produkt-Wörter
    "mix-getränke", "premium", "classic", "special", "select",
    "original", "alkoholfrei", "alkoholfreies", "alkoholfreie",
    # Trinkart-Wörter die VOR der Marke stehen können
    "wodka",  # "Wodka Gorbatschow" → skip "Wodka", nimm "Gorbatschow"
})

# Sortiert nach Länge absteigend → längster Treffer gewinnt
_SORTED_BRANDS: list[str] = sorted(KNOWN_BRANDS, key=len, reverse=True)


def resolve_brand(product_name: str) -> str | None:
    """
    Leitet die Marke aus einem Trinkgut-Produktnamen ab.

    Strategie:
    1. Prüfe gegen KNOWN_BRANDS (Längstes-Präfix gewinnt).
       Erlaubt Satzzeichen direkt nach dem Markennamen.
    2. Wende BRAND_NAME_OVERRIDES an.
    3. Fallback: erstes nicht-übersprungenes Wort (SKIP_WORDS).
    4. Normalisierung: UPPERCASE + Apostroph-Normalisierung.
    """
    if not product_name or not product_name.strip():
        return None

    name_stripped = product_name.strip()
    name_lower    = name_stripped.lower()

    # ── Schritt 1+2: KNOWN_BRANDS Prefix-Match ──
    for brand in _SORTED_BRANDS:
        brand_lower = brand.lower()
        if not name_lower.startswith(brand_lower):
            continue
        # Was folgt nach dem Marken-Präfix?
        rest = name_lower[len(brand_lower):]
        # Nur matchen wenn danach Leerzeichen, Satzzeichen oder String-Ende
        if rest and rest[0] not in " ,.-/:()":
            continue
        # Treffer!
        canonical = BRAND_NAME_OVERRIDES.get(brand, brand)
        return _normalize(canonical)

    # ── Schritt 3: Fallback-Heuristik ──
    words = name_stripped.split()
    for i, word in enumerate(words):
        # Satzzeichen am Wortende abschneiden
        clean = word.strip(",.;:()/")
        if len(clean) < 2:
            continue
        if clean.lower() in _SKIP_WORDS:
            continue
        # Kurze Abkürzungen oder Wörter mit Punkt → zwei Wörter nehmen
        if (len(clean) <= 3 or clean.endswith(".")) and i + 1 < len(words):
            next_clean = words[i + 1].strip(",.;:")
            if len(next_clean) >= 2:
                return _normalize(f"{clean} {next_clean}")
        return _normalize(clean)

    # Letzter Ausweg: erstes Wort
    return _normalize(words[0]) if words else None


def _normalize(brand: str) -> str:
    """UPPERCASE + typografische Apostrophe normalisieren."""
    return brand.strip().replace("’", "'").replace("‘", "'").upper()
