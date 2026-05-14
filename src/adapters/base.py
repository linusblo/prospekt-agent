from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.offer import Offer


class SupermarketAdapter(ABC):
    """Abstrakte Basisklasse für alle Supermarkt-Adapter.

    Jeder neue Supermarkt implementiert diese drei Methoden.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identifikationsname des Supermarkts (entspricht Supermarket-Enum-Wert)."""
        ...

    @abstractmethod
    def fetch_offers(self) -> list[Offer]:
        """Hauptmethode: HTML laden → parsen → Offer-Liste zurückgeben."""
        ...

    @abstractmethod
    def _fetch_html(self) -> str:
        """HTML der Angebotsseite herunterladen."""
        ...

    @abstractmethod
    def _parse_offers(self, html: str) -> list[Offer]:
        """JSON aus HTML extrahieren und in Offer-Objekte mappen."""
        ...
