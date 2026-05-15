#!/usr/bin/env python3
"""
Fügt die Spalte 'card_price' zur offers-Tabelle hinzu (idempotent).

Wird automatisch auch beim Start des Agents / Dashboards durch
OfferRepository._init_db() ausgeführt. Dieses Skript ist für
explizite manuelle Ausführung gedacht.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


def main() -> None:
    db_path = os.getenv("DB_PATH", "data/offers.db")
    if not Path(db_path).exists():
        print(f"DB nicht gefunden: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("ALTER TABLE offers ADD COLUMN card_price REAL")
        conn.commit()
        print(f"✅ Spalte 'card_price' hinzugefügt: {db_path}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print(f"ℹ️  Spalte 'card_price' existiert bereits – nichts zu tun.")
        else:
            raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
