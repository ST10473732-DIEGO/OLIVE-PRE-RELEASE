# Connect World relay release bundle

`build_relay.py` turns the relay into one standalone, versioned file that a stranger can run
without the OLIVE source repository:

```sh
python packaging/relay/build_relay.py            # -> dist/relay/olive-world-relay-1.0.0.tar.gz (+ .sha256)
```

The bundle contains only `olive/world/{__init__,wire,websocket}.py`,
`olive/world_relay/{__init__,__main__,server}.py` and a minimal `olive/__init__.py`, plus
`Dockerfile` (base image pinned by digest), `compose.yaml` (builds from the bundle, or uses a
pinned image digest later), `Caddyfile`, `relay.env.example`, a systemd unit, `healthcheck.sh`,
`README.md`, `BUILD-INFO.json` (version, source commit, SHA-256 of every file),
`LICENSE-RELAY.md` (**DRAFT — owner/legal review required**) and `THIRD_PARTY_NOTICES.md`.
No secrets, no route database, no desktop or mobile code. `/healthz` and `/readiness` are
unchanged.

The same commit and `SOURCE_DATE_EPOCH` give the same bytes. The release CI `relay` job builds
the bundle twice and compares, then builds an OCI image from the unpacked bundle into a local
archive (`push: false`) and records its digest. **Nothing is published:** publishing the bundle
or an image is a separate owner decision. Templates live in `bundle/`; the deployment files
shared with `world-relay/` are copied from there at build time.
