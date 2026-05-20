"""Prospekt-Agent Streamlit Dashboard — Phase C2."""
from __future__ import annotations

import html as _html
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

st.set_page_config(page_title="Prospekt-Agent", layout="wide")

# ---------------------------------------------------------------------------
# Global CSS — Clean & Minimal
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* Tabs: kein Emoji-Padding, dezente Schrift */
.stTabs [data-baseweb="tab-list"] { gap: 4px; }
.stTabs [data-baseweb="tab"] {
    font-size: 14px; font-weight: 500; color: #6b7280;
    padding: 6px 14px; border-radius: 6px 6px 0 0;
}
.stTabs [aria-selected="true"] { color: #111827; }

/* Buttons dezenter */
.stButton > button {
    border-radius: 8px;
    border: 1px solid #e5e7eb;
    background: #ffffff;
    color: #374151;
    font-size: 13px;
    font-weight: 500;
    padding: 4px 14px;
}
.stButton > button:hover { background: #f9fafb; box-shadow: none; }

/* Divider dünner */
hr { border-top: 1px solid #f3f4f6 !important; margin: 12px 0 !important; }

/* Metriken kompakter */
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 22px !important;
}

/* Block-Container mehr Luft */
.block-container { padding-top: 1.5rem !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Deutsches Datum
# ---------------------------------------------------------------------------
_DE_WD  = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]
_DE_MON = ["Januar","Februar","März","April","Mai","Juni",
           "Juli","August","September","Oktober","November","Dezember"]

def _german_now() -> str:
    dt = datetime.now()
    return f"{_DE_WD[dt.weekday()]}, {dt.day}. {_DE_MON[dt.month-1]} {dt.year}"

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

_RATING_COLORS = {
    "green":   "#22c55e",
    "yellow":  "#f59e0b",
    "red":     "#ef4444",
    "no_data": "#9ca3af",
}


def _savings_summary(matched: dict[str, list[dict]]) -> tuple[float, int, int, str]:
    """Berechnet Gesamt-Ersparnisse aus allen aktuellen Matches."""
    total   = 0.0
    best_s  = 0.0
    best_t  = ""
    n_prod  = 0
    markets: set[str] = set()
    for products in matched.values():
        for prod in products:
            o = prod["primary"]
            n_prod += 1
            markets.add(o.get("source") or "")
            orig = o.get("original_price")
            sale = o.get("sale_price") or 0.0
            if orig and orig > sale:
                s = orig - sale
                total += s
                if s > best_s:
                    best_s = s
                    disc   = o.get("discount_percent") or 0
                    mkt    = get_display_name(o.get("source") or "")
                    best_t = (
                        f"{o.get('name','')} — {sale:.2f} € statt {orig:.2f} €"
                        f" (−{disc:.0f}%) bei {mkt}"
                    )
    return total, n_prod, len(markets), best_t


def _card_html(
    o: dict,
    alts: list[dict],
    p_count: int,
    rating: dict | None,
    variant_names: list[str],
    upcoming: bool = False,
) -> str:
    """Rendert eine Produktkarte als HTML-String."""
    name      = _html.escape(o.get("name") or "")
    brand     = _html.escape(o.get("brand") or "")
    price     = o.get("sale_price") or 0.0
    orig      = o.get("original_price")
    disc      = o.get("discount_percent")
    img_url   = o.get("image_url") or ""
    market    = _html.escape(get_display_name(o.get("source") or ""))
    n_var     = len(variant_names)
    card_p    = o.get("card_price")

    date_str  = _html.escape(
        _starts_in_text(o.get("valid_from")) if upcoming
        else format_german_date(o.get("valid_until"))
    )

    unit_raw  = o.get("sales_unit_raw") or ""
    bp_str    = _fmt_base_price(o)
    content   = _html.escape(unit_raw + (f" · {bp_str}" if bp_str else ""))

    # Bild oder Platzhalter
    img_el = (
        f'<img src="{img_url}" '
        f'style="width:58px;height:58px;object-fit:contain;border-radius:8px;background:#f9fafb;flex-shrink:0">'
        if img_url else
        '<div style="width:58px;height:58px;border-radius:8px;background:#f3f4f6;flex-shrink:0"></div>'
    )

    # Name-Block
    if n_var > 1:
        preview = " · ".join(_html.escape(v) for v in variant_names[:3])
        if n_var > 3:
            preview += f" (+{n_var-3})"
        name_block = (
            f'<div style="font-size:15px;font-weight:600;color:#111">{n_var} Sorten</div>'
            f'<div style="font-size:11px;color:#9ca3af;margin-top:2px">{preview}</div>'
        )
    else:
        name_block = f'<div style="font-size:15px;font-weight:600;color:#111;line-height:1.3">{name}</div>'
    brand_el = f'<div style="font-size:12px;color:#9ca3af;margin-top:2px">{brand}</div>' if brand else ""

    # Preis-Block
    disc_badge = (
        f'<span style="background:#dcfce7;color:#16a34a;font-size:10px;'
        f'font-weight:600;padding:1px 5px;border-radius:4px;margin-left:4px">−{disc:.0f}%</span>'
        if disc else ""
    )
    old_el = (
        f'<div style="font-size:11px;color:#9ca3af;text-decoration:line-through;'
        f'margin-top:1px">{orig:.2f} €</div>'
        if orig else ""
    )

    # Rating-Badge
    r_el = ""
    if rating:
        lvl   = rating.get("level", "no_data")
        label = _html.escape(rating.get("label", "–").replace("Tendenz: ", ""))
        col   = _RATING_COLORS.get(lvl, "#9ca3af")
        r_el  = f'<div style="font-size:11px;color:{col};font-weight:500;margin-top:2px">{label}</div>'

    # Märkte-Badge
    alts_el = ""
    if alts:
        alts_el = (
            f'<span style="background:#eff6ff;color:#2563eb;font-size:10px;'
            f'padding:1px 6px;border-radius:4px">+{len(alts)}</span>'
        )
    dup_el = (
        f'<span style="font-size:10px;color:#9ca3af">×{p_count}</span>'
        if p_count > 1 else ""
    )

    card_el = (
        f'<span style="font-size:10px;color:#7c3aed">🃏 {card_p:.2f} €*</span>'
        if card_p else ""
    )

    return f"""<div style="background:white;border:1px solid #f0f0f0;border-radius:12px;
padding:14px 16px;margin:6px 0;display:flex;gap:14px;align-items:flex-start">
  {img_el}
  <div style="flex:1;min-width:0">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px">
      <div style="flex:1;min-width:0">{name_block}{brand_el}</div>
      <div style="text-align:right;flex-shrink:0">
        <div style="display:flex;align-items:baseline;gap:4px;justify-content:flex-end">
          <span style="font-size:18px;font-weight:700;color:#111">{price:.2f} €</span>{disc_badge}
        </div>
        {old_el}{r_el}
      </div>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;
    margin-top:10px;flex-wrap:wrap;gap:4px">
      <div style="font-size:12px;color:#6b7280">{content or "–"}</div>
      <div style="display:flex;gap:5px;align-items:center;flex-wrap:wrap">
        {card_el}
        <span style="background:#f3f4f6;color:#555;font-size:11px;
        padding:2px 8px;border-radius:4px">{market}</span>
        {alts_el}{dup_el}
        <span style="color:#d1d5db;font-size:11px">{date_str}</span>
      </div>
    </div>
  </div>
</div>"""


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
    """Rendert eine Wishlist-Gruppe als Card-Layout."""
    n = len(products)
    st.markdown(
        f'<div style="font-size:14px;font-weight:600;color:#374151;'
        f'margin:18px 0 6px 0;border-bottom:1px solid #f3f4f6;padding-bottom:6px">'
        f'{_html.escape(item_name)}'
        f'<span style="font-size:12px;font-weight:400;color:#9ca3af;margin-left:8px">'
        f'{n} Treffer</span></div>',
        unsafe_allow_html=True,
    )

    for prod in products:
        o             = prod["primary"]
        alts          = prod["alternatives"]
        p_count       = prod["primary_count"]
        rating        = prod.get("rating")
        variant_names = prod.get("variant_names") or []

        st.markdown(
            _card_html(o, alts, p_count, rating, variant_names, upcoming=upcoming),
            unsafe_allow_html=True,
        )

        if alts:
            with st.expander(f"Verfügbar bei {len(alts)} weiteren Märkten"):
                alt_rows = []
                for alt in alts:
                    alt_bp    = _fmt_base_price(alt)
                    alt_card  = alt.get("card_price")
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

st.markdown(
    '<h1 style="font-size:28px;font-weight:700;color:#111;margin-bottom:2px">Prospekt-Agent</h1>',
    unsafe_allow_html=True,
)
st.caption(f"Stand: {_german_now()}")

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
    ["Treffer", "Wishlist", "Alle Angebote", "Preis-Historie", "Status"]
)

# ── Tab 1: Treffer ──────────────────────────────────────────────────────────
with tab_hits:
    col_title, col_btn = st.columns([6, 1])
    with col_title:
        st.markdown(
            '<div style="font-size:22px;font-weight:700;color:#111;margin-bottom:4px">'
            'Deine Treffer</div>',
            unsafe_allow_html=True,
        )

    # ── Aktualisieren-Button (Ghost-Stil) ──
    with col_btn:
        if st.button("↻ Aktualisieren", use_container_width=True):
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

        # ── Spar-Übersicht Card ────────────────────────────────────────
        total_s, n_prod, n_mkts, best_deal = _savings_summary(current_by_item)
        if total_s > 0:
            best_html = (
                f'<div style="font-size:12px;color:#15803d;margin-top:12px;'
                f'padding-top:12px;border-top:1px solid #bbf7d0">'
                f'<span style="font-weight:600">Bester Deal: </span>'
                f'{_html.escape(best_deal)}</div>'
            ) if best_deal else ""
            st.markdown(f"""
<div style="background:linear-gradient(135deg,#f0fdf4 0%,#dcfce7 100%);
border:1px solid #bbf7d0;border-radius:14px;padding:22px 26px;margin-bottom:20px">
  <div style="font-size:12px;color:#16a34a;font-weight:600;
  text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">
    Diese Woche sparst du bis zu
  </div>
  <div style="font-size:38px;font-weight:800;color:#111;line-height:1">
    {total_s:.2f} €
  </div>
  <div style="font-size:13px;color:#4b5563;margin-top:6px">
    bei {n_prod} Angeboten über {n_mkts} Märkten
  </div>
  {best_html}
</div>""", unsafe_allow_html=True)

        st.caption(f"{n_current} aktuelle · {n_upcoming} kommende Treffer")

        # ── Abschnitt 1: Aktuelle Angebote ──
        st.markdown(
            '<div style="font-size:16px;font-weight:700;color:#111;margin:20px 0 4px 0">'
            'Aktuelle Angebote</div>',
            unsafe_allow_html=True,
        )
        if current_by_item:
            for item_name, products in current_by_item.items():
                _render_offer_group(item_name, products, upcoming=False)
        else:
            st.info("Keine aktuellen Treffer — schau auch in kommende Angebote unten.")

        # ── Abschnitt 2: Kommende Angebote ──
        if upcoming_by_item:
            st.markdown(
                '<div style="font-size:16px;font-weight:700;color:#111;margin:28px 0 2px 0">'
                'Kommende Angebote</div>'
                '<div style="font-size:12px;color:#9ca3af;margin-bottom:4px">'
                'gültig ab nächster Woche</div>',
                unsafe_allow_html=True,
            )
            for item_name, products in upcoming_by_item.items():
                _render_offer_group(item_name, products, upcoming=True)

# ── Tab 2: Wishlist ─────────────────────────────────────────────────────────
with tab_wish:
    col_wh, col_wb = st.columns([5, 1])
    col_wh.markdown(
        '<div style="font-size:22px;font-weight:700;color:#111;margin-bottom:4px">'
        'Meine Wunschliste</div>',
        unsafe_allow_html=True,
    )
    with col_wb:
        if st.button("+ Neu", use_container_width=True):
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
            col.markdown(f'<span style="font-size:12px;color:#6b7280;font-weight:600">{label}</span>', unsafe_allow_html=True)
        st.divider()

        repo = OfferRepository(DB_PATH)

        for row in rows:
            item_id   = row["id"]
            item_name = row["name"]
            is_active = bool(row["active"])

            def _on_toggle(iid: int = item_id) -> None:
                OfferRepository(DB_PATH).toggle_wishlist_item_active(iid)
                st.cache_data.clear()

            row_alpha = "1.0" if is_active else "0.45"
            st.markdown(
                f'<div style="opacity:{row_alpha}">',
                unsafe_allow_html=True,
            )
            cols = st.columns([1, 2, 3, 3, 1.2, 1.2, 0.8, 0.8])
            with cols[0]:
                st.checkbox("", key=f"active_{item_id}", value=is_active, on_change=_on_toggle)

            cols[1].markdown(
                f'<span style="font-size:13px;font-weight:600;color:#111">'
                f'{_html.escape(item_name)}</span>',
                unsafe_allow_html=True,
            )
            brands_list = json.loads(row.get("allowed_brands") or "[]")
            b_text = ", ".join(brands_list[:2]) + (f" (+{len(brands_list)-2})" if len(brands_list) > 2 else "")
            cols[2].write(b_text or "–")
            kw_list = json.loads(row.get("keywords") or "[]")
            kw_text = ", ".join(kw_list[:3]) + (f" (+{len(kw_list)-3})" if len(kw_list) > 3 else "")
            cols[3].write(kw_text or "–")
            cols[4].write(f"{row['max_price']:.2f}" if row.get("max_price") else "–")
            cols[5].write(row.get("unit_filter") or "–")
            with cols[6]:
                if st.button("Bearbeiten", key=f"edit_{item_id}"):
                    _wishlist_form(edit_id=item_id)
            with cols[7]:
                if st.button("Löschen", key=f"del_{item_id}"):
                    _confirm_delete(item_id, item_name)
            st.markdown("</div>", unsafe_allow_html=True)

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
    st.markdown(
        '<div style="font-size:22px;font-weight:700;color:#111;margin-bottom:12px">Status</div>',
        unsafe_allow_html=True,
    )

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

    active_wish = sum(1 for i in wish_r if bool(i.get("active")))

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

    with st.expander("Technische Details"):
        st.code(f"DB-Pfad: {Path(DB_PATH).absolute()}")
