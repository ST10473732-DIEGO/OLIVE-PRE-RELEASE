# Connect World

Connect World lets your iPhone reach your OLIVE computer from any network. Both
devices dial **out** to a small relay over WSS on port 443, so neither needs a VPN
or port forwarding. The relay forwards the devices' own pinned TLS 1.3 session
byte for byte: it cannot read prompts, replies, Notes, Draw, attachments or device
identities. It does see transport metadata: IP addresses, connection timing and
byte counts.

You run the relay yourself. OLIVE does not require any particular relay host.

| Page | Contents |
| --- | --- |
| [Beginner guide: run your own relay](self-host-relay.md) | Domain, VPS, SSH key, DNS, firewall, Docker, TLS, health, phone provisioning, cellular test, hardening, updates, troubleshooting |
| [Relay deployment](../../world-relay/README.md) | Docker Compose with automatic TLS (Caddy), nginx or systemd alternatives, updates |
| [Protocol and security](protocol.md) | What is unchanged, `olive-world/1`, what the relay sees, route credentials, Direct preference and failover, limitations |
| [Production acceptance](protocol.md#14-production-acceptance-2026-10-01) | 2026-10-01: desktop on home Wi-Fi, physical iPhone on cellular, public relay |

## Setting it up, in short

1. Deploy a relay on a server with a DNS name you control (`world-relay/README.md`),
   using a hostname such as `world-relay.example.com`.
2. On the desktop: Devices › This computer › OLIVE Connect World: set the relay URL
   `wss://<your relay>/olive-world/1` under *Advanced* and turn it on.
3. Provision the phone **on the home network first**: it receives its route only
   over an authenticated Direct session.
4. Test away from home (Wi-Fi off on the phone), then back home: the phone returns
   to Direct.

First time running a server? Follow the beginner guide:
[Run your own Connect World relay](self-host-relay.md).
