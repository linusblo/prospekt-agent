from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .wishlist import Wishlist, WishlistItem

# ---------------------------------------------------------------------------
# Einheiten-Konvertierung
# ---------------------------------------------------------------------------

# Familiengruppen: welche Einheiten sind vergleichbar
_UNIT_FAMILY: dict[str, str] = {
    "L": "volume", "ml": "volume", "cl": "volume",
    "kg": "weight", "g": "weight",
    "Stk": "count",
}

# Konvertierung zur Basiseinheit (L für Volumen, kg für Gewicht)
_TO_BASE: dict[str, float] = {
    "L": 1.0, "ml": 0.001, "cl": 0.01,
    "kg": 1.0, "g": 0.001,
    "Stk": 1.0,
}

# ---------------------------------------------------------------------------
# Food-Filter
# Basiert auf DB-Analyse (Stand 2026-05-13, 291 Produkte).
# HINWEIS: Viele Non-Food-Artikel (Kleidung, Garten) haben NUR "Angebote"
# als Kategorie – für die ist exclude_keywords im WishlistItem das
# bessere Werkzeug als dieser Filter.
# ---------------------------------------------------------------------------

FOOD_CATEGORY_IDS: frozenset[str] = frozenset({
    # Catch-All (alle Angebote-Seite Produkte)
    "Angebote",
    # Bekannte Food-Subcategories aus DB
    "markenprodukte",
    "frisches-obst-gemuese",
    "fruchtgummi",
    "cola-limo-schorlen",
    "meine-metzgerei",
    "pralinen-schoko-snacks",
    "grill-beilagen",
    "tiefkuehlpizza",
    "gefluegel",
    "sekt-weinhaltige-getraenke",
    "bbq",
    "milch-milchgetraenke",
    "eisbecher-toppings",
    "fertig-salate-sandwiches",
    "snack-time",
    "sommer-eis-desserts",
    "bier",
    "muesli-haferflocken",
    "joghurt-quark-milchdesserts",
    "frische-backwaren",
    "mein-bestes",
    "grillfleisch-grillwurst",
    "bio",
    "schwein",
    "gemischtes-hackfleisch",
    "tiefkuehlfisch-dosenfisch",
    "protein",
    "eistee",
    "mineralwasser",
    "schokoriegel",
    "broetchen-croissants",
    "wuerstchen-snackwurst",
    "alkoholfreie-getraenke",
    "milsani",
    "nuesse-trockenfruechte",
    "trader-joes",
    "chips-salzgebaeck",
    "schinken-salami",
    "sommer-getraenke",
    "neu-bei-aldi",
    "choceur",
    "brot-toast",
})

NON_FOOD_CATEGORY_IDS: frozenset[str] = frozenset({
    "batterien-akkus-feuerzeuge",
    # Weitere Non-Food-Kategorien hier ergänzen
})


# ---------------------------------------------------------------------------
# Ergebnis-Typen
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    wishlist_item: WishlistItem
    offer: dict
    matched_on: list[str]
    duplicate_count: int = 1


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------

