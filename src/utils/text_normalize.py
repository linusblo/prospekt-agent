from __future__ import annotations

import re


def normalize_for_matching(text: str) -> str:
    """
    Normalisiert Text für das Keyword-Matching.

    Ersetzt Sonderzeichen durch Leerzeichen, damit Wortgrenzen (\b)
    konsistent funktionieren — unabhängig davon ob das Produkt
    "COCA-COLA", "Coca Cola" oder "Coca-Cola, Fanta" heißt.

    Beispiele:
      "COCA-COLA"                   → "coca cola"
      "COCA-COLA, FANTA, SPRITE"    → "coca cola fanta sprite"
      "Buttermilch"                 → "buttermilch"   (unverändert)
      "Dr. Oetker"                  → "dr oetker"
      "Light/Zero"                  → "light zero"
    """
    text = text.lower()
    text = re.sub(r"[-,/.]", " ", text)      # Sonderzeichen → Leerzeichen
    text = re.sub(r"\s+", " ", text)         # Mehrfach-Leerzeichen zusammenführen
    return text.strip()
