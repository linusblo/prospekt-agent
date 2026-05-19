from __future__ import annotations

MARKET_DISPLAY_NAMES: dict[str, str] = {
    "aldi_nord": "Aldi Nord",
    "kaufland":  "Kaufland",
    "trinkgut":  "Trinkgut",
    "lidl":      "Lidl",
    "rewe":      "Rewe",
    "edeka":     "Edeka",
    "combi":     "Combi",
    "penny":     "Penny",
    "netto":     "Netto",
}


def get_display_name(slug: str) -> str:
    return MARKET_DISPLAY_NAMES.get(slug, slug)
