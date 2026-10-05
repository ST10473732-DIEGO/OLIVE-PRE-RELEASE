# OLIVE Connect World relay 1.0.0 (release bundle)

> **Not published yet.** This bundle is an OLIVE 1.0 release-candidate artefact built in
> private CI. Nothing here has been released publicly.

This bundle is everything needed to run your own OLIVE Connect World relay. You do not need
the OLIVE source code. The relay is blind and stateless: both of your devices dial out to it,
it joins the two connections and forwards their already-encrypted bytes. It stores nothing,
has no secrets and no route database.

Contents:

| File | Purpose |
| --- | --- |
| `olive/` | The relay (Python standard library only) |
| `olive-world-relay` | Run it with your system Python 3.11+ |
| `Dockerfile`, `compose.yaml`, `Caddyfile`, `relay.env.example` | Docker Compose with automatic HTTPS |
| `olive-world-relay.service`, `nginx.conf.example` | systemd + nginx alternative |
| `healthcheck.sh` | Check a running relay |
| `BUILD-INFO.json` | Version, source commit and SHA-256 of every file |
| `LICENSE-RELAY.md`, `THIRD_PARTY_NOTICES.md` | Licence (draft) and notices |

## Check the download

```sh
sha256sum -c olive-world-relay-1.0.0.tar.gz.sha256
```

## Docker Compose with automatic HTTPS (recommended)

You need a small Linux server with a public address, Docker with Compose v2, and a DNS name.

```sh
tar xzf olive-world-relay-1.0.0.tar.gz && cd olive-world-relay-1.0.0
cp relay.env.example relay.env && ${EDITOR:-nano} relay.env     # set OLIVE_WORLD_DOMAIN
docker compose --env-file relay.env up -d --build
./healthcheck.sh https://world-relay.<your-domain>
```

Open TCP 80 (certificate issuance only) and 443. Then, on the OLIVE computer: Devices ›
This computer › OLIVE Connect World › Advanced › Relay URL → `wss://world-relay.<your-domain>`.

## Without Docker

```sh
sudo mkdir -p /opt/olive-world-relay && sudo tar xzf olive-world-relay-1.0.0.tar.gz -C /opt/olive-world-relay --strip-components=1
sudo cp /opt/olive-world-relay/olive-world-relay.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now olive-world-relay
```

Put nginx (see `nginx.conf.example`) or another TLS proxy in front of `127.0.0.1:8765`.

## Quick local test

```sh
./olive-world-relay --host 127.0.0.1 --port 8765 --dev
curl http://127.0.0.1:8765/healthz
```
