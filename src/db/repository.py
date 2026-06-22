from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

log = logging.getLogger(__name__)

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
    created_at, updated_at,
    alert_enabled, alert_max_base_price, alert_max_total_price,
    alert_recipients, alert_only_green
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,  ?, ?, ?, ?, ?)
ON CONFLICT(name) DO UPDATE SET
    brand                 = excluded.brand,
    allowed_brands        = excluded.allowed_brands,
    keywords              = excluded.keywords,
    exclude_keywords      = excluded.exclude_keywords,
    excluded_packaging    = excluded.excluded_packaging,
    categories            = excluded.categories,
    max_price             = excluded.max_price,
    min_discount_percent  = excluded.min_discount_percent,
    unit_filter           = excluded.unit_filter,
    min_quantity          = excluded.min_quantity,
    supermarkets          = excluded.supermarkets,
    active                = excluded.active,
    notes                 = excluded.notes,
    updated_at            = excluded.updated_at,
    alert_enabled         = excluded.alert_enabled,
    alert_max_base_price  = excluded.alert_max_base_price,
    alert_max_total_price = excluded.alert_max_total_price,
    alert_recipients      = excluded.alert_recipients,
    alert_only_green      = excluded.alert_only_green
"""

_INSERT_WISHLIST = """
INSERT INTO wishlist_items (
    name, brand, allowed_brands, keywords, exclude_keywords,
    excluded_packaging, categories, max_price, min_discount_percent,
    unit_filter, min_quantity, supermarkets, active, notes,
    created_at, updated_at,
    alert_enabled, alert_max_base_price, alert_max_total_price,
    alert_recipients, alert_only_green
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,  ?, ?, ?, ?, ?)
"""

_UPDATE_WISHLIST_BY_ID = """
UPDATE wishlist_items SET
    name                  = ?,
    brand                 = ?,
    allowed_brands        = ?,
    keywords              = ?,
    exclude_keywords      = ?,
    excluded_packaging    = ?,
    categories            = ?,
    max_price             = ?,
    min_discount_percent  = ?,
    unit_filter           = ?,
    min_quantity          = ?,
    supermarkets          = ?,
    active                = ?,
    notes                 = ?,
    updated_at            = ?,
    alert_enabled         = ?,
    alert_max_base_price  = ?,
    alert_max_total_price = ?,
    alert_recipients      = ?,
    alert_only_green      = ?
