ARG BUILD_FROM=python:3.12-slim
FROM ${BUILD_FROM}

# ── Systemabhängigkeiten ─────────────────────────────────────────────────────
# gcc:        C-Extensions in rapidfuzz und curl_cffi
# supervisor: Prozessmanagement (Streamlit + Scheduler)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc \
       supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Anwendungscode ───────────────────────────────────────────────────────────
# Der Build-Kontext ist das Add-on-Verzeichnis (homeassistant-addon/prospekt-agent/).
# Die folgenden Symlinks liegen dort und zeigen auf den Repo-Root:
#   src -> ../../src
#   dashboard -> ../../dashboard
#   scripts -> ../../scripts
#   requirements.txt -> ../../requirements.txt
#   wishlist.yaml -> ../../wishlist.yaml
#
# Docker folgt Symlinks beim Erstellen des Build-Context-Tars — die Zieldateien
# werden eingebettet, nicht die Symlinks selbst. Derselbe git-Commit ergibt
# immer denselben Container-Inhalt (deterministisch).
#
# FALLBACK (falls HA Supervisor Symlinks beim Build nicht folgt):
#   git in Systemabhängigkeiten ergänzen und stattdessen:
#   RUN git clone --depth 1 --branch main \
#           https://github.com/linusblo/prospekt-agent.git /tmp/repo \
#       && cp -r /tmp/repo/src /tmp/repo/dashboard /tmp/repo/scripts . \
#       && cp /tmp/repo/requirements.txt /tmp/repo/wishlist.yaml . \
#       && rm -rf /tmp/repo
#   Der Build-Fehler "COPY failed: file not found" ist das Erkennungszeichen
#   dafür, dass der Fallback aktiviert werden muss.
COPY src/             ./src/
COPY dashboard/       ./dashboard/
COPY scripts/         ./scripts/
COPY requirements.txt .
COPY wishlist.yaml    .

# ── Python-Abhängigkeiten ────────────────────────────────────────────────────
RUN pip install --no-cache-dir -r requirements.txt

# ── Add-on-spezifische Dateien ───────────────────────────────────────────────
COPY run.sh           /run.sh
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY scheduler.py     /scheduler.py

RUN chmod +x /run.sh

CMD ["/run.sh"]
