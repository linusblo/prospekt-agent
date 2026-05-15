from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .wishlist import Wishlist, WishlistItem

# ---------------------------------------------------------------------------
# Einheiten-Konvertierung
# ---------------------------------------------------------------------------

_UNIT_FAMILY: dict[str, str] = {
    "L": "volume", "ml": "volume", "cl": "volume",
    "kg": "weight", "g": "weight",
    "Stk": "count",
}

_TO_BASE: dict[str, float] = {
    "L": 1.0, "ml": 0.001, "cl": 0.01,
    "kg": 1.0, "g": 0.001,
    "Stk": 1.0,
}

# ---------------------------------------------------------------------------
# Food-Filter
# ---------------------------------------------------------------------------

FOOD_CATEGORY_IDS: frozenset[str] = frozenset({
    "Angebote",
    "markenprodukte", "frisches-obst-gemuese", "fruchtgummi",
    "cola-limo-schorlen", "meine-metzgerei", "pralinen-schoko-snacks",
    "grill-beilagen", "tiefkuehlpizza", "gefluegel",
    "sekt-weinhaltige-getraenke", "bbq", "milch-milchgetraenke",
    "eisbecher-toppings", "fertig-salate-sandwiches", "snack-time",
    "sommer-eis-desserts", "bier", "muesli-haferflocken",
    "joghurt-quark-milchdesserts", "frische-backwaren", "mein-bestes",
    "grillfleisch-grillwurst", "bio", "schwein", "gemischtes-hackfleisch",
    "tiefkuehlfisch-dosenfisch", "protein", "eistee", "mineralwasser",
    "schokoriegel", "broetchen-croissants", "wuerstchen-snackwurst",
    "alkoholfreie-getraenke", "milsani", "nuesse-trockenfruechte",
    "trader-joes", "chips-salzgebaeck", "schinken-salami",
    "sommer-getraenke", "neu-bei-aldi", "choceur", "brot-toast",
})

NON_FOOD_CATEGORY_IDS: frozenset[str] = frozenset({
    "batterien-akkus-feuerzeuge",
})


# ---------------------------------------------------------------------------
# Ergebnis-Typen
# ---------------------------------------------------------------------------

@dataclass
class _MatchResult:
    """Interner Typ: ein einzelnes gematchtes Angebot (vor der Gruppierung)."""
    wishlist_item: WishlistItem
    offer: dict
    matched_on: list[str]


@dataclass
class MatchedProduct:
    """
    Öffentlicher Typ: ein Produkt, ggf. bei mehreren Märkten verfügbar.

    primary_offer:          günstigstes Angebot (niedrigster sale_price,
                            bei Gleichstand niedrigster base_price_value)
    primary_market_count:   Anzahl identischer Einträge im selben Markt
                            (Aldi hat manchmal denselben Artikel mehrfach)
    alternative_offers:     Angebote des gleichen Produkts bei anderen Märkten,
                            sortiert nach Preis — leer wenn nur ein Markt
    wishlist_item:          das zugehörige Wishlist-Item
    """
    wishlist_item: WishlistItem
    primary_offer: dict
    primary_market_count: int = 1
    alternative_offers: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------

class Matcher:
    def __init__(self, wishlist: Wishlist, food_only: bool = True) -> None:
        self._wishlist = wishlist
        self._food_only = food_only

    def match_all(self, offers: list[dict]) -> dict[str, list[MatchedProduct]]:
        """Gibt für jedes aktive WishlistItem die MatchedProducts zurück."""
        return {
            item.name: self.match_item(item, offers)
            for item in self._wishlist.active_items
        }

    def match_item(self, item: WishlistItem, offers: list[dict]) -> list[MatchedProduct]:
        """
        1. Filter-Phase: alle Offers gegen Wishlist-Item testen
        2. Zwei-Phasen-Gruppierung:
           Phase 1 — Within-Market-Dedup: (brand, name, price, unit, source)
           Phase 2 — Cross-Market-Merge: (brand, name, unit) nur über versch. Sources
        """
        raw: list[_MatchResult] = []
        for offer in offers:
            passed, matched_on = self._passes_filters(item, offer)
            if passed:
                raw.append(_MatchResult(wishlist_item=item, offer=offer, matched_on=matched_on))
        return _group_cross_market(raw)

    # ------------------------------------------------------------------
    # Filter-Logik (unverändert)
    # ------------------------------------------------------------------

    def _passes_filters(self, item: WishlistItem, offer: dict) -> tuple[bool, list[str]]:
        matched_on: list[str] = []

        if self._food_only and not item.categories:
            if not self._is_food(offer):
                return False, []

        if item.brand or item.allowed_brands:
            if not self._matches_brand(item, offer):
                return False, []
            matched_on.append("brand")

        search_terms = {item.name} | set(item.keywords)
        if not _matches_words(search_terms, _offer_text(offer)):
            return False, []
        matched_on.append("keywords")

        if item.exclude_keywords:
            if _matches_words(set(item.exclude_keywords), _offer_text(offer)):
                return False, []

        if item.max_price is not None:
            if (offer.get("sale_price") or 0.0) > item.max_price:
                return False, []
            matched_on.append("price")

        if item.min_discount_percent is not None:
            discount = offer.get("discount_percent")
            if discount is None or discount < item.min_discount_percent:
                return False, []
            matched_on.append("discount")

        if item.unit_filter is not None or item.min_quantity is not None:
            if not self._matches_unit_and_quantity(item, offer):
                return False, []
            if item.unit_filter:
                matched_on.append("unit")
            if item.min_quantity is not None:
                matched_on.append("quantity")

        if item.excluded_packaging:
            if not self._passes_packaging(item.excluded_packaging, offer):
                return False, []

        if item.categories:
            offer_cats = _parse_category_ids(offer.get("category_ids"))
            if not any(c in offer_cats for c in item.categories):
                return False, []
            matched_on.append("category")

        if item.supermarkets:
            if (offer.get("source") or "") not in item.supermarkets:
                return False, []

        return True, matched_on

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
            return item.unit_filter is None
        offer_unit = su.get("unit")
        offer_qty = float(su.get("quantity") or 0.0)
        offer_mult = int(su.get("multiplier") or 1)
        if item.unit_filter is not None:
            filter_family = _UNIT_FAMILY.get(item.unit_filter)
            offer_family = _UNIT_FAMILY.get(offer_unit) if offer_unit else None
            if filter_family != offer_family:
                return False
        if item.min_quantity is not None and offer_unit is not None:
            offer_in_base = offer_qty * offer_mult * _TO_BASE.get(offer_unit, 0.0)
            base_factor = _TO_BASE.get(item.unit_filter, 1.0) if item.unit_filter else 1.0
            if offer_in_base < item.min_quantity * base_factor:
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
        if cats & NON_FOOD_CATEGORY_IDS:
            return False
        return bool(cats & FOOD_CATEGORY_IDS)


