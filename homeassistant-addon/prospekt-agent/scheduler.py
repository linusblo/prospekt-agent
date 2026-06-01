"""
Täglicher Scraper-Scheduler für das Prospekt-Agent HA Add-on.

Läuft als dauerhafter supervisord-Prozess. Startet run_agent.py einmal
täglich zur konfigurierten Uhrzeit (SCRAPE_TIME, Default: 06:00).

Beim ersten Start (keine DB vorhanden): sofortiger Initiallauf, damit
das Dashboard nach dem ersten Add-on-Start direkt Daten zeigt.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime

import schedule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [scheduler]  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("scheduler")

SCRAPE_TIME = os.getenv("SCRAPE_TIME", "06:00")
DB_PATH     = os.getenv("DB_PATH", "/data/offers.db")


def run_scraper() -> None:
    """Führt run_agent.py aus und loggt Ergebnis und Fehler klar."""
    log.info("Starte Scraper-Lauf...")
    start = datetime.now()
    result = subprocess.run(
        [sys.executable, "/app/scripts/run_agent.py"],
        cwd="/app",
        env=os.environ.copy(),
        capture_output=False,   # Ausgabe direkt an stdout/stderr (supervisord leitet weiter)
    )
    elapsed = (datetime.now() - start).seconds
    if result.returncode == 0:
        log.info("Scraper-Lauf erfolgreich abgeschlossen (Dauer: %ds).", elapsed)
    elif result.returncode == 1:
        # run_agent.py exitiert mit 1 wenn ALLE Sources fehlschlagen
        log.error(
            "Scraper-Lauf fehlgeschlagen — alle Sources konnten keine Daten liefern "
            "(Dauer: %ds). Details siehe Logs oben.", elapsed
        )
    else:
        # Teilfehler: einzelne Sources sind abgestürzt, andere liefen durch
        log.warning(
            "Scraper-Lauf beendet mit Code %d (Dauer: %ds). "
            "Einzelne Sources haben Fehler gemeldet — Details siehe Logs oben.",
            result.returncode, elapsed,
        )


# ── Täglicher Lauf zur konfigurierten Uhrzeit ────────────────────────────────
schedule.every().day.at(SCRAPE_TIME).do(run_scraper)
log.info("Scheduler aktiv — Scraper läuft täglich um %s.", SCRAPE_TIME)
log.info("DB-Pfad: %s", DB_PATH)

# ── Initiallauf bei Erstinstallation ─────────────────────────────────────────
# run_agent.py läuft bereits in run.sh beim Erststart wenn die DB fehlt.
# Hier nur als zusätzliche Absicherung falls supervisord den Scheduler
# vor run.sh's Initiallauf startet.
if not os.path.exists(DB_PATH):
    log.info("DB noch nicht vorhanden — starte Initiallauf sofort.")
    run_scraper()

# ── Hauptschleife ─────────────────────────────────────────────────────────────
while True:
    schedule.run_pending()
    time.sleep(30)   # 30s Polling für pünktliche Ausführung
