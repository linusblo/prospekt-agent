from __future__ import annotations

import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Normalisierung auf kanonische Einheiten
_UNIT_NORM: dict[str, str] = {
    "l": "L", "liter": "L", "litre": "L",
    "ml": "ml", "cl": "cl",
    "kg": "kg", "kilo": "kg", "kilogramm": "kg",
    "g": "g", "gr": "g", "gramm": "g",
    "stk": "Stk", "st": "Stk", "stück": "Stk",
}

# Gruppe 1: Menge (z.B. "1", "100")
# Gruppe 2: Einheit (z.B. "kg", "l", "g", "ml")
# Gruppe 3: optionaler "ab"-Prefix
# Gruppe 4: erster Preiswert
# Gruppe 5: optionaler zweiter Preiswert (Range-Ende)
_PATTERN = re.compile(
    r"\(\s*"
    r"(\d+(?:[,.]\d+)?)\s*"          # Menge
    r"([a-zA-ZäöüÄÖÜ]+)\s*"          # Einheit
    r"=\s*"
    r"(ab\s*)?"                       # optionales "ab"
    r"(?:€\s*)?"                      # optionales "€" Präfix
    r"(\d+[,.]\d+|\d+)"              # erster Preis
    r"(?:\s*[-–]\s*"                  # optionaler Bereich-Trenner
    r"(\d+[,.]\d+|\d+))?"            # zweiter Preis
    r"(?:\s*(?:€|\*))?",              # optionales "€" Suffix
    re.IGNORECASE,
)


@dataclass
class ParsedBasePrice:
    value: float | None = None          # unterer/einziger Preis
    max_value: float | None = None      # oberer Preis bei Range, sonst None
    unit: str | None = None             # normalisierte Einheit
    has_prefix: bool = False            # True wenn "ab" im Original


class KauflandBasePriceParser:
    def parse(self, raw: str | None) -> ParsedBasePrice:
        """
        Parst Strings wie:
          "(1 kg = 5.70)"           → value=5.70, max=None, unit='kg'
          "(1 kg = 5.70 - 11.10)"   → value=5.70, max=11.10, unit='kg'
          "(1 kg = ab € 5.08)"      → value=5.08, has_prefix=True, unit='kg'
          "(1 l = 2.50)"             → value=2.50, unit='L'
          "(100 g = 0.59)"           → value=0.59, unit='g'
          "(1 kg = ab 4.52 - 8.80)" → value=4.52, max=8.80, has_prefix=True
        """
        if not raw:
            return ParsedBasePrice()

        m = _PATTERN.search(raw)
        if not m:
            log.warning("KauflandBasePriceParser: kein Match für %r", raw)
            return ParsedBasePrice()

        _per_amount, unit_raw, ab_prefix, price1_str, price2_str = m.groups()

        try:
            price1 = _to_float(price1_str)
            price2 = _to_float(price2_str) if price2_str else None
        except (ValueError, AttributeError):
            log.warning("KauflandBasePriceParser: Preis nicht parsbar in %r", raw)
            return ParsedBasePrice()

        unit = _UNIT_NORM.get(unit_raw.lower(), unit_raw)
        has_prefix = ab_prefix is not None and "ab" in ab_prefix.lower()

        return ParsedBasePrice(
            value=price1,
            max_value=price2,
            unit=unit,
            has_prefix=has_prefix,
        )


def _to_float(s: str) -> float:
    return float(s.replace(",", "."))
