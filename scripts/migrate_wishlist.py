#!/usr/bin/env python3
"""
Migriert wishlist.yaml einmalig in die SQLite-Datenbank.

Idempotent: Mehrfaches Ausführen aktualisiert vorhandene Einträge,
legt keine Duplikate an. wishlist.yaml wird NICHT gelöscht.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from src.db.repository import OfferRepository
from src.matching.wishlist import Wishlist


def main() -> None:
    wishlist_path = Path("wishlist.yaml")
    if not wishlist_path.exists():
        print(f"Fehler: {wishlist_path} nicht gefunden.")
        sys.exit(1)

    db_path = os.getenv("DB_PATH", "data/offers.db")

    print(f"Lese {wishlist_path} …")
    wishlist = Wishlist.from_yaml(wishlist_path)
    print(f"  {len(wishlist.items)} Einträge gefunden.")

    print(f"Verbinde mit Datenbank: {db_path}")
    repo = OfferRepository(db_path)

    inserted = updated = 0
    for item in wishlist.items:
        result = repo.upsert_wishlist_item(item)
        if result == "inserted":
            inserted += 1
            print(f"  + Neu:           {item.name}")
        else:
            updated += 1
            print(f"  ~ Aktualisiert:  {item.name}")

    print(f"\nFertig: {inserted} neu eingefügt, {updated} aktualisiert.")
    print("wishlist.yaml bleibt erhalten, wird aber von run_agent.py nicht mehr gelesen.")


if __name__ == "__main__":
    main()
