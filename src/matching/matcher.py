from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .wishlist import Wishlist, WishlistItem
from src.analysis.price_rating import PriceRating, rate_offer
from src.utils.text_normalize import normalize_for_matching

if TYPE_CHECKING:
    from src.db.repository import OfferRepository

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
    variant_names:          Alle Produkt-Namen die zur selben Aktion gehören
                            (gleicher Markt, gleicher Preis, gleiche Verpackung).
                            Enthält immer mind. den primary_offer.name.
                            Leer = kein Varianten-Grouping durchgeführt.
    wishlist_item:          das zugehörige Wishlist-Item
    price_rating:           Ampel-Bewertung (None wenn kein Repository übergeben)
    """
    wishlist_item: WishlistItem
    primary_offer: dict
    primary_market_count: int = 1
    alternative_offers: list[dict] = field(default_factory=list)
    variant_names: list[str] = field(default_factory=list)
    price_rating: PriceRating | None = None


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------

class Matcher:
    def __init__(
        self,
        wishlist: Wishlist,
        food_only: bool = True,
        repository: OfferRepository | None = None,
        excluded: dict[str, set[tuple[str, str, str]]] | None = None,
    ) -> None:
        """
        excluded: {wishlist_item_name → {(source, brand_norm, name_norm), ...}}
                  Nur die Excludes des jeweiligen Items werden auf seine Treffer
                  angewendet — kein ungewollter Überlauf zwischen Items.
        """
        self._wishlist    = wishlist
        self._food_only   = food_only
        self._repo        = repository
        self._excluded    = excluded or {}

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
        3. Optionale Ampel-Bewertung (wenn repository übergeben)
        """
        raw: list[_MatchResult] = []
        for offer in offers:
            passed, matched_on = self._passes_filters(item, offer)
            if passed:
                raw.append(_MatchResult(wishlist_item=item, offer=offer, matched_on=matched_on))

        # Produkt-spezifische Ausschlüsse für dieses Wishlist-Item anwenden.
        # Nur self._excluded.get(item.name) — kein globaler Überlauf auf andere Items.
        excl_for_item = self._excluded.get(item.name, set())
        if excl_for_item:
            raw = [r for r in raw if _make_excl_key(r.offer) not in excl_for_item]

        products = _group_cross_market(raw)
        if self._repo is not None:
            for mp in products:
                o = mp.primary_offer
                mp.price_rating = rate_offer(
                    source           = o.get("source") or "",
                    brand            = o.get("brand")  or "",
                    name             = o.get("name")   or "",
                    sales_unit_raw   = o.get("sales_unit_raw") or "",
                    current_price    = o.get("sale_price") or 0.0,
                    current_base_price = o.get("base_price_value"),
                    repository       = self._repo,
                )
        return products

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
        """
        Prüft Brand-Filter mit Wortgrenzen auf normalisiertem Text.
        Erlaubt z.B. 'COCA-COLA' in allowed_brands zu matchen, wenn die
        Offer-Brand 'COCA-COLA, FANTA, SPRITE' lautet.
        """
        offer_brand_norm = normalize_for_matching(offer.get("brand") or "")
        if item.brand:
            item_norm = normalize_for_matching(item.brand)
            if not item_norm:
                return True
            return bool(re.search(r"\b" + re.escape(item_norm) + r"\b", offer_brand_norm))
        if item.allowed_brands:
            for allowed in item.allowed_brands:
                allowed_norm = normalize_for_matching(allowed)
                if not allowed_norm:
                    continue
                if re.search(r"\b" + re.escape(allowed_norm) + r"\b", offer_brand_norm):
                    return True
            return False
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
      → Identische Duplikate kollabiert (Zähler primary_market_count)

    Phase 1.5 (NEU) — Variant-Grouping:
      Schlüssel: (source, brand, sale_price, sales_unit_raw, valid_from, valid_until)
      → Gleicher Markt, gleicher Preis, gleiche Packung, aber VERSCHIEDENE Namen
        = Sorten-Varianten → zu einem MatchedProduct zusammengefasst,
          alle Namen in variant_names gespeichert.
      → Verschiedene Preise bei gleicher Source bleiben separat.

    Phase 2 — Cross-Market-Merge:
      Schlüssel: (brand, name, sales_unit_raw)
      → Nur über VERSCHIEDENE sources zusammenführen.
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

    # Ein Eintrag pro Gruppe mit Duplikat-Zähler
    deduped: list[tuple[dict, int]] = [
        (group[0].offer, len(group)) for group in within.values()
    ]

    # ---------- Phase 1.5: Variant-Grouping ----------
    # Key: (source, brand, price, unit, valid_from, valid_until) — ohne name!
    variant_groups: dict[tuple, list[tuple[dict, int]]] = {}
    for offer, count in deduped:
        key = (
            offer.get("source") or "",
            (offer.get("brand") or "").lower(),
            offer.get("sale_price"),
            (offer.get("sales_unit_raw") or "").lower(),
            offer.get("valid_from") or "",
            offer.get("valid_until") or "",
        )
        variant_groups.setdefault(key, []).append((offer, count))

    # Repräsentant + alle Namen
    variant_deduped: list[tuple[dict, int, list[str]]] = []
    for group in variant_groups.values():
        rep_offer, rep_count = group[0]
        all_names = [o.get("name") or "" for o, _ in group]
        variant_deduped.append((rep_offer, rep_count, all_names))

    # ---------- Phase 2: Cross-Market-Merge ----------
    cross: dict[tuple, list[tuple[dict, int, list[str]]]] = {}
    for (offer, count, names) in variant_deduped:
        key = (
            (offer.get("brand") or "").lower(),
            (offer.get("name") or "").lower(),
            (offer.get("sales_unit_raw") or "").lower(),
        )
        cross.setdefault(key, []).append((offer, count, names))

    out: list[MatchedProduct] = []

    for group in cross.values():
        by_source: dict[str, list[tuple[dict, int, list[str]]]] = {}
        for offer, count, names in group:
            src = offer.get("source") or ""
            by_source.setdefault(src, []).append((offer, count, names))

        if len(by_source) == 1:
            for offer, count, names in group:
                out.append(MatchedProduct(
                    wishlist_item=wishlist_item,
                    primary_offer=offer,
                    primary_market_count=count,
                    alternative_offers=[],
                    variant_names=names,
                ))
        else:
            source_bests: list[tuple[dict, int, list[str]]] = []
            for src_offers in by_source.values():
                src_offers.sort(key=lambda oc: oc[0].get("sale_price") or 999.0)
                source_bests.append(src_offers[0])
                for extra_offer, extra_count, extra_names in src_offers[1:]:
                    out.append(MatchedProduct(
                        wishlist_item=wishlist_item,
                        primary_offer=extra_offer,
                        primary_market_count=extra_count,
                        alternative_offers=[],
                        variant_names=extra_names,
                    ))

            source_bests.sort(key=lambda oc: (
                oc[0].get("sale_price") or 999.0,
                oc[0].get("base_price_value") or 999.0,
            ))
            primary_offer, primary_count, primary_names = source_bests[0]
            alternatives = [o for o, _, _ in source_bests[1:]]

            out.append(MatchedProduct(
                wishlist_item=wishlist_item,
                primary_offer=primary_offer,
                primary_market_count=primary_count,
                alternative_offers=alternatives,
                variant_names=primary_names,
            ))

    return out


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _offer_text(offer: dict) -> str:
    """
    Gibt normalisierten Such-Text aus name + brand zurück.
    Bindestriche, Kommas, Schrägstriche → Leerzeichen, damit
    \b-Wortgrenzen konsistent funktionieren.

    Beispiel: brand "COCA-COLA" → "coca cola" im Suchtext.
    """
    name  = offer.get("name")  or ""
    brand = offer.get("brand") or ""
    return normalize_for_matching(f"{name} {brand}")


def _matches_words(terms: set[str], text: str) -> bool:
    """
    Prüft ob mind. 1 Begriff mit Wortgrenzen im Text vorkommt.
    Beide Seiten werden normalisiert, damit Sonderzeichen kein Problem sind.
    """
    for term in terms:
        normalized = normalize_for_matching(term)
        if re.search(r"\b" + re.escape(normalized) + r"\b", text):
            return True
    return False


def _make_excl_key(offer: dict) -> tuple[str, str, str]:
    """
    Baut den Ausschluss-Schlüssel (source, brand_norm, name_norm) für ein Angebot.
    Dieselbe Normalisierung wie der Matcher → konsistentes Matching.
    """
    return (
        offer.get("source") or "",
        normalize_for_matching(offer.get("brand") or "")[:32],
        normalize_for_matching(offer.get("name")  or "")[:40],
    )


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
