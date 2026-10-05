# OLIVE Connect

Connect links your OLIVE devices: computers and the iPhone companion. Devices pair
once with a mutual confirmation, then talk over pinned TLS 1.3 using their paired
identities. Pairing grants no capability by itself: each capability (Remote AI,
sync, files, Studio, Notes, Draw) is Off, Ask or Allow per device and can be
revoked at any time.

Paths:

- **Direct**: on the same local network (Bonjour discovery, explicitly selected interface).
- **World**: away from home, through a relay you run ([Connect World](../connect-world/README.md)).
  Direct is always preferred when healthy.

## Using Connect

| Page | Contents |
| --- | --- |
| [Pairing](pairing.md) | Desktop pairing carrier, confirmation and recovery |
| [Devices](devices.md) | Devices workspace: connection state, permissions, approvals |

## Protocol family

| Spec | Scope |
| --- | --- |
| [C2 identity and pairing](protocol/c2-identity-pairing.md) | Ed25519 device identities in the OS vault; exporter-bound pairing comparison |
| [C3 transport](protocol/c3-transport.md) | Discovery (untrusted) and authenticated LAN transport |
| [C5 sync](protocol/c5-sync.md) | Signed record sync for tasks, calendar, reminders and selected Chat |
| [C6 files](protocol/c6-files.md) | Inert, hash-verified file transfer into an inbox |
| [C7 Remote AI](protocol/c7-remote-ai.md) | Bounded, attributed remote text inference |
| [C8 Remote Studio](protocol/c8-remote-studio.md) | Guarded shared workspaces |
| [`olive-chat/1`](protocol/olive-chat-1.md) | Full Chat-mode parity for the phone, attachments and media results |
| [Notes](../features/notes.md) · [Draw](../features/draw.md) | `olive-notes/1` and `olive-draw/1` sync |
| [Connect World](../connect-world/protocol.md) | `olive-world/1` relay rendezvous |

The C1 foundation record is archived in [archive/connect](../archive/connect/OLIVE_CONNECT_C1.md);
the cross-device architecture is in [architecture/cross-device.md](../architecture/cross-device.md).
