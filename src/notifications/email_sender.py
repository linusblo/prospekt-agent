from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import Settings

log = logging.getLogger(__name__)


class EmailSender:
    def __init__(self, settings: Settings) -> None:
        self._email    = settings.SMTP_EMAIL
        self._password = settings.SMTP_PASSWORD
        self._host     = settings.SMTP_HOST
        self._port     = settings.SMTP_PORT

    def send_alert(
        self,
        recipients: list[str],
        subject: str,
        body_html: str,
    ) -> bool:
        """
        Sendet eine HTML-E-Mail via STARTTLS.
        Gibt True bei Erfolg zurück, loggt Fehler und gibt False zurück.
        """
        if not recipients:
            log.warning("send_alert: keine Empfänger angegeben")
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = self._email
            msg["To"]      = ", ".join(recipients)

            # Plain-Text-Fallback (rudimentär, Strip von HTML-Tags)
            import re as _re
            plain = _re.sub(r"<[^>]+>", "", body_html).strip()
            msg.attach(MIMEText(plain,     "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html",  "utf-8"))

            with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(self._email, self._password)
                smtp.sendmail(self._email, recipients, msg.as_string())

            log.info("Alert-Mail gesendet an %s: %s", recipients, subject)
            return True

        except Exception:
            log.error(
                "Fehler beim Senden der Alert-Mail an %s: %s",
                recipients, subject, exc_info=True,
            )
            return False
