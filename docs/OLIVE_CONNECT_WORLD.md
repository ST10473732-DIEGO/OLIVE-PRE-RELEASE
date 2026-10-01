# OLIVE Connect World

OLIVE Connect World lets a paired iPhone reach its OLIVE computer from any
network, such as cellular, hotel Wi-Fi or an office network. You don't need a
VPN, port forwarding, a firewall hole or an IP address. Both devices make
**outbound** secure connections to a relay. The relay joins them and forwards
encrypted bytes it cannot read.

World is a *transport*. It sits beneath OLIVE Connect. Chat, Notes, Draw,
attachments and media are exactly the same protocols whether the bytes went
Direct or through World. The computer still does all the work. World never
means cloud AI.

```
SAME LAN (preferred):

  iPhone ─────────────────────────────► Desktop
           Direct Connect (TCP, pinned TLS 1.3)


DIFFERENT NETWORKS:

  iPhone ──WSS:443──► World Relay ◄──WSS:443── Desktop
          (outbound)       │        (outbound)
                           │ forwards opaque bytes;
                           │ cannot read OLIVE content
                           ▼
           the same pinned, mutually authenticated
           TLS 1.3 session, end to end iPhone ⇄ Desktop
```

## 1. What is new, and what is unchanged

| Unchanged | New |
| --- | --- |
| Pairing, device identity (Ed25519 X.509, C2) and the Devices trust store | `olive-world/1` relay rendezvous (`olive/world/wire.py`) |
| TLS 1.3 policy: pinned certificates and no system trust between devices | Relay server `python -m olive.world_relay` (standard library only) |
| Connect frames 1–18 and their limits | Byte bridge from relay to a Connect channel (`olive/world/client.py`) |
| Permissions (Remote AI Off/Ask/Allow, `sync.notes`, `sync.draw`, files) | Desktop presence and provisioning (`olive/connect/world.py`) |
| Revocation, request ledgers, job ids, transfer offsets | Path preference: Direct beats World (`network.py` `adopt`, `olive/world/paths.py`) |
| `olive-chat/1`, `olive-notes/1`, `olive-draw/1` | iPhone: `WorldSocket`, `WorldPathSelector`, Keychain route store, World UI |

## 2. Why the existing TLS session is tunnelled unchanged

Both ends already run Connect's TLS 1.3 over a plain byte stream:

* **Desktop:** pyOpenSSL `SSL.Connection` over a socket.
* **iPhone:** an OpenSSL 3.5.8 memory-BIO adapter (`NativeConnect/OliveTLS.c`)
  that feeds bytes from `ConnectSocket`.

World swaps only that byte stream:

* **Desktop:** the relay WebSocket is bridged into one end of a local socket
  pair. The other end is handed to the normal `Channel` as an inbound
  connection, so the TLS server runs unchanged.
* **iPhone:** `ConnectTransport` takes any `ConnectByteStream`. Direct uses
  `ConnectSocket` (Wi-Fi TCP). World uses `WorldSocket` (`URLSessionWebSocketTask`).

So **no new application cryptography** was added. End-to-end protection is
the same TLS 1.3 session that already protects Direct. Its properties are:

* **Mutual authentication with the paired identities.** Both sides present
  their Ed25519 certificates and pin the peer's exact DER from pairing. The
  verify depth is 0 and the system CA store is never consulted.
* **Fresh keys per connection.** Session tickets are off (`OP_NO_TICKET`) and
  the session cache is off, so every connection performs a full ephemeral key
  exchange. It never resumes.
* **Key exchange.** Measured desktop to desktop over World on this machine:
  `X25519MLKEM768`, a hybrid of ML-KEM-768 and ephemeral X25519.
  * The iPhone uses OpenSSL 3.5.8, which has the same default groups, but
    the group negotiated with a physical iPhone **has not been observed yet**
    (Mac checklist).
  * Every TLS 1.3 group is ephemeral (EC)DHE.
* **AEAD records.** Measured: `TLS_AES_256_GCM_SHA384`. TLS 1.3 only offers
  AEAD suites (AES-GCM, ChaCha20-Poly1305).
