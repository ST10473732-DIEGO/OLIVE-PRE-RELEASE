# OLIVE Connect World relay 1.0.0: built from this bundle alone (no OLIVE source repository).
#   docker build -t olive-world-relay:1.0.0 .
# Blind and stateless: Python standard library only, no secrets, no route database, no volumes.
# The base image is pinned by digest (Docker Hub index digest for python:3.12-slim, recorded 2026-10-03).
FROM python:3.12-slim@sha256:dddfd7e07f9d15aeeca61529320492139d21cac7f0070c00609243e51e4e0016

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OLIVE_WORLD_RELAY_HOST=0.0.0.0 \
    OLIVE_WORLD_RELAY_PORT=8765 \
    OLIVE_WORLD_RELAY_BEHIND_PROXY=1

LABEL org.opencontainers.image.title="OLIVE Connect World relay" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.licenses="LicenseRef-OLIVE-Relay" \
      org.opencontainers.image.description="Blind, stateless relay for OLIVE Connect World"

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin olive-relay
WORKDIR /app
# Only the relay modules this bundle carries; nothing else from OLIVE.
COPY olive /app/olive
COPY LICENSE-RELAY.md THIRD_PARTY_NOTICES.md BUILD-INFO.json /usr/share/doc/olive-world-relay/

USER olive-relay
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/readiness', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["python", "-m", "olive.world_relay"]
