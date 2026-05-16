from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from ..models.offer import Offer
from ..matching.wishlist import WishlistItem

# ---------------------------------------------------------------------------
# Offers-Tabelle
# ---------------------------------------------------------------------------

_CREATE_OFFERS_TABLE = """
CREATE TABLE IF NOT EXISTS offers (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT    NOT NULL,
    product_slug        TEXT    NOT NULL,
    name                TEXT    NOT NULL,
    brand               TEXT,
    short_description   TEXT,
    long_description    TEXT,
    sale_price          REAL    NOT NULL,
    original_price      REAL,
    discount_percent    REAL,
    base_price_value    REAL,
    base_price_value_max REAL,
    base_price_unit     TEXT,
    base_price_has_prefix INTEGER NOT NULL DEFAULT 0,
    sales_unit_raw      TEXT,
    sales_unit_json     TEXT,
    is_deposit_product  INTEGER NOT NULL DEFAULT 0,
    deposit_value       REAL,
    valid_from          TEXT,
    valid_until         TEXT,
    image_url           TEXT,
    category_ids        TEXT,
    scraped_at          TEXT    NOT NULL,
    card_price          REAL,
    card_base_price_value     REAL,
    card_base_price_value_max REAL,
    card_base_price_unit      TEXT,
    card_discount_percent     REAL,
    UNIQUE(source, product_slug)
)
"""

_UPSERT_OFFER = """
INSERT INTO offers (
    source, product_slug, name, brand,
    short_description, long_description,
    sale_price, original_price, discount_percent,
    base_price_value, base_price_value_max, base_price_unit, base_price_has_prefix,
    sales_unit_raw, sales_unit_json,
    is_deposit_product, deposit_value,
    valid_from, valid_until,
    image_url, category_ids, scraped_at,
    card_price, card_base_price_value, card_base_price_value_max,
    card_base_price_unit, card_discount_percent
) VALUES (
    ?,?,?,?,  ?,?,  ?,?,?,
    ?,?,?,?,  ?,?,  ?,?,  ?,?,
    ?,?,?,
    ?,?,?,?,?
)
ON CONFLICT(source, product_slug) DO UPDATE SET
    name                      = excluded.name,
    brand                     = excluded.brand,
    short_description         = excluded.short_description,
    long_description          = excluded.long_description,
    sale_price                = excluded.sale_price,
    original_price            = excluded.original_price,
    discount_percent          = excluded.discount_percent,
    base_price_value          = excluded.base_price_value,
    base_price_value_max      = excluded.base_price_value_max,
    base_price_unit           = excluded.base_price_unit,
    base_price_has_prefix     = excluded.base_price_has_prefix,
    sales_unit_raw            = excluded.sales_unit_raw,
    sales_unit_json           = excluded.sales_unit_json,
    is_deposit_product        = excluded.is_deposit_product,
    deposit_value             = excluded.deposit_value,
    valid_from                = excluded.valid_from,
    valid_until               = excluded.valid_until,
    image_url                 = excluded.image_url,
    category_ids              = excluded.category_ids,
    scraped_at                = excluded.scraped_at,
    card_price                = excluded.card_price,
    card_base_price_value     = excluded.card_base_price_value,
    card_base_price_value_max = excluded.card_base_price_value_max,
    card_base_price_unit      = excluded.card_base_price_unit,
    card_discount_percent     = excluded.card_discount_percent
"""

# ---------------------------------------------------------------------------
# Wishlist-Tabelle
# ---------------------------------------------------------------------------

_CREATE_WISHLIST_TABLE = """
CREATE TABLE IF NOT EXISTS wishlist_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL UNIQUE,
    brand               TEXT,
    allowed_brands      TEXT    NOT NULL DEFAULT '[]',
    keywords            TEXT    NOT NULL DEFAULT '[]',
    exclude_keywords    TEXT    NOT NULL DEFAULT '[]',
    excluded_packaging  TEXT    NOT NULL DEFAULT '[]',
    categories          TEXT    NOT NULL DEFAULT '[]',
    max_price           REAL,
    min_discount_percent REAL,
    unit_filter         TEXT,
    min_quantity        REAL,
    supermarkets        TEXT    NOT NULL DEFAULT '[]',
    active              INTEGER NOT NULL DEFAULT 1,
    notes               TEXT,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL
)
"""