* **Forward secrecy.** Each connection's keys come from ephemeral key
  exchange, and resumption is disabled. A later leak of a device identity
  key, or of a World route secret, therefore does not decrypt recorded relay
  traffic.
  * Identity keys only *sign* the handshake.
  * The route secret never touches the TLS keys.
* **Replay and tamper.** TLS 1.3 records carry implicit sequence numbers
  inside the AEAD nonce. If a record is altered, replayed, reordered or
  duplicated, the AEAD check fails (`bad_record_mac`) and the channel closes
  before any byte reaches an application protocol. Above TLS, Connect's
  request ledger and olive-chat/1 job ids still make retries idempotent.
* **Encrypted hello.** After the handshake both sides exchange a fixed
  encrypted Connect HELLO. Nothing is dispatched before both verifiers
  finish.

Domain separation: route credentials use HKDF with the explicit context
`olive-connect-world/v1` and distinct labels (`route-secret`, `route-id`,
`relay-credential`). They are never used as TLS or AEAD keys.

## 3. The relay protocol: olive-world/1

* **Endpoint.** `wss://<relay host>/olive-world/1`, an HTTP/1.1 WebSocket
  upgrade with subprotocol `olive-world.1`. Normally TLS on 443 at a reverse
  proxy.
* **Hello.** The first message is a text frame of at most 512 bytes, sent
  within 10 s:
  `{"credential":"<64 hex>","role":"desktop"|"phone","route":"<32 hex>","v":1}`.
* **Events.** The relay answers `{"event":"waiting","v":1}`, then
  `{"event":"paired","v":1}` once the other role presents the same credential.
* **After `paired`.** Binary messages only, each at most 256 KiB (peers send
  at most 64 KiB). The relay forwards each one to the partner.
* **Rendezvous.** The relay keys rendezvous on
  `SHA-256("olive-world/1 rendezvous\0" ‖ route ‖ credential)`. Knowing a
  route id alone cannot claim or join a route.
* **One route = one pair.** A route has exactly one `desktop` and one
  `phone` slot. There are no rooms and no broadcast. The newest connection
  in a slot replaces the older one (`4003 replaced`), so a phone that
  changed networks gets in at once.
* **Close codes.**

  | Code | Name |
  | --- | --- |
  | 4000 | `protocol_error` |
  | 4001 | `unsupported_version` |
  | 4002 | `hello_timeout` |
  | 4003 | `replaced` |
  | 4004 | `peer_left` |
  | 4005 | `rate_limited` |
  | 4006 | `too_large` |
  | 4007 | `peer_unavailable` (a phone waited 20 s with no computer) |
  | 4008 | `capacity` |
  | 4009 | `idle_timeout` |
  | 1001 | going away (graceful shutdown) |

* **Keepalive.**
  * The relay pings every 20 s. Silence for 60 s closes the connection.
  * Clients ping every 25 s and treat 70 s of silence as a dead path.

**Limits.** All are configurable:

* Message size is checked from the frame header before any allocation.
* Per-connection write buffer is 256 KiB. Forwarding awaits the partner's
  `drain()`, so a slow reader stops the fast sender (TCP backpressure) and
  memory stays bounded.
* A partner that won't read for 30 s ends the session.
* Concurrent connections: 2048 total, 64 per client address. Generous
  because CGNAT shares addresses.
* New connections: 120 per minute per address.
* HTTP head: at most 8 KiB.
* Route table: at most 4096 entries.

**HTTP surface.** Nothing else is served: no admin pages, no listings, no
debug pages. Any other path returns 404.

* `GET /healthz` returns `{"status":"ok","version":..,"protocol":..,"active_tunnels":n}`.
* `GET /readiness` returns 200, or 503 while draining.

**Stateless.** Routes live in memory only and vanish when unmatched. There
is no database, store-and-forward, media cache or account. A restart drops
sessions. Clients reconnect with backoff, and accepted desktop work continues
from desktop state.

**Never a generic proxy.** A route connects only its two registered OLIVE
endpoints. There is no SOCKS, HTTP CONNECT or target address.

## 4. What the relay can and cannot see

The relay **can** see:

