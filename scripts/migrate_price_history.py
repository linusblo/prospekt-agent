#!/usr/bin/env python3
"""
Legt die Tabelle price_history + Indexe an und befüllt sie initial
mit den aktuellen Daten aus der offers-Tabelle.

SQL-Statements (kein DROP, kein UPDATE, kein DELETE):

  1. CREATE TABLE IF NOT EXISTS price_history (...)
     UNIQUE(source, product_slug, scraped_at)

  2. CREATE INDEX IF NOT EXISTS idx_price_history_lookup
        ON price_history(source, brand, name, sales_unit_raw)

  3. CREATE INDEX IF NOT EXISTS idx_price_history_date
        ON price_history(scraped_at)

  4. INSERT OR IGNORE INTO price_history (...) SELECT ... FROM offers
     (Initialer Datenkopie — idempotent dank INSERT OR IGNORE)
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS price_history (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    source                TEXT    NOT NULL,
    product_slug          TEXT    NOT NULL,
    brand                 TEXT,
    name                  TEXT    NOT NULL,
    sale_price            REAL    NOT NULL,
    original_price        REAL,
    discount_percent      REAL,
    base_price_value      REAL,
    base_price_value_max  REAL,
    base_price_unit       TEXT,
    base_price_has_prefix INTEGER NOT NULL DEFAULT 0,
    card_price            REAL,
    card_base_price_value REAL,
    sales_unit_raw        TEXT,
    valid_from            TEXT,
    valid_until           TEXT,
    scraped_at            TEXT    NOT NULL,
    UNIQUE(source, product_slug, scraped_at)
)
"""

_CREATE_INDEX_LOOKUP = """
CREATE INDEX IF NOT EXISTS idx_price_history_lookup
    ON price_history(source, brand, name, sales_unit_raw)
"""

_CREATE_INDEX_DATE = """
CREATE INDEX IF NOT EXISTS idx_price_history_date
    ON price_history(scraped_at)
"""

_COPY_FROM_OFFERS = """
INSERT OR IGNORE INTO price_history (
    source, product_slug, brand, name,
    sale_price, original_price, discount_percent,
    base_price_value, base_price_value_max, base_price_unit,
    base_price_has_prefix, card_price, card_base_price_value,
    sales_unit_raw, valid_from, valid_until, scraped_at
)
SELECT
    source, product_slug, brand, name,
    sale_price, original_price, discount_percent,
    base_price_value, base_price_value_max, base_price_unit,
    COALESCE(base_price_has_prefix, 0),
    card_price, card_base_price_value,
    sales_unit_raw, valid_from, valid_until, scraped_at
FROM offers
"""


def main() -> None:
    db_path = os.getenv("DB_PATH", "data/offers.db")
    if not Path(db_path).exists():
        print(f"DB nicht gefunden: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    try:
        # Tabelle + Indexe
        conn.execute(_CREATE_TABLE)
        conn.execute(_CREATE_INDEX_LOOKUP)
        conn.execute(_CREATE_INDEX_DATE)
        conn.commit()
        print("✅ Tabelle price_history + Indexe bereit.")

        # Zähle vorhandene Einträge vor der Kopie
        before = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]

        # Initialer Datenkopie
        conn.execute(_COPY_FROM_OFFERS)
        conn.commit()

        after = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        copied = after - before
        print(f"✅ {copied} Einträge aus offers kopiert ({after} Gesamt in price_history).")

        # Offers-Zahl zum Vergleich
        offers_total = conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
        print(f"   (offers-Tabelle hat {offers_total} Einträge)")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
