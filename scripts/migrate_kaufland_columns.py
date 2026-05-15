#!/usr/bin/env python3
"""
Fügt 6 neue Spalten zur offers-Tabelle hinzu (idempotent).

SQL-Statements (werden einzeln ausgeführt, kein DROP/UPDATE/DELETE):
  ALTER TABLE offers ADD COLUMN base_price_value_max      REAL;
  ALTER TABLE offers ADD COLUMN base_price_has_prefix     INTEGER NOT NULL DEFAULT 0;
  ALTER TABLE offers ADD COLUMN card_base_price_value     REAL;
  ALTER TABLE offers ADD COLUMN card_base_price_value_max REAL;
  ALTER TABLE offers ADD COLUMN card_base_price_unit      TEXT;
  ALTER TABLE offers ADD COLUMN card_discount_percent     REAL;

Bestehende Aldi-Einträge erhalten NULL für REAL/TEXT-Spalten
und 0 für die INTEGER-Spalte.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

_NEW_COLUMNS: list[tuple[str, str]] = [
    ("base_price_value_max",      "REAL"),
    ("base_price_has_prefix",     "INTEGER NOT NULL DEFAULT 0"),
    ("card_base_price_value",     "REAL"),
    ("card_base_price_value_max", "REAL"),
    ("card_base_price_unit",      "TEXT"),
    ("card_discount_percent",     "REAL"),
]


def main() -> None:
    db_path = os.getenv("DB_PATH", "data/offers.db")
    if not Path(db_path).exists():
        print(f"DB nicht gefunden: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    added = skipped = 0
    try:
        for col_name, col_def in _NEW_COLUMNS:
            sql = f"ALTER TABLE offers ADD COLUMN {col_name} {col_def}"
            try:
                conn.execute(sql)
                conn.commit()
                print(f"  ✅ {col_name} hinzugefügt")
                added += 1
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    print(f"  ℹ️  {col_name} existiert bereits – übersprungen")
                    skipped += 1
                else:
                    raise
    finally:
        conn.close()

    print(f"\nFertig: {added} hinzugefügt, {skipped} bereits vorhanden.")


if __name__ == "__main__":
    main()
