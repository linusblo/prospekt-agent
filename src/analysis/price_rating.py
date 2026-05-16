from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.db.repository import OfferRepository

log = logging.getLogger(__name__)

# Reihenfolge: besser → schlechter
_LEVEL_ORDER: list[str] = ["green", "yellow", "red"]

_NO_DATA_THRESHOLD = 3      # < 3 Einträge → no_data
_FULL_RATING_THRESHOLD = 10  # >= 10 Einträge → volle Bewertung (keine "Tendenz:")

RATING_EMOJI: dict[str, str] = {
    "green":   "🟢",
    "yellow":  "🟡",
    "red":     "🔴",
    "no_data": "⚪",
}


@dataclass
class PriceRating:
    level: str             # "green" | "yellow" | "red" | "no_data"
    label: str             # "Sehr gut" | "Mittelmäßig" | "Schwach" | "Zu wenig Daten"
    explanation: str       # menschlich lesbarer Text
    historic_count: int    # Anzahl historische Datenpunkte
    min_price: float | None = None
    max_price: float | None = None
    median_price: float | None = None


def rate_offer(
    source: str,
    brand: str,
    name: str,
    sales_unit_raw: str | None,
    current_price: float,
    current_base_price: float | None,
    repository: OfferRepository,
    days: int = 90,
) -> PriceRating:
    """
    Bewertet ein Angebot anhand historischer Preise aus price_history.

    Logik:
    - < 3 Datenpunkte → "no_data"
    - 3–9 Datenpunkte → "Tendenz: ..." (vorsichtige Bewertung)
    - >= 10 Datenpunkte → Vollbewertung über P20/P60
    - Wenn base_price vorliegt: beide Metriken bewerten, besser gewinnt
    """
    history = repository.get_price_history_for_product(
        source=source,
        brand_lower=brand.lower(),
        name_lower=name.lower(),
        sales_unit_raw=sales_unit_raw or "",
        days=days,
    )

    n = len(history)

    if n < _NO_DATA_THRESHOLD:
        return PriceRating(
            level="no_data",
            label="Zu wenig Daten",
            explanation=f"Zu wenig Daten (nur {n} historische Einträge)",
            historic_count=n,
        )

    prices = sorted(
        h["sale_price"] for h in history if h.get("sale_price") is not None
    )
    if not prices:
        return PriceRating(
            level="no_data",
            label="Zu wenig Daten",
            explanation="Keine Preiswerte verfügbar",
            historic_count=n,
        )

    min_price    = prices[0]
    max_price    = prices[-1]
    median_price = statistics.median(prices)
    is_tendenz   = n < _FULL_RATING_THRESHOLD
    prefix       = "Tendenz: " if is_tendenz else ""

    level, label, explanation = _classify(
        current_price, prices, min_price, median_price, prefix, days
    )

    # Base-Price-Vergleich: wenn Basispreis vorliegt → strengere Wertung aus beiden nehmen
    if current_base_price is not None:
        base_prices = sorted(
            h["base_price_value"] for h in history
            if h.get("base_price_value") is not None
        )
        if len(base_prices) >= _NO_DATA_THRESHOLD:
            bp_level, _, _ = _classify(
                current_base_price, base_prices,
                base_prices[0], statistics.median(base_prices),
                prefix, days,
            )
            # Bessere Bewertung gewinnt (niedrigerer Index = besser)
            if _LEVEL_ORDER.index(bp_level) < _LEVEL_ORDER.index(level):
                level = bp_level
                if bp_level == "green":
                    label = f"{prefix}Sehr gut (Basispreis)"
                    explanation = (
                        f"Günstigster Basispreis der letzten {days} Tage "
                        f"(Median Gesamtpreis: {median_price:.2f} €)"
                    )
                elif bp_level == "yellow":
                    label = f"{prefix}Mittelmäßig (Basispreis)"

    return PriceRating(
        level=level,
        label=label,
        explanation=explanation,
        historic_count=n,
        min_price=min_price,
        max_price=max_price,
        median_price=median_price,
    )


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _classify(
    current: float,
    prices: list[float],
    min_p: float,
    median_p: float,
    prefix: str,
    days: int,
) -> tuple[str, str, str]:
    """Klassifiziert current anhand von P20/P60 der Preisliste."""
    n = len(prices)
    # statistics.quantiles(data, n=5) → [P20, P40, P60, P80]
    if n >= 2:
        quants = statistics.quantiles(prices, n=5)
        # Auf 4 Dezimalstellen runden → eliminiert IEEE-754-Artefakte
        p20 = round(quants[0], 4)
        p60 = round(quants[2], 4)
    else:
        p20 = p60 = round(prices[0], 4)

    cur = round(current, 4)

    if cur <= p20:
        return (
            "green",
            f"{prefix}Sehr gut",
            f"Bester Preis der letzten {days} Tage (Median: {median_p:.2f} €)",
        )
    if current <= p60:
        return (
            "yellow",
            f"{prefix}Mittelmäßig",
            f"Etwas günstiger als sonst (Median: {median_p:.2f} €)",
        )
    return (
        "red",
        f"{prefix}Schwach",
        f"Schwacher Aktionspreis (Tiefstpreis: {min_p:.2f} €)",
    )
