# OLIVE Connect World relay: blind, stateless, standard library only.
# Build from the repository root:  docker build -f world-relay/Dockerfile -t olive-world-relay:1.0.0 .
# (world-relay/compose.yaml does this for you.)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OLIVE_WORLD_RELAY_HOST=0.0.0.0 \
    OLIVE_WORLD_RELAY_PORT=8765 \
    OLIVE_WORLD_RELAY_BEHIND_PROXY=1

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin olive-relay \
 && mkdir -p /app/olive \
 && touch /app/olive/__init__.py
WORKDIR /app
# Only the relay and its wire/WebSocket package: no desktop app, models or user data.
COPY olive/world /app/olive/world
COPY olive/world_relay /app/olive/world_relay

USER olive-relay
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/readiness', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["python", "-m", "olive.world_relay"]