_UPSERT_WISHLIST = """
INSERT INTO wishlist_items (
    name, brand, allowed_brands, keywords, exclude_keywords,
    excluded_packaging, categories, max_price, min_discount_percent,
    unit_filter, min_quantity, supermarkets, active, notes,
    created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(name) DO UPDATE SET
    brand               = excluded.brand,
    allowed_brands      = excluded.allowed_brands,
    keywords            = excluded.keywords,
    exclude_keywords    = excluded.exclude_keywords,
    excluded_packaging  = excluded.excluded_packaging,
    categories          = excluded.categories,
    max_price           = excluded.max_price,
    min_discount_percent = excluded.min_discount_percent,
    unit_filter         = excluded.unit_filter,
    min_quantity        = excluded.min_quantity,
    supermarkets        = excluded.supermarkets,
    active              = excluded.active,
    notes               = excluded.notes,
    updated_at          = excluded.updated_at
"""

_INSERT_WISHLIST = """
INSERT INTO wishlist_items (
    name, brand, allowed_brands, keywords, exclude_keywords,
    excluded_packaging, categories, max_price, min_discount_percent,
    unit_filter, min_quantity, supermarkets, active, notes,
    created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_UPDATE_WISHLIST_BY_ID = """
UPDATE wishlist_items SET
    name                 = ?,
    brand                = ?,
    allowed_brands       = ?,
    keywords             = ?,
    exclude_keywords     = ?,
    excluded_packaging   = ?,
    categories           = ?,
    max_price            = ?,
    min_discount_percent = ?,
    unit_filter          = ?,
    min_quantity         = ?,
    supermarkets         = ?,
    active               = ?,
    notes                = ?,
    updated_at           = ?
WHERE id = ?
"""

# ---------------------------------------------------------------------------
# Price-History-Tabelle
# ---------------------------------------------------------------------------

_CREATE_PRICE_HISTORY_TABLE = """
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

_CREATE_HISTORY_INDEX_LOOKUP = """
CREATE INDEX IF NOT EXISTS idx_price_history_lookup
    ON price_history(source, brand, name, sales_unit_raw)
"""

_CREATE_HISTORY_INDEX_DATE = """
CREATE INDEX IF NOT EXISTS idx_price_history_date
    ON price_history(scraped_at)
"""

