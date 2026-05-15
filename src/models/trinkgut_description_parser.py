from __future__ import annotations

import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Normalisierung auf kanonische Einheiten
_UNIT_NORM: dict[str, str] = {
    "l": "L", "liter": "L",
    "ml": "ml", "cl": "cl",
    "kg": "kg", "g": "g",
}

# Basispreis-Regex: "(1 l = € 2.27)" oder "(1 kg = 5.70)" oder "(1 l = 1.78)"
_BP_RE = re.compile(
    r"\(1\s*(l|kg|g|ml|cl)\s*=\s*€?\s*([\d,.]+)\)",
    re.IGNORECASE,
)

# "versch. Sorten, " Präfix (kommt häufig bei Trinkgut vor)
_VERSCH_RE = re.compile(r"^versch\.?\s*Sorten,?\s*", re.IGNORECASE)


@dataclass
class ParsedDescription:
    sales_unit_raw: str | None = None     # z.B. "20 x 0,5 l Kasten"
    base_price_value: float | None = None  # z.B. 2.27
    base_price_unit: str | None = None    # z.B. "L"


class TrinkgutDescriptionParser:
    """
    Parst den Freitext aus <p class="product-description"> bei Trinkgut.

    Eingabe-Formate:
      "versch. Sorten, Kasten = 20 x 0,5 l / 24 x 0,33 l (1 l = € 2.27) zzgl. 0.25 Pfand"
      "versch. Sorten, 0,5 l Dose (1 l = € 1.78) zzgl."
      "Pack = 6 x 0,33 l (1 l = € 2.02) zzgl."
    """

    def parse(self, description: str | None) -> ParsedDescription:
        if not description:
            return ParsedDescription()

        bp_value, bp_unit = self._extract_base_price(description)
        sales_unit_raw = self._extract_sales_unit(description)

        return ParsedDescription(
            sales_unit_raw=sales_unit_raw,
            base_price_value=bp_value,
            base_price_unit=bp_unit,
        )

    # ------------------------------------------------------------------

    def _extract_base_price(self, desc: str) -> tuple[float | None, str | None]:
        m = _BP_RE.search(desc)
        if not m:
            log.debug("TrinkgutDescriptionParser: kein Basispreis in %r", desc[:80])
            return None, None
        unit = _UNIT_NORM.get(m.group(1).lower(), m.group(1))
        try:
            value = float(m.group(2).replace(",", "."))
        except ValueError:
            log.warning("TrinkgutDescriptionParser: Preis nicht parsbar in %r", desc[:80])
            return None, None
        return value, unit

    def _extract_sales_unit(self, desc: str) -> str | None:
        # Teil vor der ersten "(" (Basispreis-Klammer)
        before_paren = desc.split("(")[0].strip()

        # "versch. Sorten, " Präfix entfernen
        before_paren = _VERSCH_RE.sub("", before_paren).strip()

        if not before_paren:
            return None

        # Erste Variante nehmen (vor "/")
        first_variant = before_paren.split("/")[0].strip()

        if not first_variant:
            return None

        # "Container = Volumen" umstellen → "Volumen Container"
        if "=" in first_variant:
            parts = first_variant.split("=", 1)
            container = parts[0].strip()
            volume    = parts[1].strip()
            result    = f"{volume} {container}".strip()
            return result or None

        return first_variant or None