class Matcher:
    def __init__(self, wishlist: Wishlist, food_only: bool = True) -> None:
        self._wishlist = wishlist
        self._food_only = food_only

    def match_all(self, offers: list[dict]) -> dict[str, list[MatchResult]]:
        """Gibt für jedes aktive WishlistItem die passenden Offers zurück."""
        return {
            item.name: self.match_item(item, offers)
            for item in self._wishlist.active_items
        }

    def match_item(self, item: WishlistItem, offers: list[dict]) -> list[MatchResult]:
        results: list[MatchResult] = []
        for offer in offers:
            passed, matched_on = self._passes_filters(item, offer)
            if passed:
                results.append(MatchResult(
                    wishlist_item=item,
                    offer=offer,
                    matched_on=matched_on,
                ))
        return _dedup(results)

    # ------------------------------------------------------------------

    def _passes_filters(self, item: WishlistItem, offer: dict) -> tuple[bool, list[str]]:
        matched_on: list[str] = []

        # Food-Filter (nur wenn item keine expliziten Kategorien hat)
        if self._food_only and not item.categories:
            if not self._is_food(offer):
                return False, []

        # Marken-Filter (case-insensitive)
        if item.brand or item.allowed_brands:
            if not self._matches_brand(item, offer):
                return False, []
            matched_on.append("brand")

        # Keyword-Matching: Wortgrenzen, nur name+brand, OR-Logik
        search_terms = {item.name} | set(item.keywords)
        if not _matches_words(search_terms, _offer_text(offer)):
            return False, []
        matched_on.append("keywords")

        # Exclude-Keywords: Wortgrenzen, nur name+brand
        if item.exclude_keywords:
            if _matches_words(set(item.exclude_keywords), _offer_text(offer)):
                return False, []

        # Preis-Filter
        if item.max_price is not None:
            if (offer.get("sale_price") or 0.0) > item.max_price:
                return False, []
            matched_on.append("price")

        # Rabatt-Filter
        if item.min_discount_percent is not None:
            discount = offer.get("discount_percent")
            if discount is None or discount < item.min_discount_percent:
                return False, []
            matched_on.append("discount")

        # Einheiten- + Mengen-Filter
        if item.unit_filter is not None or item.min_quantity is not None:
            if not self._matches_unit_and_quantity(item, offer):
                return False, []
            if item.unit_filter:
                matched_on.append("unit")
            if item.min_quantity is not None:
                matched_on.append("quantity")

        # Verpackungs-Ausschluss
        if item.excluded_packaging:
            if not self._passes_packaging(item.excluded_packaging, offer):
                return False, []

        # Explizite Kategorie-Filter
        if item.categories:
            offer_cats = _parse_category_ids(offer.get("category_ids"))
            if not any(c in offer_cats for c in item.categories):
                return False, []
            matched_on.append("category")

        # Supermarkt-Filter
        if item.supermarkets:
            if (offer.get("source") or "") not in item.supermarkets:
                return False, []

        return True, matched_on

    # ------------------------------------------------------------------

    def _matches_brand(self, item: WishlistItem, offer: dict) -> bool:
        offer_brand = (offer.get("brand") or "").lower()
        if item.brand:
            return offer_brand == item.brand.lower()
        if item.allowed_brands:
            return offer_brand in {b.lower() for b in item.allowed_brands}
        return True

    def _matches_unit_and_quantity(self, item: WishlistItem, offer: dict) -> bool:
        su = _get_sales_unit(offer)
        if su is None:
            # Kein geparster salesUnit → nur durchlassen wenn kein strikter Filter
            return item.unit_filter is None

        offer_unit = su.get("unit")  # z.B. "g", "ml", "L", "kg"
        offer_qty = float(su.get("quantity") or 0.0)
        offer_mult = int(su.get("multiplier") or 1)

        # Einheiten-Familien-Check: "kg" matched "g", "L" matched "ml"
        if item.unit_filter is not None:
            filter_family = _UNIT_FAMILY.get(item.unit_filter)
            offer_family = _UNIT_FAMILY.get(offer_unit) if offer_unit else None
            if filter_family != offer_family:
                return False

        # Mengen-Check: immer in Basiseinheit (kg / L)
        if item.min_quantity is not None and offer_unit is not None:
            offer_in_base = offer_qty * offer_mult * _TO_BASE.get(offer_unit, 0.0)
            # min_quantity ist in der Einheit von unit_filter → in Basis umrechnen
            base_factor = _TO_BASE.get(item.unit_filter, 1.0) if item.unit_filter else 1.0
            min_in_base = item.min_quantity * base_factor
            if offer_in_base < min_in_base:
                return False

        return True

    def _passes_packaging(self, excluded_packaging: list[str], offer: dict) -> bool:
        su = _get_sales_unit(offer)
        if su is None:
            return True
        packaging = (su.get("packaging") or "").lower()
        return not any(p.lower() in packaging for p in excluded_packaging)

    def _is_food(self, offer: dict) -> bool:
        cats = _parse_category_ids(offer.get("category_ids"))
        # Explizit Non-Food → raus
        if cats & NON_FOOD_CATEGORY_IDS:
            return False
        # Mindestens eine bekannte Food-Kategorie → drin
        return bool(cats & FOOD_CATEGORY_IDS)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _offer_text(offer: dict) -> str:
    """Nur name + brand für Keyword-Matching (NICHT description)."""
    name = (offer.get("name") or "").lower()
    brand = (offer.get("brand") or "").lower()
    return f"{name} {brand}"


def _matches_words(terms: set[str], text: str) -> bool:
    """True wenn mind. 1 Begriff mit Wortgrenzen (\b) im Text vorkommt."""
    for term in terms:
        if re.search(r"\b" + re.escape(term.lower()) + r"\b", text):
            return True
    return False


def _dedup(results: list[MatchResult]) -> list[MatchResult]:
    """Deduplicates by (brand, name, sale_price, sales_unit_raw)."""
    seen: dict[tuple, MatchResult] = {}
    for r in results:
        o = r.offer
        key = (
            (o.get("brand") or "").lower(),
            (o.get("name") or "").lower(),
            o.get("sale_price"),
            (o.get("sales_unit_raw") or "").lower(),
        )
        if key in seen:
            seen[key].duplicate_count += 1
        else:
            seen[key] = r
    return list(seen.values())


def _get_sales_unit(offer: dict) -> dict | None:
    raw = offer.get("sales_unit_json")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _parse_category_ids(raw: object) -> set[str]:
    if isinstance(raw, set):
        return raw
    if isinstance(raw, list):
        return set(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return set(parsed)
        except json.JSONDecodeError:
            pass
    return set()
