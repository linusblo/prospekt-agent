"""
Heuristik für den "Zu Wishlist"-Vorschlags-Dialog.

extract_hauptbegriff() nimmt einen Produktnamen und die Brand und gibt
den bedeutungstragenden Hauptbegriff zurück, den der Nutzer als Suchbegriff
in der Wishlist verwenden kann (z.B. "Kaffee" statt "Prodomo",
"Bier" statt "Pilsener").

Nutzt denselben Normalizer wie der Matcher (normalize_for_matching),
damit Stopword-Matching und Duplikat-Prüfung konsistent sind.
"""
from __future__ import annotations

import re

from src.utils.text_normalize import normalize_for_matching as _nm

# TODO: Diese Liste wächst erfahrungsgemäß. Langfristig in eine config-Datei
#       auslagern oder aus der DB (häufige nicht-Brand-Wörter) ableiten.
_STOPWORDS: frozenset[str] = frozenset({
    # Größen / Mengen
    "xxl", "xl", "mini", "mega", "extra", "family", "big", "small",
    # Qualitäts-Adjektive
    "bio", "light", "classic", "original", "premium", "natural", "finest",
    "leichte", "frische", "ergiebige", "feine", "zarte", "sanfte",
    "genussvolle", "herzhafte", "delikate", "cremige",
    # Nationalitäts-Adjektive
    "irish", "french", "italian", "german",
    "franzosisch", "italienisch", "schottisch", "irisch", "spanisch",
    # Verpackungstypen
    "mehrweg", "einweg", "flasche", "dose", "glas", "packung", "pack",
    "kasten", "karton", "becher",
    # Prozent-/Zahlen-Tokens
    # HINWEIS: normalize_for_matching lässt "%" stehen → "100%" ist ein Token
    "100%", "100",
    # Konnektoren / Hilfsworte
    "oder", "und", "mit", "von", "aus", "fur", "o", "no", "nr",
})


def extract_hauptbegriff(name: str, brand: str) -> str:
    """
    Gibt das erste bedeutungstragende Token des Produktnamens zurück.

    Algorithmus:
    1. Name + Brand mit normalize_for_matching tokenisieren
    2. Brand-Tokens überspringen
    3. Stopwords überspringen
    4. Tokens, die mit Ziffer starten, überspringen (z.B. "98", "0.5")
    5. Erstes verbleibendes Token → Hauptbegriff
    Fallback: erstes Token des normalisierten Namens

    Beispiele:
      "Bitburger Pilsener (Mehrweg)" / "BITBURGER" → "pilsener"
        (kein besserer Begrif verfügbar; Nutzer kann auf "bier" korrigieren)
      "Bärenmarke Ergiebige Kaffeemilch" / "BÄRENMARKE" → "kaffeemilch"
      "Mövenpick 100% Direktsaft" / "MÖVENPICK" → "direktsaft"
      "Barilla Pasta Nudeln Fusilli No 98" / "BARILLA" → "pasta"
    """
    brand_tokens = set(_nm(brand).split())
    tokens = _nm(name).split()
    for token in tokens:
        if token in brand_tokens:
            continue
        if token in _STOPWORDS:
            continue
        if re.match(r"^\d", token):
            continue
        return token
    # Fallback: erstes Token des Namens, auch wenn es Brand oder Stopword ist
    return tokens[0] if tokens else ""
