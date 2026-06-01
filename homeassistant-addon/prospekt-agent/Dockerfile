ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12
FROM ${BUILD_FROM}

RUN apk add --no-cache build-base git supervisor

WORKDIR /app

# ── Anwendungscode ───────────────────────────────────────────────────────────
# GIT_TAG wird von build.yaml übergeben (default: "main").
# Für deterministische Releases: Tag setzen, build.yaml aktualisieren.
#   --depth 1: Shallow Clone, lädt nur den Stand des angegebenen Tags/Branches.
ARG GIT_TAG=main
RUN git clone --depth 1 --branch ${GIT_TAG} \
        https://github.com/linusblo/prospekt-agent.git /tmp/repo \
    && cp -r /tmp/repo/src         ./src         \
    && cp -r /tmp/repo/dashboard   ./dashboard   \
    && cp -r /tmp/repo/scripts     ./scripts     \
    && cp    /tmp/repo/requirements.txt . \
    && cp    /tmp/repo/wishlist.yaml    . \
    && rm -rf /tmp/repo

# ── Python-Abhängigkeiten ────────────────────────────────────────────────────
RUN pip install --no-cache-dir -r requirements.txt

# ── Add-on-spezifische Dateien ───────────────────────────────────────────────
COPY run.sh           /run.sh
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY scheduler.py     /scheduler.py

RUN chmod +x /run.sh

CMD ["/run.sh"]
