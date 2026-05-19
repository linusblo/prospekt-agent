from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, model_validator


class Supermarket(str, Enum):
    ALDI_NORD = "aldi_nord"
    KAUFLAND  = "kaufland"
    TRINKGUT  = "trinkgut"
    LIDL      = "lidl"
    REWE      = "rewe"
    EDEKA     = "edeka"
    COMBI     = "combi"
    PENNY     = "penny"
    NETTO     = "netto"


class ParsedSalesUnit(BaseModel):
    quantity: float | None = None    # 1.25
    unit: str | None = None          # "L", "ml", "kg", "g"
    packaging: str | None = None     # "Flasche", "Dose", "Glas", "Beutel"
    multiplier: int = 1              # 6 bei "6x1,5-L-Flasche"
    raw: str                         # Originaltext wird immer erhalten


class Offer(BaseModel):
    # Herkunft
    source: Supermarket
    product_slug: str               # Eindeutiger Key pro Supermarkt

    # Produktinfo
    name: str
    brand: str | None = None
    short_description: str | None = None
    long_description: str | None = None

    # Preis
    sale_price: float
    original_price: float | None = None     # strikePrice
    discount_percent: float | None = None   # berechnet aus orig/sale

    # Basispreis
    base_price_value: float | None = None       # 0.79 (unterer Wert / Einzelwert)
    base_price_value_max: float | None = None   # 11.10 wenn Range, sonst None
    base_price_unit: str | None = None          # "kg", "L", "g", …
    base_price_has_prefix: bool = False         # True wenn "ab" im Originalstring

    # Verpackung
    sales_unit_raw: str | None = None
    sales_unit: ParsedSalesUnit | None = None

    # Pfand
    is_deposit_product: bool = False
    deposit_value: float | None = None

    # Gültigkeitszeitraum (Unix-Timestamps werden beim Mapping konvertiert)
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    # Loyalty-/Card-Preis (z.B. Kaufland-Card)
    card_price: float | None = None
    card_base_price_value: float | None = None
    card_base_price_value_max: float | None = None
    card_base_price_unit: str | None = None
    card_discount_percent: float | None = None

    # Metadaten
    image_url: str | None = None
    category_ids: list[str] = []
    scraped_at: datetime

    @model_validator(mode="after")
    def compute_discount(self) -> Offer:
        if (
            self.discount_percent is None
            and self.original_price is not None
            and self.original_price > self.sale_price
        ):
            self.discount_percent = round(
                (self.original_price - self.sale_price) / self.original_price * 100, 1
            )
        return self