* client IP addresses (or the proxy's X-Forwarded-For)
* connect and disconnect times and durations
* byte counts and message timing and sizes
* that a route exists, as an opaque rendezvous key, and its relay credential
* which side is `desktop` and which is `phone`

The relay **cannot** see:

* prompts, replies, Chat messages or sources
* Notes or Draw records
* attachments, filenames or media
* OLIVE protocol payloads
* device names or device identities. The certificates are inside the TLS
  1.3 handshake, which encrypts certificates.
* private keys or route secrets. It receives only an HKDF-derived relay
  credential.

This is end-to-end encryption of **content**, not metadata anonymity.

Tests capture everything the relay forwards and check it:

* every forwarded byte parses as TLS records
* application data uses record type 23
* known strings never appear: a test sentence, a note's text, a prompt, a
  filename, a drawing title, protocol names

## 5. Route credentials and provisioning

* **Desktop secrets.**
  * One 32-byte World master key lives in the OS credential vault
    (reference `connect-world-v1`), next to the Connect identity key.
  * Per-pair values are derived, never stored. `generation` is the per-peer
    counter in `connect/world-v1.json`. `identity` is this computer's
    Connect fingerprint, which binds routes to the Connect identity.
  * `route_secret = HKDF(master, "route-secret" ‖ local ‖ peer ‖ generation ‖ identity)`
  * `route_id = HKDF(master, "route-id" ‖ …)[:16]` (128 bits)
  * `relay_credential = HKDF(route_secret, "relay-credential")`
  * `world-v1.json` holds only On/Off, the relay URL, generations and
    states. It holds no secret.
* **Provisioning an existing pair, with no re-pairing.**
  1. After an authenticated Connect session, the phone asks the read-only
     `connect.ping` / `protocols` probe.
  2. If the computer lists `olive-world/1`, the phone sends
     `connect.ping` / `world` with `{}` or `{"have":"<route id>"}`.
  3. The computer answers one of three ways:
     * `unavailable` (`disabled` | `relay_not_configured` | `secure_storage_unavailable`)
     * `current` (route id + relay URL, no secret)
     * `provisioned` (relay URL, route id, route secret, generation)
* **Idempotent.** The same generation is returned until a rotation or
  revocation. Repeated requests never create routes.
* **Authority.** Fixtures can't use this. It needs an authenticated,
  paired, unrevoked peer and grants no capability.
* **iPhone storage.**
  * The route is stored in the **Keychain**, device-only and not
    synchronizable: one account `world-route-v1.<computer id>` per paired
    computer.
  * The World On/Off preference and the computer's "unavailable" reason are
    non-secret UserDefaults.
* **Route credential role.** A bearer *routing* credential. It reaches the
  computer's relay registration, and nothing more. A stolen or random token
  cannot authenticate: the TLS server for that route pins exactly the
  route's peer certificate. Desktop A's route cannot reach desktop B, because
  the phone pins A.
* **Rotation.**
  * *Rotate World route* (Devices, under Advanced on a device) increments the
    generation. The old route can no longer meet the computer, and an active
    World tunnel for it ends.
  * The phone gets the new route the next time it connects. While it is
    away from the LAN, that means World is unavailable until it next
    connects Direct.
  * Trust is unchanged.
* **Revocation.**
  * Revoking a device on the computer retires its route: the generation
    increments, the route is marked revoked, its presence task stops and
    its channels close.
  * The route is never re-issued, and the `world` operation refuses it.
  * Even a replayed old route registration fails: the TLS context for that
    route requires a paired, unrevoked certificate.
  * On the iPhone, unpairing or an authenticated revocation forgets that
    computer's route.
  * Other devices are untouched.

## 6. Direct preference, fallback and handover

Policy (`olive/world/paths.py`, mirrored by `WorldPathSelector.swift`):

* **Start.**
  * Direct attempts begin immediately on Wi-Fi with a discovered endpoint.
  * World begins **1.5 s** later. It begins at once when there is no Wi-Fi
    or no endpoint, or in forced-World test mode.
* **First authenticated channel wins.** If World wins while a Direct
  attempt is still running, a 0.75 s grace lets a nearly simultaneous Direct
  win instead.
* **One logical peer.**
  * The computer keeps one channel per peer.
  * In `LocalNetwork.adopt`, Direct replaces World (`retirement_direct_preferred`).
  * World never displaces Direct (`direct_preferred`).
  * Both ends apply the same rule, so neither duplicate channels nor
    duplicate device cards appear.
* **World to Direct.** The phone probes Direct while on World:
  * when Wi-Fi returns (NWPathMonitor)
  * when Bonjour finds the computer
  * every 30 s on Wi-Fi

  A success replaces World.
* **Direct to World.** When Wi-Fi drops, the phone closes the Direct channel
  at once and retries. World starts immediately because the LAN is not
  usable.
* **No duplicated work.** Old channels' callbacks are generation-checked
  (`finished()` acts only on the current channel). Retries stay idempotent:
  * Chat jobs are addressed by job id (start resend is idempotent; status
    is polled).
  * Attachments resume from the computer's offset by content hash.
  * Media downloads resume the same `.part` file by offset.
  * Notes and Draw resend idempotent CRDT and records.
* **Traffic priority.** Connect is already stop-and-wait per request:
  attachment and artifact chunks are one 128 KiB frame per request. Cancel,
  status, ACKs and small Notes updates therefore never wait behind a whole
  transfer. World preserves byte order and adds no queue of its own. Each
  pair uses its own WebSocket, so pairs never block each other.
* **Deadlines over the internet.** On World channels, the per-frame,
  handshake and write deadlines are 5× the LAN values on both ends: 15 s,
  15 s and 10 s on the desktop. Limits and the idle timeout are unchanged.

## 7. Reconnect, keepalive and lifecycle

* **Backoff.**
  * Delays: 0.5, 1, 2, 5, 10, 30 s, with ±20 % jitter. The ceiling is 30 s.
  * It resets after a connection that lived 30 s.
  * The desktop re-registers immediately after an *authenticated* session
    ends. Failed tunnels back off.
  * The iPhone stops after about 10 minutes and shows
    "Offline · Waiting for your computer". A network change, returning to
    the foreground or *Reconnect* restarts it.
* **Network changes.** NWPathMonitor (no polling) triggers one immediate
  attempt:
  * when the network returns
  * Wi-Fi ↔ cellular
* **No duplicate loops.** The desktop presence has one event-loop thread and
  one task per pair and generation. Tested: ten refreshes produce one
  thread, one task and one relay registration.
* **iOS lifecycle.** World connects automatically while OLIVE Mobile is
  active. On return from the background it reconnects and recovers status.
  * iOS does not keep sockets alive for suspended apps, and no push
    infrastructure was added.
  * Accepted desktop jobs continue while the phone sleeps.
  * The Keychain route survives force-quit and relaunch.
* **Desktop relaunch or reboot.** Presence starts with OLIVE Connect and
  dials out again. It needs no port forwarding, UPnP or configuration.

## 8. Backward compatibility

* Old phone with a new desktop: the phone never sends `world`, and Direct
  is unchanged.
* The probe result keeps exactly `{pong, protocols}`. `olive-world/1` is one
  more string in the list. Shipped phones only test membership of their own
  names, and a test checks this.
* New phone with an old desktop: the probe doesn't list `olive-world/1`. The
  phone shows "Not supported by this computer" and never sends `world`.
  * Had it sent `world`, an older desktop would refuse it with
    `unknown_operation` and keep the channel open (tested).
* Devices UI: an older backend has no `world` key, so the World card is
  hidden. `live.connection` stays `"local"` for Direct.
* The iPhone's `ConnectFailure` enum is untouched. World reasons have their
  own `WorldFailure` type, because exhaustive switches exist.

## 9. Backup, restore and profile copies

* World secrets are in the OS vault, never in profile files or backups.
* A profile restored or copied to another location or machine has no vault
  master key (vault namespaces are per profile path), and no Connect
  identity key either. Connect requires re-pairing, and World is
  re-provisioned on the first Direct connection.
* Routes are bound to the Connect identity fingerprint. A new identity
  derives different routes.
* If two running copies register the same route, the relay keeps replacing
  one with the other. After 3 replacements in 2 minutes the computer reports
  "In use elsewhere" (`world_identity_conflict`) and backs off for 5 minutes.

## 10. Settings and UI

* **Desktop: Devices › This computer › OLIVE Connect World.**
  * An On/Off toggle and a status:
    * Ready
    * Connecting…
    * Relay unavailable
    * Relay not configured
    * Waiting for Connect
    * In use elsewhere
  * *Advanced* shows the relay host, relay state, protocol, the relay URL
    (self-hosting) and the metadata note.
  * A paired device shows **Connected · Direct** or **Connected · World**,
    only after OLIVE authenticated the peer.
  * Its details show the World state:
    * Not set up yet
    * Setting up this device…
    * Ready
    * Connected · World
    * Revoked

    They also show the last World connection, bytes through the relay,
    reconnects and *Rotate World route*.
  * Activity shows "Connected via OLIVE Connect World" and "Set up for OLIVE
    Connect World".
* **iPhone.**
  * Devices shows **Connected · Direct** or **Connected · World**. Under
    *Permissions & details* there is Path and the OLIVE Connect World state.
  * Settings › OLIVE Connect World has a toggle and status:
    * Ready
    * Not set up yet
    * Off on your computer
    * Relay unavailable
    * Ready · Computer offline
    * Not supported by this computer
  * Advanced diagnostics show supported, provisioned and path. They never
    show a route or key.
* **Relay URL.**
  * Desktop: `world_relay_url` in Advanced, or the managed default
    `OLIVE_WORLD_RELAY_URL` when one is genuinely configured. There is no
    hard-coded relay.
  * Only `wss://` is accepted.
  * `ws://` is accepted only with `OLIVE_WORLD_DEV=1` on loopback, or the
    TEST-ONLY `OLIVE_WORLD_TEST_LAN=1` on a private LAN address.
  * The iPhone refuses `ws://` unless a DEBUG build is launched with
    `--olive-world-test-lan`. `NSAllowsLocalNetworking` permits plaintext
    only to local addresses, and release code never builds a `ws://` URL.

## 11. Running and deploying the relay

```sh
# Development (loopback, plaintext, explicit):
python -m olive.world_relay --host 127.0.0.1 --port 8765 --dev
# Desktop against it (development only):
OLIVE_WORLD_DEV=1 OLIVE_WORLD_RELAY_URL=ws://127.0.0.1:8765 ./run_olive.sh
```

Production is `world-relay/`:

* Docker image and Compose with Caddy (automatic TLS)
* nginx and systemd alternatives
* a health check script

See [`world-relay/README.md`](../world-relay/README.md).

## 12. Test-only switches

These are clearly named, and none of them weakens production:

| Switch | Effect |
| --- | --- |
| Python `WorldPeer` | The client (phone) role for integration tests and the Mac test host. Credentials come only from a real provisioning answer. |
| `tests/world_fixture.RelayThread` | A loopback development relay. Its `observer` captures (and in tamper and replay tests, alters) forwarded bytes. The CLI never sets it. |
| iPhone DEBUG `--olive-world-force` / `OLIVE_WORLD_FORCE=1` | No Direct attempts. |
| iPhone DEBUG `--olive-world-test-lan` | `ws://` relay on a private LAN address (Mac test host). |
| `tests/fixtures/draw_phone_test_host.py --world` | Test relay on the Mac's LAN plus World commands: `world`, `world_rotate`, `world_on`/`world_off`, `relay_restart`, `drop_direct`. |

## 13. Limitations

* **Public relay.** Public deployment and cellular ↔ home Wi-Fi acceptance
  need a real relay host. None was configured in this repository.
* **iOS background.** iOS suspends background sockets. World is active
  while OLIVE Mobile is in the foreground, plus the existing continued
  processing for user-started work.
* **Relay load.** Relay bandwidth equals the World traffic. A 100 MB video
  through World is 100 MB in plus 100 MB out at the relay. Direct is
  preferred so that this happens only away from home.
* **Rotation while away.** Rotating a route while the phone is away takes
  World offline for that phone until it next connects on the LAN. This is
  intentional for suspected compromise.
* **Single relay.** One relay URL at a time. No multi-relay failover.
