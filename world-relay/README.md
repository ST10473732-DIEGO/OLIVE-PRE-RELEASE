# OLIVE Connect World relay

A small, stateless and deliberately dumb relay. It lets a paired OLIVE iPhone
reach its OLIVE computer from any network.

* Both devices dial **out** to the relay over `wss://` on port 443. Neither
  side needs port forwarding.
* The relay joins the two connections of one pair and forwards opaque bytes.
  Those bytes are the devices' own pinned TLS 1.3 session, which the relay
  cannot read.
* It stores nothing and runs no models.

Code: `olive/world_relay/`. It uses the Python standard library only, plus
`olive/world/` for the wire protocol and WebSocket. Design and security
details: [`docs/connect-world/protocol.md`](../docs/connect-world/protocol.md).

## Quick local run (development)

```sh
python -m olive.world_relay --host 127.0.0.1 --port 8765 --dev     # ws:// on loopback only
curl http://127.0.0.1:8765/healthz
```

## Production with Docker Compose and automatic TLS (recommended)

Requirements:

* a small Linux server with a public IPv4 and/or IPv6 address
* Docker with Compose v2
* a DNS name you control

1. **DNS.** Point `world-relay.<your-domain>` (A and/or AAAA record) at the
   server.
2. **Firewall.** Allow inbound TCP 80 and 443. Port 80 is used only for
   certificate issuance.
3. **Configure.** On the server, in a checkout of this repository:

   ```sh
   cd world-relay
   cp relay.env.example relay.env
   ${EDITOR:-nano} relay.env          # set OLIVE_WORLD_DOMAIN=world-relay.<your-domain>
   ```

4. **Start.**

   ```sh
   docker compose --env-file relay.env up -d --build
   ```

5. **Check.**

   ```sh
   ./healthcheck.sh https://world-relay.<your-domain>
   ```

   This prints `{"active_tunnels": 0, "protocol": "olive-world/1", "status": "ok", ...}`
   and `readiness 200`.

6. **On the OLIVE computer.** Devices › This computer › OLIVE Connect World ›
   Advanced › Relay URL. Enter `wss://world-relay.<your-domain>`, select
   **Use relay**, then turn World **On**.
7. **On the iPhone.** Open OLIVE once on the **same Wi-Fi** as the computer.
   It is provisioned automatically. After that it connects from anywhere and
   shows **Connected · World**.

Caddy obtains and renews the certificate automatically. The relay container:

* listens only on the private compose network (`172.30.57.0/24`)
* trusts `X-Forwarded-For` only from Caddy (`172.30.57.2`)
* runs as an unprivileged user with a read-only filesystem, no capabilities,
  256 MB memory and 128 processes

### Production reference deployment

OLIVE's public relay `wss://world-relay.getolive.si` runs exactly this Compose and
Caddy setup on a VPS. It passed production acceptance on 2026-10-01: health and
readiness return 200, the container is healthy, it comes back on its own after a full
VPS reboot, and a physical iPhone on cellular reached a desktop on home Wi-Fi with no
VPN or port forwarding. Host hardening used there: a configured firewall, and
key-only SSH with password login disabled. See
[`docs/connect-world/protocol.md`](../docs/connect-world/protocol.md) §14.

### Alternatives

* **Existing nginx:** see `nginx.conf.example`. Run the relay on 127.0.0.1
  with `--behind-proxy --trusted-proxy 127.0.0.1`.
* **systemd, no Docker:** see `olive-world-relay.service`. Python ≥ 3.11 and
  the `olive/world*` sources at `/opt/olive`.
* **TLS in the relay itself:** `--tls-cert fullchain.pem --tls-key privkey.pem`.
  Port 443 needs a capability or port mapping; never run OLIVE as root.

The relay refuses to start a plaintext listener unless one of these applies:

* `--dev` on loopback
* `--behind-proxy`
* the TEST-ONLY `--test-lan` on a private address

## Ports, protocol and limits

| What | Value |
| --- | --- |
| Public | TCP 443 (`wss://<host>/olive-world/1`), TCP 80 only for ACME |
| Relay listener | 8765 (internal) |
| Health | `GET /healthz` → `{"status","version","protocol","active_tunnels"}` |
| Readiness | `GET /readiness` → 200, or 503 while draining |
| Max tunnel message | 256 KiB (checked from the frame header, before allocation) |
| Per-connection buffer | 256 KiB, with TCP backpressure to the sender |
| Hello deadline | 10 s from accept |
| Keepalive / idle | ping 20 s / close after 60 s silent |
| Phone waiting for its computer | 20 s, then `4007 peer_unavailable` |
| Connections | 2048 total, 64 per client address, 120 new per minute per address |

Environment variables (`OLIVE_WORLD_RELAY_*`): `HOST`, `PORT`, `DEV`,
`BEHIND_PROXY`, `TLS_CERT`, `TLS_KEY`, `TRUSTED_PROXIES` (comma-separated),
`MAX_CONNECTIONS`, `PER_IP_CONNECTIONS`, `LOG_LEVEL`.

## Resources and bandwidth

* **CPU and RAM.** Idle cost is tiny. Each connection uses a few kilobytes
  plus at most about 0.5 MB of buffers while transferring. 1 vCPU and 512 MB
  RAM comfortably serve a household or a small team.
* **Bandwidth.** Every World byte crosses the relay twice: in from one
  device, out to the other. A 100 MB video viewed through World is about
  100 MB in plus 100 MB out. OLIVE prefers Direct whenever both devices
  share a network, so normal home use costs nothing.

## Logs

Logs go to stdout (Docker keeps 3 × 10 MB). Each line holds only:

* an anonymous connection number
* the event: `listening`, `hello`, `paired`, `refused`, `close`, `stopped`
* the role (desktop or phone)
* a category, the duration and byte counts

Logs **never** include:

* route ids or credentials
* client or device identities
* addresses
* frame contents, prompts, notes or filenames

Caddy access logging is off.

## Updates and backups

* **Update:**

  ```sh
  git pull && docker compose --env-file relay.env up -d --build
  ```

  Clients reconnect within seconds. Running desktop jobs are unaffected.
* **Backups:** there is nothing to back up. The relay keeps no database and
  no files. Caddy's certificate volume can be recreated, so back it up only
  if you want to avoid re-issuance.

## Privacy: what a relay operator can see

**Visible:**

* device IP addresses
* connection times and durations
* byte counts and timing
* that a route exists (an opaque key)
* which end is the computer

**Not visible:**

* prompts, replies, notes, drawings, files, filenames or media
* device names and identities
* any key that could decrypt the session

The relay provides end-to-end encryption of content, not metadata anonymity.
