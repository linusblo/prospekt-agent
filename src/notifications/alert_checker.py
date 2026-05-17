"""
Prüft MatchedProducts gegen Alarm-Regeln und versendet E-Mails.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.db.repository import OfferRepository
    from src.matching.matcher import MatchedProduct
    from src.notifications.email_sender import EmailSender

log = logging.getLogger(__name__)


def check_and_send_alerts(
    matched_products: list[MatchedProduct],
    repository: OfferRepository,
    email_sender: EmailSender,
    default_recipients: list[str],
) -> int:
    """
    Prüft alle MatchedProducts gegen Alarm-Regeln.
    Sendet E-Mails wo nötig, verhindert Duplikate via alerts_sent.
    Gibt Anzahl gesendeter Alerts zurück.
    """
    sent_count = 0

    for mp in matched_products:
        item  = mp.wishlist_item
        offer = mp.primary_offer

        if not item.alert_enabled:
            continue

        recipients = item.alert_recipients or default_recipients
        if not recipients:
            log.debug("Alert für '%s': keine Empfänger → übersprungen", item.name)
            continue

        # --- Preis-Schwellen prüfen (OR-Logik) ---
        triggered: dict[str, str] = {}  # alert_type → beschreibender Text

        if item.alert_max_base_price is not None:
            bp = offer.get("base_price_value")
            if bp is not None and bp < item.alert_max_base_price:
                triggered["base_price"] = (
                    f"Basispreis {bp:.2f} €/{offer.get('base_price_unit','?')} "
                    f"< Schwelle {item.alert_max_base_price:.2f} €"
                )

        if item.alert_max_total_price is not None:
            price = offer.get("sale_price") or 0.0
            if price < item.alert_max_total_price:
                triggered["total_price"] = (
                    f"Gesamtpreis {price:.2f} € < Schwelle {item.alert_max_total_price:.2f} €"
                )

        if not triggered:
            continue

        # --- Ampel-Filter ---
        if item.alert_only_green:
            if not mp.price_rating or mp.price_rating.level != "green":
                log.debug(
                    "Alert für '%s': alert_only_green, aber Level = %s → übersprungen",
                    item.name, mp.price_rating.level if mp.price_rating else "None",
                )
                continue

        # --- Duplikat-Schutz: pro alert_type prüfen und senden ---
        source     = offer.get("source") or ""
        slug       = offer.get("product_slug") or ""
        valid_from = offer.get("valid_from") or None

        for alert_type, reason in triggered.items():
            if repository.has_alert_been_sent(item.name, source, slug, alert_type, valid_from):
                log.debug(
                    "Alert für '%s' (%s) bereits gesendet → übersprungen",
                    item.name, alert_type,
                )
                continue

            subject = f"🔔 Prospekt-Alarm: {item.name} unter deiner Schwelle!"
            body    = _build_email_body(item, offer, mp, alert_type, reason)

            success = email_sender.send_alert(recipients, subject, body)
            if success:
                repository.save_alert_sent(
                    item.name, source, slug, alert_type, valid_from, recipients
                )
                sent_count += 1

    return sent_count


# ---------------------------------------------------------------------------
# E-Mail-Body
# ---------------------------------------------------------------------------

def _build_email_body(
    item:       MatchedProduct.wishlist_item,  # type: ignore[type-arg]
    offer:      dict,
    mp:         MatchedProduct,
    alert_type: str,
    reason:     str,
) -> str:
    from src.config.markets import get_display_name
    from src.utils.formatting import format_german_date

    market      = get_display_name(offer.get("source") or "")
    price       = offer.get("sale_price") or 0.0
    orig        = offer.get("original_price")
    bp          = offer.get("base_price_value")
    bp_unit     = offer.get("base_price_unit") or ""
    valid_from  = format_german_date(offer.get("valid_from"))
    valid_until = format_german_date(offer.get("valid_until"))
    rating_lbl  = mp.price_rating.label if mp.price_rating else "–"

    orig_html = f" <s style='color:#aaa'>{orig:.2f} €</s>" if orig else ""
    bp_str    = f"{bp:.2f} €/{bp_unit}" if bp else "–"

    if alert_type == "base_price" and item.alert_max_base_price:
        threshold_str = f"{item.alert_max_base_price:.2f} €/{bp_unit}"
        threshold_lbl = "Max. Basispreis"
    else:
        threshold_str = f"{item.alert_max_total_price:.2f} €" if item.alert_max_total_price else "–"
        threshold_lbl = "Max. Gesamtpreis"

    # Varianten
    variants_html = ""
    if mp.variant_names and len(mp.variant_names) > 1:
        v_list = " · ".join(mp.variant_names)
        variants_html = f"<tr><td style='{_TD}' colspan='2'><em>{v_list}</em></td></tr>"

    # Alternative Märkte
    alts_html = ""
    if mp.alternative_offers:
        rows = "".join(
            f"<li>{get_display_name(a.get('source',''))} — "
            f"<strong>{a.get('sale_price',0):.2f} €</strong></li>"
            for a in mp.alternative_offers
        )
        alts_html = f"<p><strong>Auch verfügbar bei:</strong><ul>{rows}</ul></p>"

    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333">
  <h2 style="color:#007bff">🔔 Prospekt-Alarm: {item.name}</h2>
  <p>Folgendes Angebot unterschreitet deinen Wunschpreis:</p>
  <table style="border-collapse:collapse;width:100%;margin:16px 0">
    <tr><td style="{_TD}"><strong>Produkt</strong></td>
        <td style="{_TD}">{offer.get("name","")}</td></tr>
    {variants_html}
    <tr><td style="{_TD}"><strong>Marke</strong></td>
        <td style="{_TD}">{offer.get("brand","")}</td></tr>
    <tr><td style="{_TD}"><strong>Markt</strong></td>
        <td style="{_TD}">{market}</td></tr>
    <tr><td style="{_TD}"><strong>Preis</strong></td>
        <td style="{_TD}"><strong style="color:#28a745">{price:.2f} €</strong>{orig_html}</td></tr>
    <tr><td style="{_TD}"><strong>Basispreis</strong></td>
        <td style="{_TD}">{bp_str}</td></tr>
    <tr style="background:#fff3cd"><td style="{_TD}"><strong>{threshold_lbl}</strong></td>
        <td style="{_TD};color:#856404">{threshold_str}</td></tr>
    <tr><td style="{_TD}"><strong>🚦 Bewertung</strong></td>
        <td style="{_TD}">{rating_lbl}</td></tr>
    <tr><td style="{_TD}"><strong>Gültig</strong></td>
        <td style="{_TD}">{valid_from} – {valid_until}</td></tr>
  </table>
  {alts_html}
  <p>
    <a href="http://localhost:8501"
       style="background:#007bff;color:white;padding:10px 20px;
              text-decoration:none;border-radius:4px;display:inline-block">
      Im Dashboard ansehen →
    </a>
  </p>
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="color:#999;font-size:11px">
    Diese Mail wurde automatisch vom Prospekt-Agent gesendet.<br>
    Alarm-Einstellungen: Dashboard → 📋 Wishlist → Eintrag bearbeiten.
  </p>
</body>
</html>"""


_TD = "padding:8px;border-bottom:1px solid #eee;vertical-align:top"
