"""Prospekt-Agent Streamlit Dashboard — Phase C2."""
from __future__ import annotations

import hashlib
import html as _html
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis.price_rating import RATING_EMOJI
from src.config.markets import get_display_name
from src.utils.text_normalize import normalize_for_matching as _nm
from src.utils.source_urls import get_overview_url
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
/* ── Design Tokens ─────────────────────────────────────────── */
:root {
    --card:       #171c26;
    --card-border:#262d3b;
    --text-dim:   #8b93a3;
    --green:      #34d399;
    --green-dim:  rgba(52,211,153,0.12);
    --amber:      #fbbf24;
    --amber-dim:  rgba(251,191,36,0.12);
}

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

/* ── Markt-Filter-Pills: grüne Selektion + Farbpunkte ─────────── */
[data-testid="stPills"] button[aria-pressed="true"],
[data-testid="stPills"] button[aria-selected="true"] {
    background-color: var(--green-dim) !important;
    color: var(--green) !important;
    border-color: rgba(52,211,153,0.4) !important;
}
/* Farbpunkte je Markt (alphabetisch: aldi_nord, combi, edeka, kaufland, trinkgut) */
[data-testid="stPills"] button:nth-of-type(1)::before { content: "● "; color: #00b2e3; }
[data-testid="stPills"] button:nth-of-type(2)::before { content: "● "; color: #005ca9; }
[data-testid="stPills"] button:nth-of-type(3)::before { content: "● "; color: #ffd500; }
[data-testid="stPills"] button:nth-of-type(4)::before { content: "● "; color: #e10915; }
[data-testid="stPills"] button:nth-of-type(5)::before { content: "● "; color: #f39200; }
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
    excl_map = repo.get_all_excludes_as_matcher_dict()
    results_by_item = Matcher(
        wishlist, food_only=True, repository=repo, excluded=excl_map
    ).match_all(offers)
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


# ---------------------------------------------------------------------------
# Shopping-List Helpers
# ---------------------------------------------------------------------------

def _sl_keys() -> set[tuple[str, str]]:
    """Aktuelles Set aller (source, slug) auf der Einkaufsliste."""
    return {
        (i["offer_source"], i["offer_slug"])
        for i in OfferRepository(DB_PATH).get_shopping_list()
    }


def _sl_add(o: dict) -> None:
    OfferRepository(DB_PATH).add_to_shopping_list({
        "offer_source":    o.get("source") or "",
        "offer_slug":      o.get("product_slug") or "",
        "product_name":    o.get("name") or "",
        "brand":           o.get("brand"),
        "sale_price":      o.get("sale_price"),
        "original_price":  o.get("original_price"),
        "base_price_text": _fmt_base_price(o),
        "sales_unit":      o.get("sales_unit_raw"),
        "market_name":     get_display_name(o.get("source") or ""),
    })


def _wl_tracked_brands() -> set[str]:
    """Alle norm. Marken die bereits von irgendeinem Wishlist-Item verfolgt werden."""
    return {
        _nm(b)
        for item in OfferRepository(DB_PATH).get_wishlist_items()
        for b in item.allowed_brands
    }


def _sl_remove_by_keys(source: str, slug: str) -> None:
    repo = OfferRepository(DB_PATH)
    for item in repo.get_shopping_list():
        if item["offer_source"] == source and item["offer_slug"] == slug:
            repo.remove_from_shopping_list(item["id"])
            return


def _elem_key(prefix: str, source: str, slug: str,
              name: str = "", brand: str = "",
              item_scope: str = "") -> str:
    """
    Baut einen stabilen, eindeutigen Streamlit-Widget-Key.

    Problem 1: slug[:32] kann bei Trinkgut/Edeka kollidieren (gleicher URL-Präfix).
    Problem 2: Dasselbe Angebot kann in ZWEI Wishlist-Gruppen auftauchen wenn zwei
               Wishlist-Items denselben Offer matchen. Ohne item_scope entstehen dann
               identische Keys in verschiedenen _render_offer_group-Aufrufen.

    Fallback-Kette: name → brand → md5(source+slug)[:12]
    item_scope: Wishlist-Item-Name (optional) — macht Keys über Gruppen hinweg eindeutig.
    """
    def _norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())[:12]

    disambig = _norm(name) or _norm(brand)
    if not disambig:
        disambig = hashlib.md5(f"{source}{slug}".encode()).hexdigest()[:12]

    scope  = _norm(item_scope)[:8] if item_scope else ""
    suffix = f"_{scope}" if scope else ""
    return f"{prefix}_{source}_{slug[-24:]}_{disambig}{suffix}"


@st.cache_data(ttl=30)
def _wishlist_keyword_set() -> set[tuple[str, str]]:
    """
    {(brand_norm, kw_norm)} für alle aktiven Wishlist-Items.
    TTL 30s — wird nach add_wishlist_item() explizit geleert.

    # TODO: st.cache_data.clear() im Dialog löscht alle Caches.
    #       Später nur gezielt _wishlist_keyword_set und die
    #       Funktionen löschen, die die ✓-Spalten in "Alle Angebote"
    #       befüllen (_all_offers, _load_matched_products).
    """
    items = OfferRepository(DB_PATH).get_wishlist_items()
    return {
        (_nm(b), _nm(kw))
        for item in items
        for b in item.allowed_brands
        for kw in [item.name] + list(item.keywords)
    }


def _send_shopping_list_email(items: list[dict]) -> None:
    """Verschickt die Einkaufsliste per E-Mail an DEFAULT_ALERT_RECIPIENTS."""
    from src.notifications.email_sender import EmailSender

    by_market: dict[str, list[dict]] = {}
    for item in items:
        by_market.setdefault(item["market_name"], []).append(item)

    n_markets = len(by_market)
    n_items   = len(items)
    subject   = f"Einkaufsliste — {n_items} Artikel bei {n_markets} Märkten"

    total      = sum(i["sale_price"] or 0 for i in items if not i.get("checked"))
    total_orig = sum(
        (i["original_price"] or i["sale_price"] or 0)
        for i in items if not i.get("checked")
    )
    savings = total_orig - total

    market_html = ""
    for mkt, mkt_items in sorted(by_market.items()):
        mkt_sum  = sum(i["sale_price"] or 0 for i in mkt_items if not i.get("checked"))
        rows_html = "".join(
            f"<tr><td style='padding:5px 0'>{i['product_name']}</td>"
            f"<td style='padding:5px 0;color:#666;font-size:12px'>{i.get('sales_unit') or ''}</td>"
            f"<td style='padding:5px 0;text-align:right;font-weight:600'>"
            f"{'~~' if i.get('checked') else ''}{i['sale_price']:.2f} €</td></tr>"
            for i in sorted(mkt_items, key=lambda x: x["product_name"])
        )
        market_html += f"""
<div style="margin-bottom:20px">
  <div style="font-size:15px;font-weight:700;border-bottom:1px solid #eee;
  padding-bottom:6px;margin-bottom:8px">{mkt}</div>
  <table style="width:100%;border-collapse:collapse">
    {rows_html}
    <tr style="border-top:1px solid #eee">
      <td colspan="2" style="padding:8px 0;color:#555;font-size:13px">Summe</td>
      <td style="padding:8px 0;text-align:right;font-weight:700">{mkt_sum:.2f} €</td>
    </tr>
  </table>
</div>"""

    savings_html = (
        f'<div style="color:#16a34a;font-size:13px;margin-top:6px">'
        f'Ersparnis: ~{savings:.2f} € gegenüber UVP</div>'
    ) if savings > 0 else ""

    body = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px">
  <h2 style="font-size:22px;color:#111">Deine Einkaufsliste</h2>
  {market_html}
  <div style="border-top:2px solid #111;margin-top:20px;padding-top:14px">
    <div style="font-size:18px;font-weight:700">Gesamtsumme: {total:.2f} €</div>
    {savings_html}
  </div>
  <p style="color:#bbb;font-size:12px;margin-top:28px">Generiert vom Prospekt-Agent</p>
</body></html>"""

    sender     = EmailSender(settings)
    recipients = settings.DEFAULT_ALERT_RECIPIENTS
    sender.send_alert(recipients, subject, body)

_RATING_COLORS = {
    "green":   "#22c55e",
    "yellow":  "#f59e0b",
    "red":     "#ef4444",
    "no_data": "#9ca3af",
}

_MARKET_COLORS = {
    "aldi_nord": "#00b2e3",
    "kaufland":  "#e10915",
    "edeka":     "#ffd500",
    "combi":     "#005ca9",
    "trinkgut":  "#f39200",
}


def _market_color(src: str) -> str:
    return _MARKET_COLORS.get(src, "#262d3b")


def _rating_dot_html(rating: dict | None) -> str:
    if not rating:
        return ""
    lvl   = rating.get("level", "no_data")
    label = _html.escape(rating.get("label", "–").replace("Tendenz: ", ""))
    colors = {"green": "#34d399", "yellow": "#fbbf24", "red": "#ef4444", "no_data": "#9ca3af"}
    color  = colors.get(lvl, "#9ca3af")
    return (
        f'<span style="display:inline-flex;align-items:center;gap:4px">'
        f'<span style="width:7px;height:7px;border-radius:50%;background:{color};'
        f'display:inline-block;flex-shrink:0"></span>'
        f'<span>{label}</span></span>'
    )


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


def _card_html_UNUSED(  # kept for reference, replaced by native Streamlit below
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


def _render_offer_group(
    item_name: str,
    products: list[dict],
    upcoming: bool = False,
    sl_keys_snapshot: set[tuple[str, str]] | None = None,
) -> None:
    """Rendert eine Wishlist-Gruppe — HTML-Cards mit Streamlit-Buttons."""
    n = len(products)
    st.markdown(
        f'<div style="font-size:14px;font-weight:600;color:#c5cdd9;'
        f'margin:18px 0 4px 0;border-bottom:1px solid var(--card-border);padding-bottom:6px">'
        f'{_html.escape(item_name)}'
        f'<span style="font-size:12px;font-weight:400;color:var(--text-dim);margin-left:8px">'
        f'{n} Treffer</span></div>',
        unsafe_allow_html=True,
    )

    for prod in products:
        o             = prod["primary"]
        alts          = prod["alternatives"]
        p_count       = prod["primary_count"]
        rating        = prod.get("rating")
        variant_names = prod.get("variant_names") or []
        n_var         = len(variant_names)

        src    = o.get("source") or ""
        slug   = o.get("product_slug") or ""
        price  = o.get("sale_price") or 0.0
        orig   = o.get("original_price")
        disc   = o.get("discount_percent")
        card_p = o.get("card_price")
        unit_raw = o.get("sales_unit_raw") or ""
        bp_str   = _fmt_base_price(o)

        # ── Bild ─────────────────────────────────────────────────
        img_url = o.get("image_url") or ""
        img_el = (
            f'<img src="{_html.escape(img_url)}" '
            f'style="width:56px;height:56px;object-fit:contain;border-radius:8px;'
            f'background:#1e2533;flex-shrink:0">'
            if img_url else
            '<div style="width:56px;height:56px;border-radius:8px;background:#1e2533;flex-shrink:0"></div>'
        )

        # ── Name-Zeile ───────────────────────────────────────────
        if n_var > 1:
            preview = " · ".join(_html.escape(v) for v in variant_names[:3])
            if n_var > 3:
                preview += f" (+{n_var-3})"
            name_line = (
                f'<span style="color:#c5cdd9">{n_var} Sorten</span>'
                f'<span style="font-size:11px;color:var(--text-dim);margin-left:6px">{preview}</span>'
            )
        else:
            name_h  = _html.escape(o.get("name") or "")
            brand_h = _html.escape(o.get("brand") or "")
            brand_part = (
                f' · <span style="color:var(--text-dim)">{brand_h}</span>' if brand_h else ""
            )
            name_line = f'<span style="color:#c5cdd9">{name_h}</span>{brand_part}'

        # ── Meta-Zeile ───────────────────────────────────────────
        meta_items = []
        if unit_raw or bp_str:
            meta_items.append(_html.escape(unit_raw + (f" · {bp_str}" if bp_str else "")))
        if rating:
            meta_items.append(_rating_dot_html(rating))
        _ov_url     = get_overview_url(src)
        market_name = _html.escape(get_display_name(src))
        mkt_sfx     = ""
        if alts:
            mkt_sfx += f" +{len(alts)}"
        if p_count > 1:
            mkt_sfx += f" ×{p_count}"
        if _ov_url:
            meta_items.append(
                f'<a href="{_html.escape(_ov_url)}" target="_blank" '
                f'style="color:var(--text-dim);text-decoration:none">'
                f'{market_name} ↗{_html.escape(mkt_sfx)}</a>'
            )
        else:
            meta_items.append(f'{market_name}{_html.escape(mkt_sfx)}')
        if upcoming:
            starts_txt = _starts_in_text(o.get("valid_from"))
            if starts_txt and starts_txt != "heute":
                meta_items.append(
                    f'<span style="background:var(--amber-dim);color:var(--amber);'
                    f'font-size:11px;font-weight:600;padding:1px 7px;border-radius:10px;'
                    f'white-space:nowrap">startet {_html.escape(starts_txt)}</span>'
                )
        else:
            date_str = _html.escape(format_german_date(o.get("valid_until")))
            if date_str:
                meta_items.append(date_str)

        sep      = ' <span style="opacity:0.35">·</span> '
        meta_row = sep.join(meta_items)

        # ── Preis-Block (flat string → keine Leerzeilen im f-string-Template) ──
        orig_span = (
            f'<span style="font-size:13px;color:var(--text-dim);'
            f'text-decoration:line-through;margin-right:6px">{orig:.2f} €</span>'
            if orig else ""
        )
        disc_el = (
            f'<div style="background:var(--green-dim);color:var(--green);font-size:12px;'
            f'font-weight:600;padding:2px 8px;border-radius:8px;display:inline-block;'
            f'margin-top:2px">−{disc:.0f}%</div>'
            if disc else ""
        )
        card_el = (
            f'<div style="font-size:11.5px;color:var(--text-dim);margin-top:3px">'
            f'💳 {card_p:.2f} € mit Karte</div>'
            if card_p else ""
        )
        price_block = (
            f'<div style="display:flex;align-items:baseline;justify-content:flex-end">'
            f'{orig_span}'
            f'<span style="font-size:20px;font-weight:700;color:#e8ecf2">{price:.2f} €</span>'
            f'</div>'
            + disc_el + card_el
        )

        border_color = _market_color(src)
        card_html = (
            f'<div style="background:var(--card);border:1px solid var(--card-border);'
            f'border-left:3px solid {border_color};border-radius:10px;padding:10px 14px;'
            f'margin:4px 0;display:flex;gap:12px;align-items:center">'
            f'{img_el}'
            f'<div style="flex:1;min-width:0;overflow:hidden">'
            f'<div style="font-size:15px;font-weight:600;line-height:1.3;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{name_line}</div>'
            f'<div style="font-size:12.5px;color:var(--text-dim);margin-top:4px;'
            f'display:flex;gap:6px;flex-wrap:wrap;align-items:center">{meta_row}</div>'
            f'</div>'
            f'<div style="text-align:right;min-width:110px;flex-shrink:0">{price_block}</div>'
            f'</div>'
        )

        # ── Buttons ──────────────────────────────────────────────
        on_sl = sl_keys_snapshot is not None and (src, slug) in sl_keys_snapshot
        btn_key = _elem_key("sl", src, slug,
                            name=o.get("name") or "",
                            brand=o.get("brand") or "",
                            item_scope=item_name)
        excl_btn_key = _elem_key("excl", src, slug,
                                  name=o.get("name") or "",
                                  brand=o.get("brand") or "",
                                  item_scope=item_name)

        c_card, c_add, c_excl = st.columns([10, 0.7, 0.7])
        with c_card:
            st.markdown(card_html, unsafe_allow_html=True)
        with c_add:
            if on_sl:
                if st.button("✓", key=btn_key,
                             use_container_width=True,
                             help="Aus Einkaufsliste entfernen"):
                    _sl_remove_by_keys(src, slug)
                    st.rerun()
            else:
                if st.button("＋", key=btn_key,
                             use_container_width=True,
                             help="Zur Einkaufsliste hinzufügen"):
                    _sl_add(o)
                    st.rerun()
        with c_excl:
            if st.button("✕", key=excl_btn_key,
                         use_container_width=True,
                         help="Dauerhaft ausblenden"):
                _repo_excl = OfferRepository(DB_PATH)
                _wl_id = next(
                    (r["id"] for r in _repo_excl.get_wishlist_rows()
                     if r["name"] == item_name),
                    None,
                )
                if _wl_id is not None:
                    _repo_excl.add_exclude(
                        _wl_id,
                        src,
                        _nm(o.get("brand") or "")[:32],
                        _nm(o.get("name")  or "")[:40],
                    )
                st.toast("Ausgeblendet — erscheint nicht mehr als Treffer.")
                st.cache_data.clear()
                st.rerun()

        # Alternativen-Expander (außerhalb der Card)
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


def _render_search_result_card(o: dict, sl_keys_snapshot: set[tuple[str, str]]) -> None:
    """Ergebnis-Card der Volltextsuche — gleiche Optik wie Wishlist-Treffer,
    aber ohne Ampel/Ausblenden/Alternativen."""
    src    = o.get("source") or ""
    slug   = o.get("product_slug") or ""
    price  = o.get("sale_price") or 0.0
    orig   = o.get("original_price")
    disc   = o.get("discount_percent")
    card_p = o.get("card_price")
    unit_raw = o.get("sales_unit_raw") or ""
    bp_str   = _fmt_base_price(o)

    img_url = o.get("image_url") or ""
    img_el = (
        f'<img src="{_html.escape(img_url)}" '
        f'style="width:56px;height:56px;object-fit:contain;border-radius:8px;'
        f'background:#1e2533;flex-shrink:0">'
        if img_url else
        '<div style="width:56px;height:56px;border-radius:8px;background:#1e2533;flex-shrink:0"></div>'
    )

    name_h  = _html.escape(o.get("name") or "")
    brand_h = _html.escape(o.get("brand") or "")
    brand_part = (
        f' · <span style="color:var(--text-dim)">{brand_h}</span>' if brand_h else ""
    )

    meta_items = []
    if unit_raw or bp_str:
        meta_items.append(_html.escape(unit_raw + (f" · {bp_str}" if bp_str else "")))
    _ov_url     = get_overview_url(src)
    market_name = _html.escape(get_display_name(src))
    if _ov_url:
        meta_items.append(
            f'<a href="{_html.escape(_ov_url)}" target="_blank" '
            f'style="color:var(--text-dim);text-decoration:none">{market_name} ↗</a>'
        )
    else:
        meta_items.append(market_name)
    date_str = _html.escape(format_german_date(o.get("valid_until")))
    if date_str:
        meta_items.append(date_str)

    sep      = ' <span style="opacity:0.35">·</span> '
    meta_row = sep.join(meta_items)

    orig_span = (
        f'<span style="font-size:13px;color:var(--text-dim);'
        f'text-decoration:line-through;margin-right:6px">{orig:.2f} €</span>'
        if orig else ""
    )
    disc_el = (
        f'<div style="background:var(--green-dim);color:var(--green);font-size:12px;'
        f'font-weight:600;padding:2px 8px;border-radius:8px;display:inline-block;'
        f'margin-top:2px">−{disc:.0f}%</div>'
        if disc else ""
    )
    card_el = (
        f'<div style="font-size:11.5px;color:var(--text-dim);margin-top:3px">'
        f'💳 {card_p:.2f} € mit Karte</div>'
        if card_p else ""
    )
    price_block = (
        f'<div style="display:flex;align-items:baseline;justify-content:flex-end">'
        f'{orig_span}'
        f'<span style="font-size:20px;font-weight:700;color:#e8ecf2">{price:.2f} €</span>'
        f'</div>'
        + disc_el + card_el
    )

    border_color = _market_color(src)
    card_html = (
        f'<div style="background:var(--card);border:1px solid var(--card-border);'
        f'border-left:3px solid {border_color};border-radius:10px;padding:10px 14px;'
        f'margin:4px 0;display:flex;gap:12px;align-items:center">'
        f'{img_el}'
        f'<div style="flex:1;min-width:0;overflow:hidden">'
        f'<div style="font-size:15px;font-weight:600;line-height:1.3;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
        f'<span style="color:#c5cdd9">{name_h}</span>{brand_part}</div>'
        f'<div style="font-size:12.5px;color:var(--text-dim);margin-top:4px;'
        f'display:flex;gap:6px;flex-wrap:wrap;align-items:center">{meta_row}</div>'
        f'</div>'
        f'<div style="text-align:right;min-width:110px;flex-shrink:0">{price_block}</div>'
        f'</div>'
    )

    on_sl   = (src, slug) in sl_keys_snapshot
    btn_key = _elem_key("sl", src, slug,
                        name=o.get("name") or "",
                        brand=o.get("brand") or "",
                        item_scope="suche")

    c_card, c_btn = st.columns([10, 0.7])
    with c_card:
        st.markdown(card_html, unsafe_allow_html=True)
    with c_btn:
        if on_sl:
            if st.button("✓", key=btn_key,
                         use_container_width=True,
                         help="Aus Einkaufsliste entfernen"):
                _sl_remove_by_keys(src, slug)
                st.rerun()
        else:
            if st.button("＋", key=btn_key,
                         use_container_width=True,
                         help="Zur Einkaufsliste hinzufügen"):
                _sl_add(o)
                st.rerun()


def _render_search_results(query: str) -> None:
    """Rendert die Volltextsuche-Ergebnisse — gleiche Card-Optik wie Wishlist-Treffer."""
    results = OfferRepository(DB_PATH).search_offers(query)

    if not results:
        st.caption(f"Keine Angebote für '{query}' gefunden")
        return

    st.caption(f"{len(results)} Treffer für '{query}'")

    sl_keys_snapshot = _sl_keys()
    for o in results:
        _render_search_result_card(o, sl_keys_snapshot)


# ---------------------------------------------------------------------------
# Dialog: Löschen bestätigen
# ---------------------------------------------------------------------------

@st.dialog("Zu Wishlist hinzufügen")
def _wishlist_add_dialog(offer: dict) -> None:
    """
    Dialog zum Anlegen eines neuen Wishlist-Eintrags aus einem Angebot.
    Vorausgefüllt mit Heuristik-Hauptbegriff + Brand, beides editierbar.
    Verhindert Duplikate via Live-Prüfung gegen _wishlist_keyword_set().
    """
    from src.utils.wishlist_suggest import extract_hauptbegriff

    default_name  = extract_hauptbegriff(
        offer.get("name") or "", offer.get("brand") or ""
    )
    default_brand = (offer.get("brand") or "").strip()

    hauptbegriff = st.text_input(
        "Produkt-Bezeichnung *",
        value=default_name,
        help="z.B. 'Bier' statt 'Pilsener' — wird als Suchbegriff in der Wishlist verwendet.",
    )
    brand_input = st.text_input(
        "Marke *",
        value=default_brand,
    )

    # Live-Duplikat-Prüfung bei jedem Tastendruck (gecachtes Set, O(1)-Lookup)
    _kw_set = _wishlist_keyword_set()
    is_duplicate = (
        bool(hauptbegriff.strip())
        and bool(brand_input.strip())
        and (_nm(brand_input), _nm(hauptbegriff)) in _kw_set
    )
    if is_duplicate:
        st.warning("Diese Kombination existiert bereits in der Wishlist.")

    st.divider()
    col_add, col_cancel = st.columns(2)

    if col_add.button(
        "Hinzufügen",
        type="primary",
        disabled=(is_duplicate or not hauptbegriff.strip() or not brand_input.strip()),
        use_container_width=True,
    ):
        try:
            OfferRepository(DB_PATH).add_wishlist_item(
                WishlistItem(
                    name           = hauptbegriff.strip(),
                    allowed_brands = [brand_input.strip().upper()],
                    keywords       = [hauptbegriff.strip()],
                    active         = True,
                    supermarkets   = [],
                )
            )
            _wishlist_keyword_set.clear()  # Duplikat-Cache invalidieren
            st.cache_data.clear()          # Alle Angebote-Tabelle + Treffer refreshen
            st.toast(
                f"'{hauptbegriff.strip()}' ({brand_input.strip().upper()}) "
                f"zur Wishlist hinzugefügt."
            )
            st.rerun()
        except sqlite3.IntegrityError:
            st.error(
                f"Ein Wishlist-Eintrag mit dem Namen "
                f"**'{hauptbegriff.strip()}'** existiert bereits."
            )

    if col_cancel.button("Abbrechen", use_container_width=True):
        st.rerun()


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

tab_hits, tab_shop, tab_wish, tab_all, tab_hist, tab_status = st.tabs(
    ["Treffer", "Einkaufsliste", "Wishlist", "Alle Angebote", "Preis-Historie", "Status"]
)

# ── Tab 1: Treffer ──────────────────────────────────────────────────────────
with tab_hits:
    st.markdown(
        '<div style="font-size:22px;font-weight:700;color:#111;margin-bottom:8px">'
        'Deine Treffer</div>',
        unsafe_allow_html=True,
    )

    # ── Toolbar: Suche + Aktualisieren in einer Zeile (Change 7) ────────────
    col_search, col_refresh = st.columns([5, 1])
    with col_search:
        search_query = st.text_input(
            "Suche",
            key="treffer_search_query",
            placeholder="🔍 Suche nach Produkt, Marke oder Beschreibung...",
            label_visibility="collapsed",
        )
    with col_refresh:
        if st.button("↻ Aktualisieren", use_container_width=True):
            from src.adapters.aldi_nord import AldiNordAdapter
            from src.adapters.kaufland import KauflandAdapter
            from src.adapters.trinkgut import TrinkgutAdapter
            adapters = [AldiNordAdapter(), KauflandAdapter(), TrinkgutAdapter()]
            repo_ref = OfferRepository(DB_PATH)

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

    if search_query.strip():
        _render_search_results(search_query.strip())
    else:
        matched = _load_matched_products()

        # ── Markt-Filter als Pills (Change 5) ───────────────────────────────
        # _all_offers() statt _active_offers() → zeigt auch Märkte ohne aktive Angebote
        _all_mkts = sorted({
            o.get("source") or ""
            for o in _all_offers()
            if o.get("source")
        })

        if _all_mkts:
            _disp_names  = [get_display_name(m) for m in _all_mkts]
            _disp_to_src = {get_display_name(m): m for m in _all_mkts}
            _selected = st.pills(
                "Märkte",
                options=_disp_names,
                selection_mode="multi",
                default=_disp_names,
                label_visibility="collapsed",
                key="market_pills",
            )
            _mkt_set = {_disp_to_src[d] for d in (_selected or [])} or set(_all_mkts)
            matched = {
                k: [p for p in v if p["primary"].get("source") in _mkt_set]
                for k, v in matched.items()
            }
            matched = {k: v for k, v in matched.items() if v}

        total_products = sum(len(v) for v in matched.values())

        if total_products == 0:
            st.info(
                "Keine Treffer.  \n"
                "Mögliche Ursachen: Wishlist leer (→ `migrate_wishlist.py` ausführen), "
                "keine aktiven Angebote, oder alle Filter zu streng."
            )
        else:
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

            upcoming_list.sort(key=lambda t: (t[0], t[1]))
            upcoming_by_item: dict[str, list[dict]] = {}
            for _, item_name, prod in upcoming_list:
                upcoming_by_item.setdefault(item_name, []).append(prod)

            n_current  = sum(len(v) for v in current_by_item.values())
            n_upcoming = len(upcoming_list)

            # ── Spar-Banner (Change 6) ───────────────────────────────────────
            total_s, n_prod, n_mkts, best_deal = _savings_summary(current_by_item)
            if total_s > 0:
                best_short = (best_deal[:75] + "…") if len(best_deal) > 75 else best_deal
                best_part  = (
                    f'<div style="font-size:13px;color:var(--text-dim);'
                    f'flex-shrink:0;text-align:right;max-width:300px">'
                    f'Bester Deal: {_html.escape(best_short)}</div>'
                ) if best_deal else ""
                st.markdown(f"""
<div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;
background:var(--green-dim);border:1px solid rgba(52,211,153,0.25);
border-radius:12px;padding:14px 20px;margin-bottom:16px">
  <div style="font-size:26px;font-weight:700;color:var(--green);flex-shrink:0">
    {total_s:.2f} €
  </div>
  <div style="font-size:13px;color:var(--text-dim);flex:1">
    mögliche Ersparnis · {n_prod} Angebote · {n_mkts} Märkte
  </div>
  {best_part}
</div>""", unsafe_allow_html=True)

            st.caption(f"{n_current} aktuelle · {n_upcoming} kommende Treffer")

            _current_sl_keys = _sl_keys()

            st.markdown(
                '<div style="font-size:16px;font-weight:700;color:#111;margin:20px 0 4px 0">'
                'Aktuelle Angebote</div>',
                unsafe_allow_html=True,
            )
            if current_by_item:
                for item_name, products in current_by_item.items():
                    _render_offer_group(item_name, products, upcoming=False,
                                        sl_keys_snapshot=_current_sl_keys)
            else:
                st.info("Keine aktuellen Treffer — schau auch in kommende Angebote unten.")

            if upcoming_by_item:
                st.markdown(
                    '<div style="font-size:16px;font-weight:700;color:#111;margin:28px 0 6px 0">'
                    'Kommende Angebote</div>'
                    '<div style="display:inline-block;font-size:15px;font-weight:600;'
                    'color:#92400e;background:#fef3c7;padding:3px 10px;border-radius:6px;'
                    'margin-bottom:8px">'
                    'gültig ab nächster Woche</div>',
                    unsafe_allow_html=True,
                )
                for item_name, products in upcoming_by_item.items():
                    _render_offer_group(item_name, products, upcoming=True,
                                        sl_keys_snapshot=_current_sl_keys)

# ── Tab 2: Einkaufsliste ────────────────────────────────────────────────────
with tab_shop:
    _repo_sl = OfferRepository(DB_PATH)
    sl_items = _repo_sl.get_shopping_list()
    n_sl     = len(sl_items)

    # ── Header + Aktions-Buttons ─────────────────────────────────────────
    col_sh, col_sb = st.columns([3, 2])
    with col_sh:
        st.markdown(
            '<div style="font-size:22px;font-weight:700;color:#111;margin-bottom:4px">'
            'Einkaufsliste</div>',
            unsafe_allow_html=True,
        )
        if n_sl > 0:
            total_sl   = sum(i["sale_price"] or 0 for i in sl_items if not i["checked"])
            unchecked  = sum(1 for i in sl_items if not i["checked"])
            st.caption(f"{unchecked} offen · {n_sl - unchecked} erledigt · Gesamt: {total_sl:.2f} €")

    with col_sb:
        bc1, bc2, bc3 = st.columns(3)
        if bc1.button("Erledigte löschen", use_container_width=True):
            _repo_sl.clear_checked_items()
            st.rerun()
        if bc2.button("Liste leeren", use_container_width=True):
            _repo_sl.clear_shopping_list()
            st.rerun()
        if bc3.button("Per E-Mail", use_container_width=True):
            if settings.email_configured:
                _send_shopping_list_email(sl_items)
                st.toast("E-Mail versendet!")
            else:
                st.error("SMTP nicht konfiguriert (.env fehlt).")

    if not sl_items:
        st.info("Deine Einkaufsliste ist leer.  \n"
                "Füge Produkte über den **+ Liste**-Button im Treffer-Tab hinzu.")
    else:
        # ── Gruppiert nach Markt ──────────────────────────────────────────
        by_market: dict[str, list[dict]] = {}
        for it in sl_items:
            by_market.setdefault(it["market_name"], []).append(it)

        grand_total = 0.0
        grand_orig  = 0.0

        for mkt_name, mkt_items in sorted(by_market.items()):
            mkt_items_s = sorted(mkt_items, key=lambda x: x["product_name"])
            mkt_total   = sum(i["sale_price"] or 0 for i in mkt_items_s if not i["checked"])
            grand_total += mkt_total
            grand_orig  += sum(
                (i["original_price"] or i["sale_price"] or 0)
                for i in mkt_items_s if not i["checked"]
            )

            with st.container(border=True):
                st.markdown(f"**{mkt_name}** · {len(mkt_items_s)} Artikel")

                for it in mkt_items_s:
                    checked = bool(it["checked"])
                    iid     = it["id"]

                    def _on_chk(item_id: int = iid) -> None:
                        OfferRepository(DB_PATH).toggle_checked(item_id)

                    c_cb, c_name, c_price, c_rm = st.columns([0.5, 4.5, 1.5, 0.5])

                    with c_cb:
                        st.checkbox("", value=checked, key=f"sl_chk_{iid}",
                                    on_change=_on_chk)

                    with c_name:
                        name_md = f"~~{it['product_name']}~~" if checked else f"**{it['product_name']}**"
                        st.markdown(name_md)
                        sub = " · ".join(filter(None, [it.get("brand"), it.get("sales_unit")]))
                        if sub:
                            st.caption(sub)

                    with c_price:
                        price = it.get("sale_price")
                        orig  = it.get("original_price")
                        if price:
                            p_md = f"~~{price:.2f} €~~" if checked else f"**{price:.2f} €**"
                            if orig and orig > price:
                                p_md += f"  \n~~{orig:.2f} €~~"
                            st.markdown(p_md)

                    with c_rm:
                        if st.button("×", key=f"sl_rm_{iid}"):
                            _repo_sl.remove_from_shopping_list(iid)
                            st.rerun()

                st.markdown(
                    f'<div style="text-align:right;color:#555;font-size:13px;'
                    f'margin-top:4px">Summe {mkt_name}: '
                    f'<strong>{mkt_total:.2f} €</strong></div>',
                    unsafe_allow_html=True,
                )

        # ── Gesamtsumme + Ersparnis ───────────────────────────────────────
        savings = grand_orig - grand_total
        savings_txt = (
            f'  \n<span style="color:#16a34a;font-size:13px">'
            f'Ersparnis: ~{savings:.2f} € gegenüber UVP</span>'
            if savings > 0.01 else ""
        )
        st.markdown(
            f'<div style="text-align:right;font-size:17px;font-weight:700;'
            f'margin-top:14px">Gesamtsumme: {grand_total:.2f} €{savings_txt}</div>',
            unsafe_allow_html=True,
        )

# ── Tab 3: Wishlist ─────────────────────────────────────────────────────────
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
        for row in rows:
            item_id   = row["id"]
            item_name = row["name"]
            is_active = bool(row["active"])

            brands_list = json.loads(row.get("allowed_brands") or "[]")
            kw_list     = json.loads(row.get("keywords") or "[]")
            max_price   = row.get("max_price")
            unit_filter = row.get("unit_filter")
            notes       = row.get("notes") or ""

            def _on_toggle(iid: int = item_id) -> None:
                OfferRepository(DB_PATH).toggle_wishlist_item_active(iid)
                st.cache_data.clear()

            with st.container(border=True):
                # Inaktive Cards visuell ausgrauen
                if not is_active:
                    st.markdown(
                        '<div style="opacity:0.45">',
                        unsafe_allow_html=True,
                    )

                c_info, c_actions = st.columns([4, 1])

                with c_info:
                    status_txt = "" if is_active else " *(inaktiv)*"
                    st.markdown(f"**{item_name}**{status_txt}")

                    if brands_list:
                        b = ", ".join(brands_list[:3])
                        if len(brands_list) > 3:
                            b += f" (+{len(brands_list)-3})"
                        st.caption(f"Marken: {b}")

                    if kw_list:
                        kw = ", ".join(kw_list[:4])
                        if len(kw_list) > 4:
                            kw += f" (+{len(kw_list)-4})"
                        st.caption(f"Keywords: {kw}")

                    limits = []
                    if max_price:
                        limits.append(f"Max {max_price:.2f} €")
                    if unit_filter:
                        limits.append(f"Einheit: {unit_filter}")
                    if limits:
                        st.caption(" · ".join(limits))

                    if notes:
                        st.caption(f"ℹ {notes[:100]}{'…' if len(notes) > 100 else ''}")

                with c_actions:
                    st.checkbox(
                        "Aktiv",
                        value=is_active,
                        key=f"active_{item_id}",
                        on_change=_on_toggle,
                    )
                    if st.button("Bearbeiten", key=f"edit_{item_id}", use_container_width=True):
                        _wishlist_form(edit_id=item_id)
                    if st.button("Löschen", key=f"del_{item_id}", use_container_width=True):
                        _confirm_delete(item_id, item_name)

                if not is_active:
                    st.markdown("</div>", unsafe_allow_html=True)

                # ── Ausgeblendete Produkte ────────────────────────────
                _excls = OfferRepository(DB_PATH).get_excludes_for_item(item_id)
                if _excls:
                    with st.expander(f"Ausgeblendete Produkte ({len(_excls)})"):
                        for _ex in _excls:
                            _c1, _c2 = st.columns([4, 1])
                            _c1.caption(
                                f"{_ex['offer_source']} · "
                                f"{_ex['name_norm'] or _ex['brand_norm']}"
                            )
                            if _c2.button(
                                "Wieder anzeigen",
                                key=f"unexcl_{_ex['id']}",
                                use_container_width=True,
                            ):
                                OfferRepository(DB_PATH).remove_exclude(_ex["id"])
                                st.cache_data.clear()
                                st.rerun()

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

    # Daten einmalig laden
    _all_sl_keys = _sl_keys()
    _wl_brands   = _wl_tracked_brands()

    rows_all = []
    for _o in all_offers:
        _cats_raw = _o.get("category_ids") or "[]"
        _cats: list[str] = json.loads(_cats_raw) if isinstance(_cats_raw, str) else (_cats_raw or [])
        _dcats = [c for c in _cats if c != "Angebote"] or _cats
        _row_src = _o.get("source") or ""
        _ov_url  = get_overview_url(_row_src) or ""
        rows_all.append({
            "_key":      f"{_o.get('source','')}|{_o.get('product_slug','')}",
            "Liste":     "✓" if (_o.get("source",""), _o.get("product_slug","")) in _all_sl_keys else "",
            "Wishlist":  "✓" if _nm(_o.get("brand") or "") in _wl_brands else "",
            "Markt":     get_display_name(_row_src),
            "_markt_url": _ov_url,
            "Produkt":   _o.get("name") or "",
            "Marke":     _o.get("brand") or "",
            "Preis":     _o.get("sale_price"),
            "UVP":       _o.get("original_price"),
            "Rabatt":    _o.get("discount_percent"),
            "Inhalt":    _o.get("sales_unit_raw") or "",
            "Basispreis": _fmt_base_price(_o),
            "Gültig bis": format_german_date(_o.get("valid_until")),
            "Kategorie": ", ".join(_dcats),
        })

    df_all = pd.DataFrame(rows_all)

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

    df_all = df_all.reset_index(drop=True)
    st.caption(f"{len(df_all)} Produkte")

    _display_cols = ["Liste", "Wishlist", "Markt", "_markt_url", "Produkt", "Marke",
                     "Preis", "UVP", "Rabatt", "Inhalt", "Basispreis", "Gültig bis"]

    if df_all.empty:
        st.info(
            "Noch keine Angebote in der Datenbank.  \n"
            "Der Scraper läuft täglich zur konfigurierten Uhrzeit, "
            "oder starte ihn manuell über den **↻ Aktualisieren**-Button im Treffer-Tab."
        )
    else:
        _all_event = st.dataframe(
            df_all[_display_cols],
            column_config={
                "Liste":      st.column_config.TextColumn("Liste",    width="small"),
                "Wishlist":   st.column_config.TextColumn("Wishlist", width="small"),
                "_markt_url": st.column_config.LinkColumn("↗", width="small",
                              display_text="↗"),
                **_PRICE_COLS,
            },
            on_select="rerun",
            selection_mode="single-row",
            hide_index=True,
            use_container_width=True,
            key="all_offers_df",
        )

        # ── Action-Area: erscheint wenn Zeile ausgewählt ─────────────────────
        _sel_rows = _all_event.selection.rows
        if _sel_rows:
            _idx     = _sel_rows[0]
            _row     = df_all.iloc[_idx]
            _key_str = str(_row.get("_key", ""))
            _parts   = _key_str.split("|", 1)
            _src     = _parts[0]
            _slg     = _parts[1] if len(_parts) > 1 else ""
            _sel_offer = next(
                (_oo for _oo in all_offers
                 if _oo.get("source") == _src and _oo.get("product_slug") == _slg),
                None,
            )

            st.caption(
                f"Ausgewählt: **{_row['Produkt']}** "
                f"({_row['Marke']}) bei {_row['Markt']}"
            )
            _ac1, _ac2, _ = st.columns([1.5, 1.5, 5])

            with _ac1:
                if _row["Liste"] == "✓":
                    st.button("✓ Auf Liste", key="ao_sl_on",
                              disabled=True, use_container_width=True)
                elif _sel_offer and st.button("+ Zur Liste", key="ao_sl_add",
                                              use_container_width=True):
                    _sl_add(_sel_offer)
                    st.rerun()

            with _ac2:
                if _row["Wishlist"] == "✓":
                    st.button("✓ In Wishlist", key="ao_wl_on",
                              disabled=True, use_container_width=True,
                              help="Diese Marke wird bereits verfolgt.")
                elif _sel_offer and st.button("+ Zur Wishlist", key="ao_wl_add",
                                              use_container_width=True):
                    _wishlist_add_dialog(_sel_offer)
        else:
            st.caption("Zeile auswählen für Aktionen.")

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