_INSERT_HISTORY = """
INSERT OR IGNORE INTO price_history (
    source, product_slug, brand, name,
    sale_price, original_price, discount_percent,
    base_price_value, base_price_value_max, base_price_unit,
    base_price_has_prefix, card_price, card_base_price_value,
    sales_unit_raw, valid_from, valid_until, scraped_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class OfferRepository:
    def __init__(self, db_path: str = "data/offers.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute(_CREATE_OFFERS_TABLE)
            conn.execute(_CREATE_WISHLIST_TABLE)
            conn.execute(_CREATE_PRICE_HISTORY_TABLE)
            conn.execute(_CREATE_HISTORY_INDEX_LOOKUP)
            conn.execute(_CREATE_HISTORY_INDEX_DATE)
            # Idempotente Schema-Migrationen für bestehende DBs
            _add_column_if_missing(conn, "offers", "card_price",                "REAL")
            _add_column_if_missing(conn, "offers", "base_price_value_max",      "REAL")
            _add_column_if_missing(conn, "offers", "base_price_has_prefix",     "INTEGER NOT NULL DEFAULT 0")
            _add_column_if_missing(conn, "offers", "card_base_price_value",     "REAL")
            _add_column_if_missing(conn, "offers", "card_base_price_value_max", "REAL")
            _add_column_if_missing(conn, "offers", "card_base_price_unit",      "TEXT")
            _add_column_if_missing(conn, "offers", "card_discount_percent",     "REAL")

    # ------------------------------------------------------------------
    # Offers
    # ------------------------------------------------------------------

    def upsert_offer(self, offer: Offer) -> None:
        with self._connection() as conn:
            conn.execute(_UPSERT_OFFER, _offer_to_row(offer))

    def upsert_many(self, offers: list[Offer]) -> int:
        with self._connection() as conn:
            conn.executemany(_UPSERT_OFFER, [_offer_to_row(o) for o in offers])
        return len(offers)

    def get_active_offers(self, source: str | None = None) -> list[dict]:
        """Angebote deren valid_until in der Zukunft liegt (oder kein Datum gesetzt)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            query = "SELECT * FROM offers WHERE (valid_until IS NULL OR valid_until >= ?)"
            params: list[object] = [now]
            if source:
                query += " AND source = ?"
                params.append(source)
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_all_offers(self, source: str | None = None) -> list[dict]:
        with self._connection() as conn:
            query = "SELECT * FROM offers"
            params: list[object] = []
            if source:
                query += " WHERE source = ?"
                params.append(source)
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def count(self, source: str | None = None) -> int:
        with self._connection() as conn:
            query = "SELECT COUNT(*) FROM offers"
            params: list[object] = []
            if source:
                query += " WHERE source = ?"
                params.append(source)
            return conn.execute(query, params).fetchone()[0]

    # ------------------------------------------------------------------
    # Wishlist
    # ------------------------------------------------------------------

    def upsert_wishlist_item(self, item: WishlistItem) -> str:
        """Idempotenter Upsert per Name. Gibt 'inserted' oder 'updated' zurück."""
        now = datetime.now(timezone.utc).isoformat()
        exists = self._wishlist_name_exists(item.name)
        with self._connection() as conn:
            conn.execute(_UPSERT_WISHLIST, _wishlist_to_row(item, now))
        return "updated" if exists else "inserted"

    def get_wishlist_items(self, active_only: bool = False) -> list[WishlistItem]:
        with self._connection() as conn:
            query = "SELECT * FROM wishlist_items"
            if active_only:
                query += " WHERE active = 1"
            query += " ORDER BY id"
            rows = conn.execute(query).fetchall()
        return [_row_to_wishlist_item(row) for row in rows]

    def wishlist_count(self, active_only: bool = False) -> int:
        with self._connection() as conn:
            query = "SELECT COUNT(*) FROM wishlist_items"
            if active_only:
                query += " WHERE active = 1"
            return conn.execute(query).fetchone()[0]

    # ------------------------------------------------------------------
    # Price-History
    # ------------------------------------------------------------------

    def save_price_history_entry(self, offer: Offer) -> None:
        """Schreibt einen neuen Eintrag in price_history — KEIN UPSERT."""
        with self._connection() as conn:
            conn.execute(_INSERT_HISTORY, _history_row(offer))

    def save_price_history_batch(self, offers: list[Offer]) -> int:
        """Schreibt alle Offers als neue History-Einträge. Gibt Anzahl zurück."""
        with self._connection() as conn:
            conn.executemany(_INSERT_HISTORY, [_history_row(o) for o in offers])
        return len(offers)

    def count_price_history(self, source: str | None = None) -> int:
        with self._connection() as conn:
            query = "SELECT COUNT(*) FROM price_history"
            params: list[object] = []
            if source:
                query += " WHERE source = ?"
                params.append(source)
            return conn.execute(query, params).fetchone()[0]

    def cleanup_expired_offers(self) -> int:
        """
        Löscht abgelaufene Angebote aus der offers-Tabelle (valid_until < jetzt).
        NIEMALS aus price_history — die Historie bleibt für Ampel/Chart erhalten.
        Gibt Anzahl gelöschter Einträge zurück.
        """
        cutoff = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cur = conn.execute(
                "DELETE FROM offers WHERE valid_until IS NOT NULL AND valid_until < ?",
                (cutoff,),
            )
            return cur.rowcount

    def cleanup_old_history(self, days: int = 180) -> int:
        """
        Löscht Einträge älter als 'days' Tage.
        Vorbereitet für Phase C2 — noch NICHT automatisch aufgerufen.
        Gibt Anzahl der gelöschten Zeilen zurück.
        """
        from datetime import timedelta
        cutoff_str = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connection() as conn:
            cur = conn.execute(
                "DELETE FROM price_history WHERE scraped_at < ?", (cutoff_str,)
            )
            return cur.rowcount

    def get_price_history_for_product(
        self,
        source: str,
        brand_lower: str,
        name_lower: str,
        sales_unit_raw: str = "",
        days: int = 90,
    ) -> list[dict]:
        """
        Historische Preise der letzten N Tage für ein Produkt.
        Matching case-insensitiv auf brand, name, sales_unit_raw.
        """
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT sale_price, base_price_value, scraped_at
                FROM price_history
                WHERE source = ?
                  AND LOWER(COALESCE(brand, ''))          = ?
                  AND LOWER(COALESCE(name,  ''))          = ?
                  AND LOWER(COALESCE(sales_unit_raw, '')) = LOWER(?)
                  AND scraped_at >= ?
                ORDER BY scraped_at ASC
                """,
                (source, brand_lower, name_lower, sales_unit_raw, cutoff),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_price_history_for_chart(
        self,
        source: str,
        brand_lower: str,
        name_lower: str,
        sales_unit_raw: str = "",
        days: int = 90,
    ) -> list[tuple[str, float]]:
        """
        Aggregiert Preishistorie pro Tag (1 Punkt/Tag = Tagesdurchschnitt).
        Gibt Liste von (date_str, avg_price) zurück, sortiert nach Datum.
        """
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT DATE(scraped_at) AS day, AVG(sale_price) AS avg_price
                FROM price_history
                WHERE source = ?
                  AND LOWER(COALESCE(brand, ''))          = ?
                  AND LOWER(COALESCE(name,  ''))          = ?
                  AND LOWER(COALESCE(sales_unit_raw, '')) = LOWER(?)
                  AND scraped_at >= ?
                GROUP BY DATE(scraped_at)
                ORDER BY day ASC
                """,
                (source, brand_lower, name_lower, sales_unit_raw, cutoff),
            ).fetchall()
        return [(row["day"], row["avg_price"]) for row in rows]

    def get_distinct_products_from_history(self) -> list[dict]:
        """Alle verschiedenen Produkte in price_history (für Produkt-Selector)."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT source, brand, name, sales_unit_raw, COUNT(*) AS data_points
                FROM price_history
                GROUP BY source, LOWER(COALESCE(brand,'')),
                         LOWER(COALESCE(name,'')),
                         LOWER(COALESCE(sales_unit_raw,''))
                ORDER BY brand, name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------

    def add_wishlist_item(self, item: WishlistItem) -> int:
        """INSERT — schlägt mit IntegrityError fehl wenn name bereits existiert."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.execute(_INSERT_WISHLIST, _wishlist_to_row(item, now))
            return cursor.lastrowid  # type: ignore[return-value]

    def update_wishlist_item(self, item_id: int, item: WishlistItem) -> None:
        """UPDATE WHERE id = ?  (name + created_at bleiben veränderbar)"""
        now = datetime.now(timezone.utc).isoformat()
        row = (
            item.name,
            item.brand,
            json.dumps(item.allowed_brands),
            json.dumps(item.keywords),
            json.dumps(item.exclude_keywords),
            json.dumps(item.excluded_packaging),
            json.dumps(item.categories),
            item.max_price,
            item.min_discount_percent,
            item.unit_filter,
            item.min_quantity,
            json.dumps(item.supermarkets),
            int(item.active),
            item.notes,
            now,      # updated_at
            item_id,  # WHERE id = ?
        )
        with self._connection() as conn:
            conn.execute(_UPDATE_WISHLIST_BY_ID, row)

    def delete_wishlist_item(self, item_id: int) -> None:
        """DELETE FROM wishlist_items WHERE id = ?"""
        with self._connection() as conn:
            conn.execute("DELETE FROM wishlist_items WHERE id = ?", (item_id,))

    def toggle_wishlist_item_active(self, item_id: int) -> None:
        """UPDATE wishlist_items SET active = NOT active WHERE id = ?"""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                "UPDATE wishlist_items"
                " SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END,"
                "     updated_at = ?"
                " WHERE id = ?",
                (now, item_id),
            )

    def get_wishlist_rows(self) -> list[dict]:
        """Alle Einträge als Dicts inkl. id, created_at, updated_at (für Dashboard)."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM wishlist_items ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_wishlist_item_by_id(self, item_id: int) -> WishlistItem | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM wishlist_items WHERE id = ?", (item_id,)
            ).fetchone()
        return _row_to_wishlist_item(row) if row else None

    def get_distinct_brands(self) -> list[str]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT brand FROM offers"
                " WHERE brand IS NOT NULL ORDER BY brand"
            ).fetchall()
        return [r[0] for r in rows]

    def get_distinct_categories(self) -> list[str]:
        with self._connection() as conn:
            rows = conn.execute("SELECT DISTINCT category_ids FROM offers").fetchall()
        cats: set[str] = set()
        for row in rows:
            try:
                for cat in json.loads(row[0] or "[]"):
                    if cat != "Angebote":
                        cats.add(cat)
            except (json.JSONDecodeError, TypeError):
                pass
        return sorted(cats)

    def _wishlist_name_exists(self, name: str) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM wishlist_items WHERE name = ?", (name,)
            ).fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _offer_to_row(offer: Offer) -> tuple:
    return (
        offer.source.value,
        offer.product_slug,
        offer.name,
        offer.brand,
        offer.short_description,
        offer.long_description,
        offer.sale_price,
        offer.original_price,
        offer.discount_percent,
        offer.base_price_value,
        offer.base_price_value_max,
        offer.base_price_unit,
        int(offer.base_price_has_prefix),
        offer.sales_unit_raw,
        offer.sales_unit.model_dump_json() if offer.sales_unit else None,
        int(offer.is_deposit_product),
        offer.deposit_value,
        offer.valid_from.isoformat() if offer.valid_from else None,
        offer.valid_until.isoformat() if offer.valid_until else None,
        offer.image_url,
        json.dumps(offer.category_ids),
        offer.scraped_at.isoformat(),
        offer.card_price,
        offer.card_base_price_value,
        offer.card_base_price_value_max,
        offer.card_base_price_unit,
        offer.card_discount_percent,
    )


def _history_row(offer: Offer) -> tuple:
    return (
        offer.source.value,
        offer.product_slug,
        offer.brand,
        offer.name,
        offer.sale_price,
        offer.original_price,
        offer.discount_percent,
        offer.base_price_value,
        offer.base_price_value_max,
        offer.base_price_unit,
        int(offer.base_price_has_prefix),
        offer.card_price,
        offer.card_base_price_value,
        offer.sales_unit_raw,
        offer.valid_from.isoformat() if offer.valid_from else None,
        offer.valid_until.isoformat() if offer.valid_until else None,
        offer.scraped_at.isoformat(),
    )


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, col: str, definition: str
) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
    except sqlite3.OperationalError:
        pass  # Spalte existiert bereits


def _wishlist_to_row(item: WishlistItem, now: str) -> tuple:
    return (
        item.name,
        item.brand,
        json.dumps(item.allowed_brands),
        json.dumps(item.keywords),
        json.dumps(item.exclude_keywords),
        json.dumps(item.excluded_packaging),
        json.dumps(item.categories),
        item.max_price,
        item.min_discount_percent,
        item.unit_filter,
        item.min_quantity,
        json.dumps(item.supermarkets),
        int(item.active),
        item.notes,
        now,   # created_at — nur beim ersten INSERT gesetzt, danach nicht überschrieben
        now,   # updated_at — wird bei jedem Upsert aktualisiert
    )


def _row_to_wishlist_item(row: sqlite3.Row) -> WishlistItem:
    def _jload(val: str | None) -> list:
        if not val:
            return []
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return []

    return WishlistItem(
        name=row["name"],
        brand=row["brand"],
        allowed_brands=_jload(row["allowed_brands"]),
        keywords=_jload(row["keywords"]),
        exclude_keywords=_jload(row["exclude_keywords"]),
        excluded_packaging=_jload(row["excluded_packaging"]),
        categories=_jload(row["categories"]),
        max_price=row["max_price"],
        min_discount_percent=row["min_discount_percent"],
        unit_filter=row["unit_filter"],
        min_quantity=row["min_quantity"],
        supermarkets=_jload(row["supermarkets"]),
        active=bool(row["active"]),
        notes=row["notes"],
    )
