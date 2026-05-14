from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class WishlistItem(BaseModel):
    name: str
    # Marken-Filter: 'brand' (ein Wert, exakt) ODER 'allowed_brands' (Liste, OR-Logik)
    brand: str | None = None
    allowed_brands: list[str] = []
    # Keyword-Matching: mind. 1 muss in name/brand matchen (Wortgrenzen, OR-Logik)
    keywords: list[str] = []
    # Ausschlüsse
    exclude_keywords: list[str] = []     # Treffer verwerfen wenn eines vorkommt
    excluded_packaging: list[str] = []   # z.B. ["Dose", "Glas"]
    # Kategorien
    categories: list[str] = []
    # Preis-Filter
    max_price: float | None = None
    min_discount_percent: float | None = None
    # Einheiten-Filter (Wortgrenzen-Familie: "kg" matched auch "g"; "L" matched auch "ml")
    unit_filter: str | None = None
    min_quantity: float | None = None    # immer in Basis-Einheit (kg oder L)
    # Supermärkte-Filter
    supermarkets: list[str] = []         # leer = alle aktiven Adapter
    active: bool = True
    notes: str | None = None


class Wishlist(BaseModel):
    items: list[WishlistItem]

    @classmethod
    def from_yaml(cls, path: str | Path) -> Wishlist:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return cls(items=[WishlistItem(**item) for item in data.get("wishlist", [])])

    @classmethod
    def from_db(cls, db_path: str = "data/offers.db") -> Wishlist:
        """Lädt Wishlist aus der SQLite-Datenbank (Lazy Import um zirkuläre Abhängigkeit zu vermeiden)."""
        from src.db.repository import OfferRepository  # noqa: PLC0415
        items = OfferRepository(db_path).get_wishlist_items()
        return cls(items=items)

    @property
    def active_items(self) -> list[WishlistItem]:
        return [item for item in self.items if item.active]
