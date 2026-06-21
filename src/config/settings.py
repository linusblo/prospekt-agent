from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


class Settings:
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587

    def __init__(self) -> None:
        self.SMTP_EMAIL    = os.getenv("SMTP_EMAIL", "")
        self.SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
        self.email_configured = bool(self.SMTP_EMAIL and self.SMTP_PASSWORD)
        self.DEFAULT_ALERT_RECIPIENTS: list[str] = (
            [self.SMTP_EMAIL] if self.SMTP_EMAIL else []
        )
        if not self.email_configured:
            log.warning(
                "SMTP_EMAIL oder SMTP_PASSWORD fehlt in .env — "
                "E-Mail-Alarm deaktiviert. Konfiguriere beide Werte für Benachrichtigungen."
            )
        # Edeka: Filial-ID (leer → Edeka-Adapter wird nicht geladen)
        self.EDEKA_MARKET_ID: str = os.getenv("EDEKA_MARKET_ID", "071115")
        # Combi: Bonial Store-/Publisher-ID (leer → Combi-Adapter wird nicht geladen)
        self.COMBI_STORE_ID: str = os.getenv("COMBI_STORE_ID", "DE-1031632951")
        self.COMBI_PUBLISHER_ID: str = os.getenv("COMBI_PUBLISHER_ID", "DE-42265682")
        if not self.COMBI_STORE_ID:
            log.warning(
                "COMBI_STORE_ID fehlt in .env — Combi-Adapter deaktiviert. "
                "Setze COMBI_STORE_ID=<Bonial-StoreID> um Combi-Angebote zu laden."
            )
        if not self.EDEKA_MARKET_ID:
            log.warning(
                "EDEKA_MARKET_ID fehlt in .env — Edeka-Adapter deaktiviert. "
                "Setze EDEKA_MARKET_ID=<FilialID> um Edeka-Angebote zu laden."
            )


# Modulweite Singleton-Instanz
settings = Settings()
