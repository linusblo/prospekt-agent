"""
Übersichts-URLs pro Daten-Source.

get_overview_url() gibt die Angebots-Übersichtsseite des jeweiligen Markts
zurück — für alle Sources identisch nutzbar, unabhängig vom Produkt-Slug.

Edeka und Combi sind filialspezifisch und lesen die konfigurierte ID aus
settings (EDEKA_MARKET_ID, COMBI_STORE_ID).

Gibt None zurück wenn die Source unbekannt ist → kein Link rendern.
"""
from __future__ import annotations


def get_overview_url(source: str) -> str | None:
    if source == "aldi_nord":
        return "https://www.aldi-nord.de/angebote.html"
    if source == "kaufland":
        return "https://filiale.kaufland.de/angebote/uebersicht.html"
    if source == "trinkgut":
        return "https://www.trinkgut.de/angebote"
    if source == "edeka":
        from src.config.settings import settings
        return f"https://www.edeka.de/maerkte/{settings.EDEKA_MARKET_ID}/angebote/"
    if source == "combi":
        from src.config.settings import settings
        return f"https://www.combi.de/alle_angebote_{settings.COMBI_STORE_ID}.html"
    return None
