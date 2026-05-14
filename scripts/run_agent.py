#!/usr/bin/env python3
"""Einstiegspunkt: Angebote laden, speichern, gegen Wunschliste abgleichen."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_agent")

from src.adapters.aldi_nord import AldiNordAdapter
from src.db.repository import OfferRepository
from src.matching.matcher import Matcher
from src.matching.wishlist import Wishlist


def main() -> None:
    log.info("Prospekt-Agent gestartet")

    adapter = AldiNordAdapter()
    log.info("Lade Angebote von %s …", adapter.source_name)
    offers = adapter.fetch_offers()

    if not offers:
        log.error("Keine Angebote gefunden – Abbruch.")
        sys.exit(1)

    db_path = os.getenv("DB_PATH", "data/offers.db")
    repo = OfferRepository(db_path)
    repo.upsert_many(offers)
    log.info(
        "%d Angebote gespeichert in %s (Datenbank gesamt: %d)",
        len(offers), db_path, repo.count(),
    )

    wishlist = Wishlist.from_db(db_path)
    if not wishlist.items:
        log.warning("Keine Wishlist-Einträge in DB. Bitte 'python scripts/migrate_wishlist.py' ausführen.")
        return
    log.info("%d aktive Wunschlisten-Einträge", len(wishlist.active_items))

    active_offers = repo.get_active_offers(source=adapter.source_name)
    matcher = Matcher(wishlist, food_only=True)
    results_by_item = matcher.match_all(active_offers)

    any_match = False
    for item_name, match_results in results_by_item.items():
        if not match_results:
            continue
        any_match = True
        print(f"\n{'='*62}")
        print(f"  {item_name}  —  {len(match_results)} Treffer")
        print(f"{'='*62}")
        for r in match_results:
            o = r.offer
            _print_offer(o, r.duplicate_count)

    if not any_match:
        print("\nKeine Wunschlisten-Treffer in den aktuellen Angeboten.")

    log.info("Fertig.")


def _print_offer(o: dict, duplicate_count: int = 1) -> None:
    name = o.get("name") or "?"
    brand = o.get("brand") or ""
    price = o.get("sale_price") or 0.0
    original = o.get("original_price")
    base_val = o.get("base_price_value")
    base_unit = o.get("base_price_unit") or ""
    unit_raw = o.get("sales_unit_raw") or ""
    valid_until = (o.get("valid_until") or "")[:10] or "?"

    # Kopfzeile
    header = f"  • {name}"
    if duplicate_count > 1:
        header += f"  ({duplicate_count}x im Sortiment)"
    print(header)

    # Preis-Zeile
    price_str = f"{price:.2f} €"
    if original:
        savings = original - price
        discount = o.get("discount_percent") or 0.0
        price_str += f"  (statt {original:.2f} €  |  -{discount:.0f}%  |  spare {savings:.2f} €)"
    print(f"    Preis:      {price_str}")

    # Inhalt + Basispreis
    if unit_raw:
        content_str = unit_raw
        if base_val and base_unit:
            content_str += f"   →   {base_val:.2f} € / {base_unit}"
        print(f"    Inhalt:     {content_str}")

    print(f"    Gültig bis: {valid_until}")
    if brand:
        print(f"    Marke:      {brand}")


if __name__ == "__main__":
    main()
