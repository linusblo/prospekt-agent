from __future__ import annotations

import re

from .offer import ParsedSalesUnit

# Kanonische Einheiten-Normalisierung
UNIT_MAP: dict[str, str] = {
    "l": "L", "liter": "L", "ltr": "L",
    "ml": "ml",
    "cl": "cl",
    "kg": "kg", "kilo": "kg", "kilogramm": "kg",
    "g": "g", "gr": "g", "gramm": "g",
    "stk": "Stk", "stück": "Stk", "st": "Stk",
}

PACKAGING_KEYWORDS: set[str] = {
    "flasche", "dose", "glas", "beutel", "pack", "packung",
    "becher", "tüte", "karton", "kasten", "tube", "tiegel",
    "rolle", "blatt", "scheiben", "riegel",
}

# Beispiele: "1,25-L-Flasche", "6x1,5-L-Flasche", "500-ml-Dose", "2-kg-Beutel"
_PATTERN = re.compile(
    r"(?:(\d+)\s*[xX×]\s*)?"           # Gruppe 1: optionaler Multiplikator (6x)
    r"(\d+(?:[.,]\d+)?)"               # Gruppe 2: Menge (1,25 oder 500)
    r"[-–\s]*"                          # Trennzeichen
    r"([A-Za-zäöüÄÖÜ.]+)"              # Gruppe 3: Einheit (L, ml, kg, Liter)
    r"(?:[-–\s]+([A-Za-zäöüÄÖÜ]+))?",  # Gruppe 4: Verpackung (Flasche, Dose)
    re.IGNORECASE,
)


class SalesUnitParser:
    def parse(self, raw: str) -> ParsedSalesUnit:
        if not raw:
            return ParsedSalesUnit(raw=raw)

        match = _PATTERN.search(raw)
        if not match:
            return ParsedSalesUnit(raw=raw)

        multiplier_str, qty_str, unit_str, pkg_str = match.groups()

        multiplier = int(multiplier_str) if multiplier_str else 1
        quantity = self._normalize_quantity(qty_str)
        unit = self._resolve_unit(unit_str)
        packaging: str | None = None

        if unit is None:
            # unit_str wurde nicht erkannt → vielleicht ist es die Verpackung
            packaging = self._resolve_packaging(unit_str)
            if pkg_str:
                unit = self._resolve_unit(pkg_str)
        elif pkg_str:
            packaging = self._resolve_packaging(pkg_str)

        return ParsedSalesUnit(
            quantity=quantity,
            unit=unit,
            packaging=packaging,
            multiplier=multiplier,
            raw=raw,
        )

    def _normalize_quantity(self, raw_number: str) -> float | None:
        try:
            return float(raw_number.replace(",", "."))
        except (ValueError, AttributeError):
            return None

    def _resolve_unit(self, raw_unit: str) -> str | None:
        return UNIT_MAP.get(raw_unit.lower().rstrip("."))

    def _resolve_packaging(self, raw_token: str) -> str | None:
        token = raw_token.lower()
        for keyword in PACKAGING_KEYWORDS:
            if keyword in token:
                return raw_token.capitalize()
        return None
