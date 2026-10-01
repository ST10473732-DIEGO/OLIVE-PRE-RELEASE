#!/bin/sh
# Usage: world-relay/healthcheck.sh https://world-relay.example.com
# Prints the relay's public health (no user state) and exits non-zero when not ready.
set -eu
BASE="${1:?relay base URL, e.g. https://world-relay.example.com}"
curl -fsS --max-time 5 "$BASE/healthz" && echo
curl -fsS --max-time 5 -o /dev/null -w 'readiness %{http_code}\n' "$BASE/readiness"
