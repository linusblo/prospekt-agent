#!/bin/bash
# Entrypoint für den Prospekt-Agent HA Add-on.
# Wird von CMD im Dockerfile aufgerufen.
set -e

echo "[INFO] Prospekt-Agent Add-on startet..."

# ── HA-Optionen einlesen ─────────────────────────────────────────────────────
# HA Supervisor schreibt die Add-on-Konfiguration nach /data/options.json
# bevor der Container startet. Wir exportieren die Werte als Umgebungsvariablen.
# load_dotenv() im Anwendungscode überschreibt bereits gesetzte Vars nicht
# (override=False ist der Default) — kein Konflikt nötig.
OPTIONS_FILE="/data/options.json"
if [ -f "$OPTIONS_FILE" ]; then
    eval "$(python3 << 'PYEOF'
import json, sys

try:
    opts = json.load(open("/data/options.json"))
except Exception as e:
    print(f"echo '[WARN] options.json nicht lesbar: {e}'", file=sys.stderr)
    opts = {}

pairs = {
    "SMTP_EMAIL":      opts.get("smtp_email",      ""),
    "SMTP_PASSWORD":   opts.get("smtp_password",   ""),
    "EDEKA_MARKET_ID": opts.get("edeka_market_id", "071115"),
    "COMBI_STORE_ID":  opts.get("combi_store_id",  "220012809"),
    "SCRAPE_TIME":     opts.get("scrape_time",     "06:00"),
}
for k, v in pairs.items():
    v = str(v).replace("'", "'\\''")   # Shell-sicheres Escaping
    print(f"export {k}='{v}'")
PYEOF
    )"
else
    echo "[WARN] /data/options.json nicht gefunden — verwende Standardwerte."
fi

# Persistenter Datenbankpfad (addon_config → /config/ im Container)
export DB_PATH="/config/offers.db"

# ── Erststart-Logik ──────────────────────────────────────────────────────────
# wishlist.yaml aus dem Container (Repo-Snapshot) als initialer Seed
if [ ! -f /config/wishlist.yaml ]; then
    echo "[INFO] Erststart: kopiere Wishlist-Template nach /config/wishlist.yaml"
    cp /app/wishlist.yaml /config/wishlist.yaml
fi

# Wishlist in Datenbank importieren wenn DB noch nicht existiert
if [ ! -f "$DB_PATH" ]; then
    echo "[INFO] Erststart: importiere Wishlist in Datenbank..."
    cd /app && python3 scripts/migrate_wishlist.py
    echo "[INFO] Migration abgeschlossen."
fi

# ── Supervisord starten ──────────────────────────────────────────────────────
# exec ersetzt diese Shell — supervisord erbt alle exportierten Umgebungsvariablen
echo "[INFO] Starte Supervisord (Streamlit-Dashboard + Scraper-Scheduler)..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
