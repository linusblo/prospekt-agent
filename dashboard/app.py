"""Prospekt-Agent Streamlit Dashboard — Phase C2."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis.price_rating import RATING_EMOJI
from src.config.markets import get_display_name
from src.config.settings import settings
from src.db.repository import OfferRepository
from src.matching.matcher import Matcher
from src.matching.wishlist import Wishlist, WishlistItem
from src.utils.formatting import format_german_date

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

DB_PATH = os.getenv("DB_PATH", "data/offers.db")

_PACKAGING_OPTIONS = ["Dose", "Glas", "Flasche", "Packung", "Beutel", "Becher"]
_UNIT_OPTIONS      = ["", "L", "ml", "cl", "kg", "g", "Stk"]

st.set_page_config(page_title="Prospekt-Agent", page_icon="🛒", layout="wide")

# ---------------------------------------------------------------------------
# Cached Daten-Loader (TTL 60 s)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def _active_offers() -> list[dict]:
    return OfferRepository(DB_PATH).get_active_offers()


@st.cache_data(ttl=60)
def _all_offers() -> list[dict]:
    return OfferRepository(DB_PATH).get_all_offers()


@st.cache_data(ttl=60)
def _wishlist_rows() -> list[dict]:
    return OfferRepository(DB_PATH).get_wishlist_rows()


@st.cache_data(ttl=60)
def _distinct_brands() -> list[str]:
    return OfferRepository(DB_PATH).get_distinct_brands()


@st.cache_data(ttl=60)
def _distinct_categories() -> list[str]:
    return OfferRepository(DB_PATH).get_distinct_categories()


@st.cache_data(ttl=60)
def _load_matched_products() -> dict[str, list[dict]]:
    """
    Gibt gematchte Produkte inkl. Ampel-Bewertung als serialisierbare Dict-Struktur zurück.
    Format: item_name → [{primary, primary_count, alternatives, rating}, ...]
    """
    repo = OfferRepository(DB_PATH)
    wishlist = Wishlist.from_db(DB_PATH)
    if not wishlist.active_items:
        return {}
    offers = repo.get_active_offers()
    results_by_item = Matcher(wishlist, food_only=True, repository=repo).match_all(offers)
    out: dict[str, list[dict]] = {}
    for item_name, products in results_by_item.items():
        out[item_name] = [
            {
                "primary":        mp.primary_offer,
                "primary_count":  mp.primary_market_count,
                "alternatives":   mp.alternative_offers,
                "variant_names":  mp.variant_names,
                "rating": {
                    "level":        mp.price_rating.level,
                    "label":        mp.price_rating.label,
                    "explanation":  mp.price_rating.explanation,
                    "historic_count": mp.price_rating.historic_count,
                    "min_price":    mp.price_rating.min_price,
                    "max_price":    mp.price_rating.max_price,
                    "median_price": mp.price_rating.median_price,
                } if mp.price_rating else None,
            }
            for mp in products
        ]
    return out


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _fmt_base_price(o: dict, card: bool = False) -> str:
    """
    Formatiert Basispreis als lesbaren String:
      Single:   "5.70 €/kg"
      Range:    "5.70 - 11.10 €/kg"
      Ab-Preis: "ab 5.70 €/kg"
      Card:     wie oben, mit " *" Suffix
    """
    prefix = "card_" if card else ""
    v     = o.get(f"{prefix}base_price_value")
    v_max = o.get(f"{prefix}base_price_value_max")
    u     = o.get(f"{prefix}base_price_unit")

    if not v or not u:
        return ""

    has_ab = bool(o.get("base_price_has_prefix")) and not card
    price_part = f"{v:.2f}" if v_max is None else f"{v:.2f} - {v_max:.2f}"
    prefix_str = "ab " if has_ab else ""
    suffix_str = " *" if card else ""

    return f"{prefix_str}{price_part} €/{u}{suffix_str}"


def _offers_to_df(offers: list[dict]) -> pd.DataFrame:
    if not offers:
        return pd.DataFrame()
    rows = []
    for o in offers:
        cats_raw = o.get("category_ids") or "[]"
        cats: list[str] = json.loads(cats_raw) if isinstance(cats_raw, str) else (cats_raw or [])
        display_cats = [c for c in cats if c != "Angebote"] or cats
        rows.append({
            "Markt":      get_display_name(o.get("source") or ""),
            "Produkt":    o.get("name") or "",
            "Marke":      o.get("brand") or "",
            "Preis":      o.get("sale_price"),
            "UVP":        o.get("original_price"),
            "Rabatt":     o.get("discount_percent"),
            "Inhalt":     o.get("sales_unit_raw") or "",
            "Basispreis": _fmt_base_price(o),
            "Gültig bis": format_german_date(o.get("valid_until")),
            "Kategorie":  ", ".join(display_cats),
        })
    return pd.DataFrame(rows)


def _time_ago(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str).astimezone(timezone.utc)
        mins = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
        if mins < 1:   return "gerade eben"
        if mins < 60:  return f"vor {mins} Min."
        if mins < 1440: return f"vor {mins // 60} Std."
        return f"vor {mins // 1440} Tag(en)"
    except Exception:
        return dt_str[:16]


def _parse_tags(text: str) -> list[str]:
    return [t.strip() for t in text.split(",") if t.strip()]


def _join_tags(tags: list[str]) -> str:
    return ", ".join(tags)


_PRICE_COLS = {
    "Preis":  st.column_config.NumberColumn("Preis €",  format="%.2f €"),
    "UVP":    st.column_config.NumberColumn("UVP €",    format="%.2f €"),
    "Rabatt": st.column_config.NumberColumn("Rabatt %", format="%.1f %%"),
}

_COL_WIDTHS = [1, 3, 2, 1.1, 1, 1.5, 1.2, 1.8]


def _parse_iso_to_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, AttributeError):
        return None


def _starts_in_text(vf_str: str | None) -> str:
    dt = _parse_iso_to_dt(vf_str)
    if dt is None:
        return "—"
    days = (dt.date() - datetime.now(timezone.utc).date()).days
    if days <= 0:
        return "heute"
    if days == 1:
        return "morgen"
    if days == 2:
        return "übermorgen"
    if days <= 13:
        return f"in {days} Tagen"
    return f"ab {dt.strftime('%d.%m.')}"


def _render_offer_group(item_name: str, products: list[dict], upcoming: bool = False) -> None:
    """Rendert eine Wishlist-Gruppe (Header + Zeilen + Expander)."""
    date_label = "Startet in" if upcoming else "Gültig bis"
    n = len(products)

    st.markdown(f"**{item_name}** — {n} Treffer")

    h = st.columns(_COL_WIDTHS)
    for col, lbl in zip(h, ["Bild", "Produkt", "Preis", "🚦", "Rabatt", "Inhalt/Basis", date_label, "Märkte"]):
        col.markdown(f"**{lbl}**")

    for prod in products:
        o             = prod["primary"]
        alts          = prod["alternatives"]
        p_count       = prod["primary_count"]
        rating        = prod.get("rating")
        variant_names = prod.get("variant_names") or []
        n_variants    = len(variant_names)

        if rating:
            r_emoji = RATING_EMOJI.get(rating["level"], "⚪")
            r_label = rating["label"].replace("Tendenz: ", "")
            r_expl  = rating["explanation"]
            n_pts   = rating.get("historic_count", 0)
            r_help  = f"{r_expl}  ({n_pts} Datenpunkte)"
        else:
            r_emoji, r_label, r_help = "⚪", "Zu wenig Daten", "Noch kein historischer Preis."

        market_label = get_display_name(o.get("source") or "")
        if alts:
            market_label += f" **+{len(alts)}**"
        if p_count > 1:
            market_label += f" *(×{p_count})*"

        price    = o.get("sale_price") or 0.0
        orig     = o.get("original_price")
        disc     = o.get("discount_percent")
        price_md = f"**{price:.2f} €**"
        if orig:
            price_md += f"  \n~~{orig:.2f} €~~"
        card_p = o.get("card_price")
        if card_p:
            price_md += f"  \n🃏 {card_p:.2f} €*"

        unit_raw = o.get("sales_unit_raw") or ""
        bp_str   = _fmt_base_price(o)
        content  = unit_raw + (f"  \n{bp_str}" if bp_str else "")

        # Datumsspalte: "Startet in" oder "Gültig bis"
        if upcoming:
            date_val = _starts_in_text(o.get("valid_from"))
        else:
            date_val = format_german_date(o.get("valid_until"))

        cols = st.columns(_COL_WIDTHS)
        img_url = o.get("image_url")
        if img_url:
            cols[0].image(img_url, width=55)
        else:
            cols[0].write("")
        if n_variants > 1:
            prod_md = f"**{n_variants} Sorten verfügbar**"
        else:
            prod_md = f"**{o.get('name', '')}**"
        if o.get("brand"):
            prod_md += f"  \n{o['brand']}"
        if n_variants > 1:
            prod_md += f"  \n*{' · '.join(variant_names)}*"
        cols[1].markdown(prod_md)
        cols[2].markdown(price_md)
        cols[3].metric(label=r_label, value=r_emoji, help=r_help)
        cols[4].write(f"-{disc:.0f}%" if disc else "–")
        cols[5].markdown(content or "–")
        cols[6].write(date_val)
        cols[7].markdown(market_label)

        if alts:
            with st.expander(f"Auch verfügbar bei {len(alts)} weiteren Märkten"):
                alt_rows = []
                for alt in alts:
                    alt_bp   = _fmt_base_price(alt)
                    alt_card = alt.get("card_price")
                    preis_str = f"{alt.get('sale_price', 0):.2f} €"
                    if alt_card:
                        preis_str += f" (🃏 {alt_card:.2f} €*)"
                    alt_rows.append({
                        "Markt":      get_display_name(alt.get("source") or ""),
                        "Preis":      preis_str,
                        "Basispreis": alt_bp or "–",
                        "Gültig bis": format_german_date(alt.get("valid_until")),
                    })
                st.dataframe(pd.DataFrame(alt_rows), hide_index=True, use_container_width=True)

    st.divider()


# ---------------------------------------------------------------------------
# Dialog: Löschen bestätigen
# ---------------------------------------------------------------------------

@st.dialog("Eintrag löschen")
def _confirm_delete(item_id: int, item_name: str) -> None:
    st.warning(f'**"{item_name}"** wird dauerhaft gelöscht.')
    col1, col2 = st.columns(2)
    if col1.button("🗑️ Ja, löschen", type="primary", use_container_width=True):
        OfferRepository(DB_PATH).delete_wishlist_item(item_id)
        st.cache_data.clear()
        st.rerun()
    if col2.button("Abbrechen", use_container_width=True):
        st.rerun()


# ---------------------------------------------------------------------------
# Dialog: Eintrag hinzufügen / bearbeiten
# ---------------------------------------------------------------------------

@st.dialog("Wishlist-Eintrag")
def _wishlist_form(edit_id: int | None = None) -> None:
    repo      = OfferRepository(DB_PATH)
    existing  = repo.get_wishlist_item_by_id(edit_id) if edit_id is not None else None
    ex        = existing  # shorthand

    all_brands  = _distinct_brands()
    all_cats    = _distinct_categories()

    # Brands aus bestehenden Item einschließen (falls inzwischen nicht mehr in DB)
    if ex:
        all_brands = sorted(set(all_brands) | set(ex.allowed_brands))

    st.subheader("Bearbeiten" if edit_id else "Neuer Eintrag")

    # ── Standard-Felder ──────────────────────────────────────────────────
    name = st.text_input(
        "Name *",
        value=ex.name if ex else "",
        placeholder="z.B. Coca-Cola",
    )
    allowed_brands = st.multiselect(
        "Marken (allowed_brands)",
        options=all_brands,
        default=ex.allowed_brands if ex else [],
        help="Leer = alle Marken erlaubt",
    )
    keywords = st.text_input(
        "Keywords (kommagetrennt)",
        value=_join_tags(ex.keywords) if ex else "",
        placeholder="cola, coca",
    )
    exclude_keywords = st.text_input(
        "Exclude-Keywords (kommagetrennt)",
        value=_join_tags(ex.exclude_keywords) if ex else "",
        placeholder="buttermilch, light",
    )
    max_price = st.number_input(
        "Max. Preis € (0 = kein Limit)",
        min_value=0.0, step=0.10, format="%.2f",
        value=float(ex.max_price) if ex and ex.max_price else 0.0,
    )
    active = st.toggle("Aktiv", value=ex.active if ex else True)

    # ── Erweiterte Felder ─────────────────────────────────────────────────
    with st.expander("Erweiterte Felder"):
        brand = st.text_input(
            "Einzel-Marke (brand) — nur wenn allowed_brands nicht ausreicht",
            value=ex.brand or "" if ex else "",
        )
        excluded_packaging = st.multiselect(
            "Verpackung ausschließen",
            options=_PACKAGING_OPTIONS,
            default=ex.excluded_packaging if ex else [],
        )
        unit_idx = _UNIT_OPTIONS.index(ex.unit_filter or "") if ex and ex.unit_filter in _UNIT_OPTIONS else 0
        unit_filter = st.selectbox("Einheit", _UNIT_OPTIONS, index=unit_idx)
        min_quantity = st.number_input(
            "Min. Menge (0 = kein Limit)",
            min_value=0.0, step=0.1, format="%.3g",
            value=float(ex.min_quantity) if ex and ex.min_quantity else 0.0,
        )
        min_discount = st.number_input(
            "Min. Rabatt % (0 = kein Limit)",
            min_value=0.0, max_value=100.0, step=1.0,
            value=float(ex.min_discount_percent) if ex and ex.min_discount_percent else 0.0,
        )
        categories = st.multiselect(
            "Kategorien",
            options=all_cats,
            default=[c for c in (ex.categories if ex else []) if c in all_cats],
        )
        from src.config.markets import MARKET_DISPLAY_NAMES
        mkt_options = list(MARKET_DISPLAY_NAMES.keys())
        supermarkets = st.multiselect(
            "Supermärkte (leer = alle)",
            options=mkt_options,
            default=ex.supermarkets if ex else [],
            format_func=get_display_name,
        )
        notes = st.text_area(
            "Notizen",
            value=ex.notes or "" if ex else "",
        )

    # ── Alarm-Einstellungen ──────────────────────────────────────────────
    with st.expander("🔔 Alarm-Einstellungen"):
        alert_enabled = st.toggle(
            "Alarm aktivieren",
            value=ex.alert_enabled if ex else False,
        )
        alert_max_base_price = st.number_input(
            "Max. Basispreis (€/Einheit, 0 = kein Limit)",
            min_value=0.0, step=0.01, format="%.2f",
            value=float(ex.alert_max_base_price) if ex and ex.alert_max_base_price else 0.0,
            help="Du wirst benachrichtigt, wenn der Liter-/Kilopreis unter diesen Wert fällt.",
        )
        alert_max_total_price = st.number_input(
            "Max. Gesamtpreis (€, 0 = kein Limit)",
            min_value=0.0, step=0.01, format="%.2f",
            value=float(ex.alert_max_total_price) if ex and ex.alert_max_total_price else 0.0,
            help="Du wirst benachrichtigt, wenn der Artikelpreis unter diesen Wert fällt.",
        )
        alert_recipients_raw = st.text_input(
            "E-Mail-Empfänger (kommagetrennt)",
            value=_join_tags(ex.alert_recipients) if ex else "",
            help="Leer = Standard-Adresse aus .env (SMTP_EMAIL).",
        )
        alert_only_green = st.toggle(
            "Nur bei 🟢 grüner Ampel alarmieren",
            value=ex.alert_only_green if ex else False,
        )

    st.divider()
    col_save, col_cancel = st.columns(2)
    save_clicked   = col_save.button("💾 Speichern", type="primary", use_container_width=True)
    cancel_clicked = col_cancel.button("✕ Abbrechen", use_container_width=True)

    if cancel_clicked:
        st.rerun()

    if save_clicked:
        # ── Validierung ──
        errors: list[str] = []
        if not name.strip():
            errors.append("Name darf nicht leer sein.")
        if max_price < 0:
            errors.append("Max. Preis muss ≥ 0 sein.")
        if min_quantity < 0:
            errors.append("Min. Menge muss ≥ 0 sein.")

        if errors:
            for e in errors:
                st.error(e)
            return  # Dialog bleibt offen

        # ── WishlistItem zusammenbauen ──
        item = WishlistItem(
            name             = name.strip(),
            brand            = brand.strip() or None,
            allowed_brands   = allowed_brands,
            keywords         = _parse_tags(keywords),
            exclude_keywords = _parse_tags(exclude_keywords),
            excluded_packaging = excluded_packaging,
            categories       = categories,
            max_price        = max_price if max_price > 0 else None,
            min_discount_percent = min_discount if min_discount > 0 else None,
            unit_filter      = unit_filter or None,
            min_quantity     = min_quantity if min_quantity > 0 else None,
            supermarkets     = supermarkets,
            active           = active,
            notes            = notes.strip() or None,
            alert_enabled         = alert_enabled,
            alert_max_base_price  = alert_max_base_price  if alert_max_base_price  > 0 else None,
            alert_max_total_price = alert_max_total_price if alert_max_total_price > 0 else None,
            alert_recipients      = _parse_tags(alert_recipients_raw),
            alert_only_green      = alert_only_green,
        )

        # ── Speichern ──
        try:
            if edit_id is None:
                OfferRepository(DB_PATH).add_wishlist_item(item)
                st.toast(f"✅ '{item.name}' hinzugefügt.")
            else:
                OfferRepository(DB_PATH).update_wishlist_item(edit_id, item)
                st.toast(f"✅ '{item.name}' aktualisiert.")
            st.cache_data.clear()
            st.rerun()
        except sqlite3.IntegrityError:
            st.error(f"Ein Eintrag mit dem Namen **'{item.name}'** existiert bereits.")


# ---------------------------------------------------------------------------
# Seitenheader
# ---------------------------------------------------------------------------

st.title("🛒 Prospekt-Agent")
st.caption(datetime.now().strftime("Stand: %A, %d. %B %Y"))

if not Path(DB_PATH).exists():
    st.error(
        f"Datenbank nicht gefunden: `{DB_PATH}`  \n"
        "Bitte zuerst `python scripts/run_agent.py` ausführen."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_hits, tab_wish, tab_all, tab_hist, tab_status = st.tabs(
    ["🎯 Treffer", "📋 Wishlist", "🛒 Alle Angebote", "📈 Preis-Historie", "ℹ️ Status"]
)

# ── Tab 1: Treffer ──────────────────────────────────────────────────────────
with tab_hits:
    col_title, col_btn = st.columns([5, 1])
    col_title.subheader("Aktuelle Wishlist-Treffer")

    # ── Teil 3: Aktualisieren-Button ──
    with col_btn:
        if st.button("🔄 Aktualisieren", use_container_width=True):
            from src.adapters.aldi_nord import AldiNordAdapter
            from src.adapters.kaufland import KauflandAdapter
            from src.adapters.trinkgut import TrinkgutAdapter
            adapters = [AldiNordAdapter(), KauflandAdapter(), TrinkgutAdapter()]
            repo_ref = OfferRepository(DB_PATH)

            # Abgelaufene zuerst bereinigen
            cleaned = repo_ref.cleanup_expired_offers()
            if cleaned:
                st.info(f"🧹 {cleaned} abgelaufene Angebote bereinigt.")

            total = 0
            errors: list[str] = []
            for adp in adapters:
                with st.spinner(f"Lade {get_display_name(adp.source_name)}…"):
                    try:
                        offers = adp.fetch_offers()
                        if offers:
                            total += repo_ref.upsert_many(offers)
                            repo_ref.save_price_history_batch(offers)
                    except Exception as exc:
                        errors.append(f"{get_display_name(adp.source_name)}: {exc}")
            st.cache_data.clear()
            if errors:
                for e in errors:
                    st.error(f"Fehler: {e}")
            if total:
                st.success(f"✅ {total} Angebote aktualisiert.")

            # ── Alert-Prüfung nach Aktualisierung ──
            if settings.email_configured:
                with st.spinner("Prüfe Alarm-Schwellen…"):
                    from src.notifications.email_sender import EmailSender
                    from src.notifications.alert_checker import check_and_send_alerts
                    _repo   = OfferRepository(DB_PATH)
                    _wl     = Wishlist.from_db(DB_PATH)
                    _offers = _repo.get_active_offers()
                    _m      = Matcher(_wl, food_only=True, repository=_repo)
                    _prods  = [mp for ps in _m.match_all(_offers).values() for mp in ps]
                    _sent   = check_and_send_alerts(
                        _prods, _repo, EmailSender(settings),
                        settings.DEFAULT_ALERT_RECIPIENTS,
                    )
                    if _sent:
                        st.info(f"🔔 {_sent} Alarm-E-Mail(s) versendet.")

    matched = _load_matched_products()
    total_products = sum(len(v) for v in matched.values())

    if total_products == 0:
        st.info(
            "Keine Treffer.  \n"
            "Mögliche Ursachen: Wishlist leer (→ `migrate_wishlist.py` ausführen), "
            "keine aktiven Angebote, oder alle Filter zu streng."
        )
    else:
        # ── Produkte in "aktuell" und "kommend" aufteilen ──
        now_dt = datetime.now(timezone.utc)

        current_by_item: dict[str, list[dict]] = {}
        upcoming_list: list[tuple[datetime, str, dict]] = []

        for item_name, products in matched.items():
            for prod in products:
                vf_dt = _parse_iso_to_dt(prod["primary"].get("valid_from"))
                if vf_dt and vf_dt > now_dt:
                    upcoming_list.append((vf_dt, item_name, prod))
                else:
                    current_by_item.setdefault(item_name, []).append(prod)

        # Kommende: erst nach valid_from, dann nach Wishlist-Name
        upcoming_list.sort(key=lambda t: (t[0], t[1]))
        upcoming_by_item: dict[str, list[dict]] = {}
        for _, item_name, prod in upcoming_list:
            upcoming_by_item.setdefault(item_name, []).append(prod)

        n_current  = sum(len(v) for v in current_by_item.values())
        n_upcoming = len(upcoming_list)
        st.caption(f"{n_current} aktuelle · {n_upcoming} kommende Treffer")

        # ── Abschnitt 1: Aktuelle Angebote ──
        st.markdown("### 🛒 Aktuelle Angebote")
        if current_by_item:
            for item_name, products in current_by_item.items():
                _render_offer_group(item_name, products, upcoming=False)
        else:
            st.info("Keine aktuellen Treffer — aber schau auch kommende Angebote unten.")

        # ── Abschnitt 2: Kommende Angebote ──
        if upcoming_by_item:
            st.markdown("### 🔮 Kommende Angebote (ab nächster Woche)")
            for item_name, products in upcoming_by_item.items():
                _render_offer_group(item_name, products, upcoming=True)

# ── Tab 2: Wishlist ─────────────────────────────────────────────────────────
with tab_wish:
    st.subheader("Meine Wunschliste")

    if st.button("➕ Neuer Eintrag", type="primary"):
        _wishlist_form(edit_id=None)

    rows = _wishlist_rows()

    if not rows:
        st.warning(
            "Keine Einträge.  \n"
            "Bitte `python scripts/migrate_wishlist.py` ausführen oder oben hinzufügen."
        )
    else:
        # Tabellen-Header
        hdr = st.columns([1, 2, 3, 3, 1.2, 1.2, 0.8, 0.8])
        for col, label in zip(hdr, ["Aktiv", "Name", "Marken", "Keywords", "Max €", "Einheit", "", ""]):
            col.markdown(f"**{label}**")
        st.divider()

        repo = OfferRepository(DB_PATH)

        for row in rows:
            item_id   = row["id"]
            item_name = row["name"]

            def _on_toggle(iid: int = item_id) -> None:
                OfferRepository(DB_PATH).toggle_wishlist_item_active(iid)
                st.cache_data.clear()

            cols = st.columns([1, 2, 3, 3, 1.2, 1.2, 0.8, 0.8])
            with cols[0]:
                st.checkbox(
                    "",
                    key=f"active_{item_id}",
                    value=bool(row["active"]),
                    on_change=_on_toggle,
                )
            cols[1].write(item_name)
            brands_list = json.loads(row.get("allowed_brands") or "[]")
            cols[2].write(", ".join(brands_list) or "–")
            kw_list = json.loads(row.get("keywords") or "[]")
            cols[3].write(", ".join(kw_list) or "–")
            cols[4].write(f"{row['max_price']:.2f}" if row.get("max_price") else "–")
            cols[5].write(row.get("unit_filter") or "–")
            with cols[6]:
                if st.button("✏️", key=f"edit_{item_id}", help="Bearbeiten"):
                    _wishlist_form(edit_id=item_id)
            with cols[7]:
                if st.button("🗑️", key=f"del_{item_id}", help="Löschen"):
                    _confirm_delete(item_id, item_name)

# ── Tab 3: Alle Angebote ────────────────────────────────────────────────────
with tab_all:
    st.subheader("Alle Angebote")
    all_offers = _all_offers()

    # Filter-Leiste (4 Filter)
    col_s, col_mkt, col_b, col_c = st.columns([3, 2, 2, 2])

    with col_s:
        search = st.text_input("🔍 Suche (Name / Marke)", placeholder="z.B. Milch, ARLA…")

    with col_mkt:
        available_sources = sorted({o.get("source") or "" for o in all_offers if o.get("source")})
        selected_sources  = st.multiselect(
            "Supermarkt",
            options=available_sources,
            default=available_sources,
            format_func=get_display_name,
        )

    with col_b:
        brand_opts   = sorted({o.get("brand") or "" for o in all_offers if o.get("brand")})
        brand_filter = st.selectbox("Marke", ["Alle"] + brand_opts)

    with col_c:
        cat_opts = sorted({
            c
            for o in all_offers
            for c in (json.loads(o["category_ids"]) if isinstance(o.get("category_ids"), str) else [])
            if c != "Angebote"
        })
        cat_filter = st.selectbox("Kategorie", ["Alle"] + cat_opts)

    df_all = _offers_to_df(all_offers)
    if not df_all.empty:
        if selected_sources:
            source_display = {get_display_name(s) for s in selected_sources}
            df_all = df_all[df_all["Markt"].isin(source_display)]
        if search:
            mask = (
                df_all["Produkt"].str.contains(search, case=False, na=False)
                | df_all["Marke"].str.contains(search, case=False, na=False)
            )
            df_all = df_all[mask]
        if brand_filter != "Alle":
            df_all = df_all[df_all["Marke"] == brand_filter]
        if cat_filter != "Alle":
            df_all = df_all[df_all["Kategorie"].str.contains(cat_filter, na=False)]

    st.caption(f"{len(df_all)} Produkte")
    st.dataframe(df_all, use_container_width=True, hide_index=True, column_config=_PRICE_COLS)

# ── Tab 4: Preis-Historie ────────────────────────────────────────────────────
with tab_hist:
    st.subheader("Preis-Historie")

    repo_h = OfferRepository(DB_PATH)
    all_products = repo_h.get_distinct_products_from_history()

    if not all_products:
        st.info("Noch keine Historien-Daten. Bitte zuerst `run_agent.py` ausführen.")
    else:
        # Produkt-Selector
        options_map: dict[str, dict] = {}
        for p in all_products:
            brand = p["brand"] or "?"
            name  = p["name"]
            unit  = p["sales_unit_raw"] or "?"
            mkt   = get_display_name(p["source"])
            pts   = p["data_points"]
            label = f"{brand} – {name} ({unit}) [{mkt}] · {pts} Datenpunkte"
            options_map[label] = p

        selected_label = st.selectbox(
            "Produkt auswählen",
            [""] + list(options_map),
            format_func=lambda x: x or "— bitte wählen —",
        )

        if selected_label:
            sel = options_map[selected_label]
            brand_l = (sel["brand"] or "").lower()
            name_l  = sel["name"].lower()
            unit_r  = sel["sales_unit_raw"] or ""

            # Chart-Daten laden
            chart_data = repo_h.get_price_history_for_chart(
                source=sel["source"],
                brand_lower=brand_l,
                name_lower=name_l,
                sales_unit_raw=unit_r,
            )

            # Vollständige History für Stats
            history = repo_h.get_price_history_for_product(
                source=sel["source"],
                brand_lower=brand_l,
                name_lower=name_l,
                sales_unit_raw=unit_r,
            )

            prices = [h["sale_price"] for h in history if h.get("sale_price")]

            if prices:
                import statistics as _stats

                min_p    = min(prices)
                max_p    = max(prices)
                med_p    = _stats.median(prices)
                n_pts    = len(prices)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Min Preis",    f"{min_p:.2f} €")
                c2.metric("Max Preis",    f"{max_p:.2f} €")
                c3.metric("Median",       f"{med_p:.2f} €")
                c4.metric("Datenpunkte",  n_pts)

                # Chart
                if chart_data:
                    df_ch = pd.DataFrame(chart_data, columns=["Datum", "Preis"])
                    df_ch["Datum"] = pd.to_datetime(df_ch["Datum"])

                    try:
                        import altair as alt

                        line = (
                            alt.Chart(df_ch)
                            .mark_line(point=True)
                            .encode(
                                x=alt.X("Datum:T", title="Datum", axis=alt.Axis(format="%d.%m.")),
                                y=alt.Y("Preis:Q", title="Preis (€)",
                                        scale=alt.Scale(zero=False)),
                                tooltip=["Datum:T", alt.Tooltip("Preis:Q", format=".2f")],
                            )
                        )

                        layers = [line]
                        if n_pts >= 10:
                            quants = _stats.quantiles(prices, n=5)
                            p20, p60 = quants[0], quants[2]
                            for val, color, legend in [
                                (p20, "green",  "P20 (günstig)"),
                                (p60, "orange", "P60 (Schwelle)"),
                            ]:
                                rule = (
                                    alt.Chart(pd.DataFrame({"y": [val], "Linie": [legend]}))
                                    .mark_rule(color=color, strokeDash=[5, 4])
                                    .encode(y="y:Q")
                                )
                                layers.append(rule)

                        st.altair_chart(
                            alt.layer(*layers).properties(height=320),
                            use_container_width=True,
                        )

                    except ImportError:
                        # Fallback ohne Altair
                        st.line_chart(df_ch.set_index("Datum"))

                # Letzte 5 Preisänderungen
                if len(history) >= 2:
                    st.markdown("**Letzte Einträge**")
                    last5 = sorted(history, key=lambda h: h["scraped_at"], reverse=True)[:5]
                    st.dataframe(
                        pd.DataFrame([{
                            "Datum":  h["scraped_at"][:10],
                            "Preis":  f"{h['sale_price']:.2f} €",
                        } for h in last5]),
                        hide_index=True,
                        use_container_width=False,
                    )

                # Cross-Market-Hinweis (wenn andere Märkte existieren)
                all_markets_for_product = [
                    p for p in all_products
                    if p["name"].lower() == sel["name"].lower()
                    and (p["brand"] or "").lower() == (sel["brand"] or "").lower()
                    and p["source"] != sel["source"]
                ]
                if all_markets_for_product:
                    st.info(
                        "Auch verfügbar bei: "
                        + ", ".join(
                            f"{get_display_name(p['source'])} ({p['data_points']} Einträge)"
                            for p in all_markets_for_product
                        )
                    )

# ── Tab 5: Status ────────────────────────────────────────────────────────────
with tab_status:
    st.subheader("System-Status")

    all_o  = _all_offers()
    act_o  = _active_offers()
    wish_r = _wishlist_rows()

    scraped_ats = [o["scraped_at"] for o in all_o if o.get("scraped_at")]
    last_scrape_rel = "–"
    last_scrape_abs = "–"
    if scraped_ats:
        last_raw = max(scraped_ats)
        last_scrape_rel = _time_ago(last_raw)
        try:
            last_scrape_abs = datetime.fromisoformat(last_raw).astimezone().strftime("%d.%m.%Y %H:%M")
        except ValueError:
            last_scrape_abs = last_raw[:16]

    active_wish = sum(1 for i in wish_r if i.get("active"))

    alert_wish = sum(1 for i in wish_r if i.get("alert_enabled"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Angebote gesamt",   len(all_o))
    c2.metric("Davon noch gültig", len(act_o))
    c3.metric("Wishlist aktiv",    active_wish)
    c4.metric("Letzter Scrape",    last_scrape_rel, help=last_scrape_abs)

    st.divider()

    # ── E-Mail / Alert-Status ──
    repo_st = OfferRepository(DB_PATH)
    alerts_today = repo_st.count_alerts_sent_today()
    email_ok = "✅ konfiguriert" if settings.email_configured else "❌ nicht konfiguriert"

    ca, cb, cc = st.columns(3)
    ca.metric("E-Mail",           email_ok)
    cb.metric("Aktive Alarme",    alert_wish, help="Wishlist-Einträge mit aktivem Alarm")
    cc.metric("Alarme heute",     alerts_today)

    if not settings.email_configured:
        st.warning(
            "Keine SMTP-Zugangsdaten in `.env` — Alarm-E-Mails deaktiviert.  \n"
            "Bitte `SMTP_EMAIL` und `SMTP_PASSWORD` in `.env` setzen."
        )

    st.divider()
    st.code(f"DB-Pfad: {Path(DB_PATH).absolute()}")
