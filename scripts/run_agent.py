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
from src.adapters.kaufland import KauflandAdapter
from src.adapters.trinkgut import TrinkgutAdapter
from src.adapters.base import SupermarketAdapter
from src.config.settings import settings
from src.db.repository import OfferRepository
from src.matching.matcher import Matcher
from src.matching.wishlist import Wishlist

ADAPTERS: list[SupermarketAdapter] = [
    AldiNordAdapter(),
    KauflandAdapter(),
    TrinkgutAdapter(),
]


def main() -> None:
    log.info("Prospekt-Agent gestartet")

    db_path = os.getenv("DB_PATH", "data/offers.db")
    repo = OfferRepository(db_path)

    # ── Abgelaufene Angebote bereinigen ──
    cleaned = repo.cleanup_expired_offers()
    if cleaned:
        log.info("Bereinigt: %d abgelaufene Angebote gelöscht", cleaned)

    # ── Angebote von allen Adaptern laden ──
    # Adapter ohne Datums-Felder vorab bereinigen
    # (Trinkgut hat kein valid_until → veraltete Einträge akkumulieren sonst)
    _SOURCES_WITHOUT_DATES = {"trinkgut"}

    total_offers = 0
    for adapter in ADAPTERS:
        if adapter.source_name in _SOURCES_WITHOUT_DATES:
            deleted = repo.delete_all_offers_for_source(adapter.source_name)
            if deleted:
                log.info("Trinkgut: %d veraltete Einträge vor dem Scrapen gelöscht", deleted)

        log.info("Lade Angebote von %s …", adapter.source_name)
        try:
            offers = adapter.fetch_offers()
            if offers:
                repo.upsert_many(offers)
                repo.save_price_history_batch(offers)
                total_offers += len(offers)
                log.info("  %d Angebote gespeichert, %d neue Historieneinträge",
                         len(offers), len(offers))
            else:
                log.warning("  Keine Angebote gefunden")
        except Exception:
            log.error("  Fehler bei %s", adapter.source_name, exc_info=True)

    if total_offers == 0:
        log.error("Keine Angebote von keinem Adapter – Abbruch.")
        sys.exit(1)

    log.info("Gesamt: %d Angebote in DB (%d gesamt)", total_offers, repo.count())

    # ── Wishlist laden ──
    wishlist = Wishlist.from_db(db_path)
    if not wishlist.items:
        log.warning("Keine Wishlist-Einträge in DB. Bitte 'python scripts/migrate_wishlist.py' ausführen.")
        return
    log.info("%d aktive Wunschlisten-Einträge", len(wishlist.active_items))

    # ── Matching über alle aktiven Angebote ──
    active_offers = repo.get_active_offers()
    matcher = Matcher(wishlist, food_only=True, repository=repo)
    results_by_item = matcher.match_all(active_offers)

    any_match = False
    for item_name, products in results_by_item.items():
        if not products:
            continue
        any_match = True
        print(f"\n{'='*62}")
        print(f"  {item_name}  —  {len(products)} Treffer")
        print(f"{'='*62}")
        for mp in products:
            _print_offer(mp.primary_offer, mp.primary_market_count, mp.alternative_offers)

    if not any_match:
        print("\nKeine Wunschlisten-Treffer in den aktuellen Angeboten.")

    # ── E-Mail-Alarme prüfen ──
    if settings.email_configured:
        from src.notifications.email_sender import EmailSender
        from src.notifications.alert_checker import check_and_send_alerts

        all_products = [mp for prods in results_by_item.values() for mp in prods]
        sender = EmailSender(settings)
        sent = check_and_send_alerts(
            all_products, repo, sender, settings.DEFAULT_ALERT_RECIPIENTS
        )
        if sent:
            log.info("%d Alarm-E-Mail(s) versendet.", sent)
        else:
            log.info("Keine Alarme ausgelöst.")
    else:
        log.info("E-Mail nicht konfiguriert → Alarm-Prüfung übersprungen.")

    log.info("Fertig.")


def _print_offer(o: dict, duplicate_count: int = 1, alternatives: list[dict] | None = None) -> None:
    name       = o.get("name") or "?"
    brand      = o.get("brand") or ""
    source     = o.get("source") or ""
    price      = o.get("sale_price") or 0.0
    original   = o.get("original_price")
    base_val   = o.get("base_price_value")
    base_unit  = o.get("base_price_unit") or ""
    unit_raw   = o.get("sales_unit_raw") or ""
    valid_until = (o.get("valid_until") or "")[:10] or "?"
    card_price = o.get("card_price")

    header = f"  • [{source}] {name}"
    if duplicate_count > 1:
        header += f"  ({duplicate_count}x im Sortiment)"
    print(header)

    price_str = f"{price:.2f} €"
    if original:
        savings  = original - price
        discount = o.get("discount_percent") or 0.0
        price_str += f"  (statt {original:.2f} €  |  -{discount:.0f}%  |  spare {savings:.2f} €)"
    if card_price:
        price_str += f"  |  Card: {card_price:.2f} €"
    print(f"    Preis:      {price_str}")

    if unit_raw:
        content_str = unit_raw
        if base_val and base_unit:
            content_str += f"   →   {base_val:.2f} € / {base_unit}"
        print(f"    Inhalt:     {content_str}")

    print(f"    Gültig bis: {valid_until}")
    if brand:
        print(f"    Marke:      {brand}")
    if alternatives:
        from src.config.markets import get_display_name
        for alt in alternatives:
            alt_price = alt.get("sale_price") or 0.0
            alt_market = get_display_name(alt.get("source") or "")
            print(f"    Auch bei:   {alt_market} — {alt_price:.2f} €")


if __name__ == "__main__":
    main()