# ---------------------------------------------------------------------------
# Zwei-Phasen-Gruppierung
# ---------------------------------------------------------------------------

def _group_cross_market(results: list[_MatchResult]) -> list[MatchedProduct]:
    """
    Phase 1 — Within-Market-Dedup:
      Schlüssel: (brand, name, sale_price, sales_unit_raw, source)
      → Identische Aldi-Duplikate werden kollabiert (Zähler primary_market_count)

    Phase 2 — Cross-Market-Merge:
      Schlüssel: (brand, name, sales_unit_raw)
      → Nur über VERSCHIEDENE sources zusammenführen.
        Gleiche source + verschiedener Preis = verschiedene Produkte → separat.
    """
    if not results:
        return []

    wishlist_item = results[0].wishlist_item

    # ---------- Phase 1: Within-Market-Dedup ----------
    within: dict[tuple, list[_MatchResult]] = {}
    for r in results:
        o = r.offer
        key = (
            (o.get("brand") or "").lower(),
            (o.get("name") or "").lower(),
            o.get("sale_price"),
            (o.get("sales_unit_raw") or "").lower(),
            o.get("source") or "",
        )
        within.setdefault(key, []).append(r)

    # Reduzierte Liste: ein Offer pro Gruppe mit Zähler
    deduped: list[tuple[dict, int]] = [
        (group[0].offer, len(group)) for group in within.values()
    ]

    # ---------- Phase 2: Cross-Market-Merge ----------
    # Gruppieren nach (brand, name, unit)
    cross: dict[tuple, list[tuple[dict, int]]] = {}
    for offer, count in deduped:
        key = (
            (offer.get("brand") or "").lower(),
            (offer.get("name") or "").lower(),
            (offer.get("sales_unit_raw") or "").lower(),
        )
        cross.setdefault(key, []).append((offer, count))

    out: list[MatchedProduct] = []

    for group in cross.values():
        # Offers nach Source aufteilen
        by_source: dict[str, list[tuple[dict, int]]] = {}
        for offer, count in group:
            src = offer.get("source") or ""
            by_source.setdefault(src, []).append((offer, count))

        if len(by_source) == 1:
            # Nur eine Source → kein Cross-Market-Merge, Einträge bleiben separat
            for offer, count in group:
                out.append(MatchedProduct(
                    wishlist_item=wishlist_item,
                    primary_offer=offer,
                    primary_market_count=count,
                    alternative_offers=[],
                ))
        else:
            # Mehrere Sources → je Source das günstigste Angebot wählen.
            # Teurere Angebote derselben Source werden als eigenständige
            # MatchedProducts ohne Alternativen ausgegeben.
            source_bests: list[tuple[dict, int]] = []
            for src_offers in by_source.values():
                src_offers.sort(key=lambda oc: oc[0].get("sale_price") or 999.0)
                source_bests.append(src_offers[0])
                # "Extra"-Varianten derselben Source (verschiedene Preise)
                for extra_offer, extra_count in src_offers[1:]:
                    out.append(MatchedProduct(
                        wishlist_item=wishlist_item,
                        primary_offer=extra_offer,
                        primary_market_count=extra_count,
                        alternative_offers=[],
                    ))

            # Bestes Angebot über alle Sources wählen
            source_bests.sort(key=lambda oc: (
                oc[0].get("sale_price") or 999.0,
                oc[0].get("base_price_value") or 999.0,
            ))
            primary_offer, primary_count = source_bests[0]
            alternatives = [o for o, _ in source_bests[1:]]

            out.append(MatchedProduct(
                wishlist_item=wishlist_item,
                primary_offer=primary_offer,
                primary_market_count=primary_count,
                alternative_offers=alternatives,
            ))

    return out


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _offer_text(offer: dict) -> str:
    name = (offer.get("name") or "").lower()
    brand = (offer.get("brand") or "").lower()
    return f"{name} {brand}"


def _matches_words(terms: set[str], text: str) -> bool:
    for term in terms:
        if re.search(r"\b" + re.escape(term.lower()) + r"\b", text):
            return True
    return False


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
