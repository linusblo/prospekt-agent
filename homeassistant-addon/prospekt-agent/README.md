# Prospekt-Agent — Home Assistant Add-on

Supermarkt-Angebote automatisch scrapen und im lokalen Streamlit-Dashboard anzeigen.

Unterstützte Märkte: Aldi Nord, Kaufland, Edeka, Combi, Trinkgut.

---

## Installation

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. URL eintragen: `https://github.com/linusblo/prospekt-agent`
3. "Prospekt-Agent" in der Liste finden und installieren
4. **Konfiguration** anpassen (siehe unten)
5. Add-on starten

---

## Konfiguration

| Option | Default | Beschreibung |
|---|---|---|
| `smtp_email` | — | Absender-Adresse für E-Mail-Alarme |
| `smtp_password` | — | Gmail App-Passwort (kein Account-Passwort!) |
| `edeka_market_id` | `071115` | Edeka Filial-ID (aus der Angebots-URL) |
| `combi_store_id` | `220012809` | Combi Store-ID |
| `scrape_time` | `06:00` | Uhrzeit des täglichen Scraper-Laufs (HH:MM) |

---

## Dashboard

Das Streamlit-Dashboard ist erreichbar unter:

```
http://<HA-IP-Adresse>:8501
```

---

## Datenhaltung und Persistenz

### Datenbank

Die SQLite-Datenbank liegt unter `/data/offers.db` im Add-on-Datenverzeichnis.

- **Überlebt Restarts:** ja — `/data` ist persistent
- **In HA-Backups enthalten:** ja — HA Supervisor sichert `/data` automatisch
- **Pfad im Container:** `/data/offers.db`

### Wishlist

Die `wishlist.yaml` aus dem Repository ist der **initiale Seed**:
- Beim **Erststart** wird sie automatisch nach `/data/wishlist.yaml` kopiert
- Ab dann verwaltest du die Wishlist ausschließlich über das Dashboard
- Die Datei in `/data/` bleibt beim Update des Add-ons erhalten

---

## Logs

Logs findest du unter:

**Settings → System → Logs → (Dropdown) Add-on Prospekt-Agent**

Typische Log-Einträge:

```
[INFO]  Starte Scraper-Lauf...
[INFO]  Aldi Nord: 176 Angebote gefunden
[ERROR] Fehler bei kaufland — Details folgen (Stacktrace)
[INFO]  Scraper-Lauf erfolgreich abgeschlossen (Dauer: 42s)
```

Wenn ein einzelner Markt einen Fehler wirft, laufen die anderen weiter.
Der Scraper schlägt nur komplett fehl (Exit-Code 1) wenn **alle** Sources
gleichzeitig keine Daten liefern.

---

## Release-Workflow

Bei jeder neuen Version folgt dieser Ablauf:

```bash
# 1. Tag setzen (auf dem aktuellen Commit)
git tag v1.1.0
git push origin v1.1.0

# 2. Add-on-Dateien anpassen
#    - homeassistant-addon/prospekt-agent/build.yaml:
#        args.GIT_TAG: "v1.1.0"
#    - homeassistant-addon/prospekt-agent/config.yaml:
#        version: "1.1.0"

# 3. Commit + Push
git add homeassistant-addon/
git commit -m "chore: bump add-on to v1.1.0"
git push
```

HA Supervisor erkennt die neue `version` in `config.yaml` und bietet
im Dashboard ein Update an. Der Build zieht dann exakt den Stand von
`v1.1.0` — deterministisch, kein `main`-Drift.

**Für Entwicklungstests** bleibt `GIT_TAG: "main"` in `build.yaml`.
Das reicht für lokale `docker build`-Tests.

---

## Technische Details

- **Python:** 3.12
- **Build-Strategie:** `git clone --depth 1 --branch ${GIT_TAG}` im Dockerfile
- **Prozessmanagement:** supervisord (Streamlit + Scheduler als separate Prozesse)
- **Scraper-Schedule:** täglich zur konfigurierten Uhrzeit via `schedule`-Library
- **HTTP-Fingerprinting:** `curl_cffi` mit Chrome-Impersonation für Edeka
