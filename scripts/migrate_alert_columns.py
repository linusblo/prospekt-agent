#!/usr/bin/env python3
"""
Phase C3 Migration: Alert-Spalten + alerts_sent-Tabelle.

SQL-Statements (kein DROP, kein DELETE, kein UPDATE bestehender Daten):

  ALTER TABLE wishlist_items ADD COLUMN alert_enabled        INTEGER NOT NULL DEFAULT 0
  ALTER TABLE wishlist_items ADD COLUMN alert_max_base_price REAL
  ALTER TABLE wishlist_items ADD COLUMN alert_max_total_price REAL
  ALTER TABLE wishlist_items ADD COLUMN alert_recipients     TEXT
  ALTER TABLE wishlist_items ADD COLUMN alert_only_green     INTEGER NOT NULL DEFAULT 0

  CREATE TABLE IF NOT EXISTS alerts_sent (...)
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

_NEW_WISHLIST_COLUMNS: list[tuple[str, str]] = [
    ("alert_enabled",         "INTEGER NOT NULL DEFAULT 0"),
    ("alert_max_base_price",  "REAL"),
    ("alert_max_total_price", "REAL"),
    ("alert_recipients",      "TEXT"),
    ("alert_only_green",      "INTEGER NOT NULL DEFAULT 0"),
]

_CREATE_ALERTS_SENT = """
CREATE TABLE IF NOT EXISTS alerts_sent (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    wishlist_item_name TEXT  NOT NULL,
    offer_source     TEXT  NOT NULL,
    offer_slug       TEXT  NOT NULL,
    alert_type       TEXT  NOT NULL,
    sent_at          TEXT  NOT NULL,
    recipients       TEXT  NOT NULL,
    valid_from       TEXT,
    UNIQUE(wishlist_item_name, offer_source, offer_slug, alert_type, valid_from)
)
"""


def main() -> None:
    db_path = os.getenv("DB_PATH", "data/offers.db")
    if not Path(db_path).exists():
        print(f"DB nicht gefunden: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    added = skipped = 0
    try:
        for col_name, col_def in _NEW_WISHLIST_COLUMNS:
            sql = f"ALTER TABLE wishlist_items ADD COLUMN {col_name} {col_def}"
            try:
                conn.execute(sql)
                conn.commit()
                print(f"  ✅ wishlist_items.{col_name} hinzugefügt")
                added += 1
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    print(f"  ℹ️  wishlist_items.{col_name} existiert bereits")
                    skipped += 1
                else:
                    raise

        conn.execute(_CREATE_ALERTS_SENT)
        conn.commit()
        print("  ✅ Tabelle alerts_sent bereit.")

    finally:
        conn.close()

    print(f"\nFertig: {added} Spalten hinzugefügt, {skipped} übersprungen.")


if __name__ == "__main__":
    main()