WHERE id = ?
"""

# ---------------------------------------------------------------------------
# Alerts-Sent-Tabelle
# ---------------------------------------------------------------------------

_CREATE_ALERTS_SENT_TABLE = """
CREATE TABLE IF NOT EXISTS alerts_sent (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    wishlist_item_name TEXT    NOT NULL,
    offer_source       TEXT    NOT NULL,
    offer_slug         TEXT    NOT NULL,
    alert_type         TEXT    NOT NULL,
    sent_at            TEXT    NOT NULL,
    recipients         TEXT    NOT NULL,
    valid_from         TEXT,
    UNIQUE(wishlist_item_name, offer_source, offer_slug, alert_type, valid_from)
)
"""

# ---------------------------------------------------------------------------
# Shopping-List-Tabelle
# ---------------------------------------------------------------------------

_CREATE_SHOPPING_LIST_TABLE = """
CREATE TABLE IF NOT EXISTS shopping_list (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_source    TEXT    NOT NULL,
    offer_slug      TEXT    NOT NULL,
    product_name    TEXT    NOT NULL,
    brand           TEXT,
    sale_price      REAL,
    original_price  REAL,
    base_price_text TEXT,
    sales_unit      TEXT,
    market_name     TEXT    NOT NULL,
    added_at        TEXT    NOT NULL,
    checked         INTEGER NOT NULL DEFAULT 0,
    notes           TEXT,
    UNIQUE(offer_source, offer_slug)
)
"""

# ---------------------------------------------------------------------------
# Wishlist-Excludes-Tabelle
# ---------------------------------------------------------------------------

_CREATE_WISHLIST_EXCLUDES_TABLE = """
CREATE TABLE IF NOT EXISTS wishlist_excludes (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    -- wishlist_item_id referenziert wishlist_items.id (numerisch, stabil).
    -- Falls ein Item gelöscht und neu angelegt wird, bekommt es eine neue ID;
    -- verwaiste Excludes bleiben dann in der Tabelle, schaden aber nicht.
    wishlist_item_id   INTEGER NOT NULL,
    offer_source       TEXT    NOT NULL,
    brand_norm         TEXT    NOT NULL,   -- normalize_for_matching(brand)[:32]
    name_norm          TEXT    NOT NULL,   -- normalize_for_matching(name)[:40]
    excluded_at        TEXT    NOT NULL,
    UNIQUE(wishlist_item_id, offer_source, brand_norm, name_norm)
)
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
            conn.execute(_CREATE_SHOPPING_LIST_TABLE)
            conn.execute(_CREATE_WISHLIST_EXCLUDES_TABLE)
            conn.execute(_CREATE_PRICE_HISTORY_TABLE)
            conn.execute(_CREATE_HISTORY_INDEX_LOOKUP)
            conn.execute(_CREATE_HISTORY_INDEX_DATE)
            conn.execute(_CREATE_ALERTS_SENT_TABLE)
            # Idempotente Schema-Migrationen für bestehende DBs
            _add_column_if_missing(conn, "offers", "card_price",                "REAL")
            _add_column_if_missing(conn, "offers", "base_price_value_max",      "REAL")
            _add_column_if_missing(conn, "offers", "base_price_has_prefix",     "INTEGER NOT NULL DEFAULT 0")
            _add_column_if_missing(conn, "offers", "card_base_price_value",     "REAL")
            _add_column_if_missing(conn, "offers", "card_base_price_value_max", "REAL")
            _add_column_if_missing(conn, "offers", "card_base_price_unit",      "TEXT")
            _add_column_if_missing(conn, "offers", "card_discount_percent",     "REAL")
            # Phase C3: Alert-Spalten in wishlist_items
            _add_column_if_missing(conn, "wishlist_items", "alert_enabled",         "INTEGER NOT NULL DEFAULT 0")
            _add_column_if_missing(conn, "wishlist_items", "alert_max_base_price",  "REAL")
            _add_column_if_missing(conn, "wishlist_items", "alert_max_total_price", "REAL")
            _add_column_if_missing(conn, "wishlist_items", "alert_recipients",      "TEXT")
            _add_column_if_missing(conn, "wishlist_items", "alert_only_green",      "INTEGER NOT NULL DEFAULT 0")

    # ------------------------------------------------------------------
    # Offers
    # ------------------------------------------------------------------

    def upsert_offer(self, offer: Offer) -> None:
        if offer.sale_price <= 0:
            log.debug("Überspringe '%s': Preis %.2f €", offer.name, offer.sale_price)
            return
        with self._connection() as conn:
            conn.execute(_UPSERT_OFFER, _offer_to_row(offer))

    def upsert_many(self, offers: list[Offer]) -> int:
        valid   = [o for o in offers if o.sale_price > 0]
        skipped = len(offers) - len(valid)
        if skipped:
            log.info("Überspringe %d Angebote mit Preis 0.00 €", skipped)
        with self._connection() as conn:
            conn.executemany(_UPSERT_OFFER, [_offer_to_row(o) for o in valid])
        return len(valid)

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

    def search_offers(self, query: str) -> list[dict]:
        """
        Case-insensitive Volltextsuche über name/brand/short_description/
        long_description aktiver Angebote. Mehrere durch Leerzeichen getrennte
        Wörter werden UND-verknüpft (jedes muss als Substring vorkommen).
        Sortiert nach discount_percent DESC, dann sale_price ASC.
        """
        words = query.strip().lower().split()
        if not words:
            return []
        matches = [o for o in self.get_active_offers() if _offer_matches_words(o, words)]
        matches.sort(key=lambda o: (-(o.get("discount_percent") or 0), o.get("sale_price") or 0))
        return matches

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

    def delete_all_offers_for_source(self, source: str) -> int:
        """
        Löscht ALLE Offers einer Source — nützlich für Adapter ohne Datums-Felder
        (z.B. Trinkgut), damit veraltete Angebote nicht akkumulieren.
        price_history bleibt UNANGETASTET.
        Gibt Anzahl gelöschter Einträge zurück.
        """
        with self._connection() as conn:
            cur = conn.execute(
                "DELETE FROM offers WHERE source = ?", (source,)
            )
            return cur.rowcount

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

    # ------------------------------------------------------------------
    # Shopping-List
    # ------------------------------------------------------------------

    def add_to_shopping_list(self, offer_data: dict) -> int:
        """
        Fügt ein Angebot zur Einkaufsliste hinzu.
        Duplikate (gleiche source + slug) werden via INSERT OR IGNORE ignoriert.
        Gibt die neue (oder bestehende) id zurück.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO shopping_list
                    (offer_source, offer_slug, product_name, brand,
                     sale_price, original_price, base_price_text,
                     sales_unit, market_name, added_at)
                VALUES (?,?,?,?, ?,?,?, ?,?,?)
                """,
                (
                    offer_data.get("offer_source") or "",
                    offer_data.get("offer_slug") or "",
                    offer_data.get("product_name") or "",
                    offer_data.get("brand"),
                    offer_data.get("sale_price"),
                    offer_data.get("original_price"),
                    offer_data.get("base_price_text"),
                    offer_data.get("sales_unit"),
                    offer_data.get("market_name") or "",
                    now,
                ),
            )
            row = conn.execute(
                "SELECT id FROM shopping_list WHERE offer_source=? AND offer_slug=?",
                (offer_data.get("offer_source") or "", offer_data.get("offer_slug") or ""),
            ).fetchone()
            return row[0] if row else -1

    def remove_from_shopping_list(self, item_id: int) -> None:
        """Entfernt einen Eintrag aus der Einkaufsliste."""
        with self._connection() as conn:
            conn.execute("DELETE FROM shopping_list WHERE id = ?", (item_id,))

    def toggle_checked(self, item_id: int) -> None:
        """Wechselt den abgehakt-Status eines Eintrags."""
        with self._connection() as conn:
            conn.execute(
                "UPDATE shopping_list SET checked = CASE WHEN checked=1 THEN 0 ELSE 1 END WHERE id=?",
                (item_id,),
            )

    def get_shopping_list(self) -> list[dict]:
        """Gibt alle Einträge sortiert nach Markt und Produktname zurück."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM shopping_list ORDER BY market_name, product_name"
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_shopping_list(self) -> None:
        """Löscht alle Einträge aus der Einkaufsliste."""
        with self._connection() as conn:
            conn.execute("DELETE FROM shopping_list")

    def clear_checked_items(self) -> None:
        """Löscht nur abgehakte Einträge."""
        with self._connection() as conn:
            conn.execute("DELETE FROM shopping_list WHERE checked = 1")

    def is_on_shopping_list(self, source: str, slug: str) -> bool:
        """Prüft ob ein Angebot bereits auf der Einkaufsliste ist."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM shopping_list WHERE offer_source=? AND offer_slug=?",
                (source, slug),
            ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Wishlist-Excludes
    # ------------------------------------------------------------------

    def add_exclude(
        self,
        wishlist_item_id: int,
        source: str,
        brand_norm: str,
        name_norm: str,
    ) -> None:
        """Schließt ein Produkt dauerhaft aus den Treffern eines Wishlist-Items aus.
        Duplikate werden via INSERT OR IGNORE ignoriert."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO wishlist_excludes
                    (wishlist_item_id, offer_source, brand_norm, name_norm, excluded_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (wishlist_item_id, source, brand_norm, name_norm, now),
            )

    def remove_exclude(self, exclude_id: int) -> None:
        """Hebt einen Ausschluss auf (WHERE id = ?)."""
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM wishlist_excludes WHERE id = ?", (exclude_id,)
            )

    def get_excludes_for_item(self, wishlist_item_id: int) -> list[dict]:
        """Gibt alle Ausschlüsse eines Wishlist-Items zurück."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM wishlist_excludes WHERE wishlist_item_id = ?"
                " ORDER BY excluded_at DESC",
                (wishlist_item_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_excludes_as_matcher_dict(
        self,
    ) -> dict[str, set[tuple[str, str, str]]]:
        """
        Gibt alle Ausschlüsse in der Form zurück, die der Matcher erwartet:
          {wishlist_item_name → {(source, brand_norm, name_norm), ...}}
        """
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT wi.name AS item_name,
                       we.offer_source, we.brand_norm, we.name_norm
                FROM wishlist_excludes we
                JOIN wishlist_items wi ON wi.id = we.wishlist_item_id
                """
            ).fetchall()
        result: dict[str, set[tuple[str, str, str]]] = {}
        for row in rows:
            result.setdefault(row["item_name"], set()).add(
                (row["offer_source"], row["brand_norm"], row["name_norm"])
            )
        return result

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
        """UPDATE WHERE id = ?"""
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
            now,
            int(item.alert_enabled),
            item.alert_max_base_price,
            item.alert_max_total_price,
            json.dumps(item.alert_recipients),
            int(item.alert_only_green),
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

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def has_alert_been_sent(
        self,
        wishlist_item_name: str,
        source: str,
        slug: str,
        alert_type: str,
        valid_from: str | None,
    ) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM alerts_sent
                WHERE wishlist_item_name = ?
                  AND offer_source = ?
                  AND offer_slug   = ?
                  AND alert_type   = ?
                  AND (valid_from = ? OR (valid_from IS NULL AND ? IS NULL))
                """,
                (wishlist_item_name, source, slug, alert_type, valid_from, valid_from),
            ).fetchone()
        return row is not None

    def save_alert_sent(
        self,
        wishlist_item_name: str,
        source: str,
        slug: str,
        alert_type: str,
        valid_from: str | None,
        recipients: list[str],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO alerts_sent
                    (wishlist_item_name, offer_source, offer_slug,
                     alert_type, sent_at, recipients, valid_from)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (wishlist_item_name, source, slug, alert_type,
                 now, json.dumps(recipients), valid_from),
            )

    def count_alerts_sent_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM alerts_sent WHERE sent_at >= ?", (today,)
            ).fetchone()[0]


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

_SEARCH_FIELDS = ("name", "brand", "short_description", "long_description")


def _offer_matches_words(offer: dict, words: list[str]) -> bool:
    """True wenn jedes Wort in `words` als Substring in einem der Suchfelder
    vorkommt (case-insensitive, UND-verknüpft über alle Wörter)."""
    haystack = " ".join(offer.get(field) or "" for field in _SEARCH_FIELDS).lower()
    return all(word in haystack for word in words)


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
        now,   # created_at
        now,   # updated_at
        int(item.alert_enabled),
        item.alert_max_base_price,
        item.alert_max_total_price,
        json.dumps(item.alert_recipients),
        int(item.alert_only_green),
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
        alert_enabled=bool(row["alert_enabled"] or 0),
        alert_max_base_price=row["alert_max_base_price"],
        alert_max_total_price=row["alert_max_total_price"],
        alert_recipients=_jload(row["alert_recipients"]),
        alert_only_green=bool(row["alert_only_green"] or 0),
    )
