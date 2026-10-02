# OLIVE Connect C4.1 — desktop pairing carrier

C4.1 connects two ordinary `DesktopDeviceService` instances through the existing
Devices workspace. No OLIVE Mobile exists yet. Desktop pairing is the reference
peer implementation future Mobile must match. C5 has not begun.

## Separate authorities

Discovery supplies untrusted endpoints. C2 establishes trust using the existing
vault Ed25519 key, self-signed identity certificate, exact certificate pinning,
TLS 1.3 handshake and full 256-bit TLS exporter comparison. C3 authenticates
already-paired channels; permissions and trusted local Ask still govern requests.
Pairing has no Connect dispatch, tool registry, generic RPC, filesystem, model,
Studio, Mail, terminal, desktop-control or Electron IPC interface.

Both desktop users select an approved local interface and turn Connect on.
Discovery can remain Off. On A, **Connect a device** creates a temporary listener
and QR. On B, **Pair device** accepts the copied public offer in a bounded text
field. No camera permission is requested. Both show the candidate's display
name, UUID/fingerprint, comparison and expiry. Names are authenticated transcript
metadata, not authority. Neither candidate is shown as online or trusted.

Both users must enter the value observed on the other desktop and choose
**Values match**. One confirmation remains waiting. A mismatch destroys the
session. Both confirmations allow completion; permissions and capabilities remain
empty/Off. C3 can subsequently establish its own authenticated socket using the
persisted identity. No pairing socket becomes a C3 channel. Revocation and the
existing prohibition on revoked-key aliases apply during completion and recovery.

## Offer and wire versions

`olive-pairing-tls13/1` remains strict and unchanged; its synthetic C2 tests remain
unchanged. Desktop emits explicit `olive-pairing-tls13/2`, adding exactly:

- `endpoint: {address, port}`: the selected interface's numeric address and the
  temporary OS-assigned TCP port; explicitly non-authoritative routing material.
- `display_name`: bounded display metadata from the existing local device record.

The responder echoes the offer's endpoint and changes only identity and display
name in its public reply. The canonical offer/reply pair remains the input to
C2's existing transcript digest and TLS exporter binding. The exporter algorithm,
label, identity contract, key and certificate are unchanged. V1 rejects V2 fields;
V2 requires them. There is no silent reinterpretation or downgrade on desktop.

Addresses must be canonical numeric RFC1918 IPv4, loopback, or IPv6 ULA. DNS,
public/WAN, wildcard, multicast, scoped/link-local and IPv4-mapped IPv6 addresses
are rejected. The responder additionally requires the endpoint to belong to its
selected interface's subnet and binds its outgoing socket to that interface.
A copied or redirected endpoint cannot authenticate a candidate.

The carrier is a four-byte network-order length followed by bytes. The first
client frame is the exact public C2 reply. Subsequent frames carry only the C2
memory-BIO TLS byte stream; empty frames poll while users compare. The server
answers one frame per request. It never parses an action envelope.

## Durable completion, network loss and restart

Perfect distributed atomicity is not claimed. C4.1 adds C2 **confirmation
receipts**, not an alternative enrollment path. After the existing authenticated
TLS comparison passes the local human handler, the existing C2 key signs the
canonical object:

```
{protocol: "olive-pairing-completion/1", session_id,
 transcript: SHA256(canonical([offer, reply])).hex(), device_id,
 confirmed_before: offer.expires_at}
```

The local receipt is durably stored **before** transmission. In V2 only, the
original TLS application confirmation (`OLIVE-CONFIRM/1:` plus transcript binding)
is followed by newline, the 88-character base64 Ed25519 signature, and newline.
Receipts normally travel inside the same exact-identity C2 TLS session. V1's
confirmation bytes and completion behavior are unchanged.

A repository transaction commits trust only after the local record and a verified
peer receipt reference the identical original offer/reply transcript. Every
receipt has a distinct signer; each signature is verified against that
transcript's original identity. Local confirmation cannot be imported from a
remote payload: the exact local receipt must already exist in the local journal.
Both records therefore prove actual confirmation, including when the peer's last
socket write or acknowledgement is lost. Repeated completion returns the same
existing binding and rechecks that it is still paired, never resurrecting revoked
trust or changing permissions.

If one desktop commits and the other loses the final receipt, both can open
**Pairing completion** in Devices, copy their public completion codes, and import
them through **Pair device**. Exchange codes in both directions if needed. A code
contains the original public transcript and available signed receipts, never a
private key or comparison value. Confirmation evidence remains durable until explicit cancellation or revocation;
there is no deadline that could permanently strand a one-sided committed record. A desktop with no saved local confirmation cannot recover,
even with a complete code from another desktop. Altered transcripts, signatures,
unknown sessions, cancellation, failure, expiry or revocation fail closed.

This manual bounded reconciliation is deliberate: it needs no permanent listener,
no automatic reopening after restart, no C3 exception for an unpaired identity,
and no weaker trust decision. The same local import route verifies the signed
completion exchange. It requires no active network listener. A network drop after
both receipts were stored is finalized locally; otherwise the saved code exchange
recovers the missing receipt. A power loss between receipt storage and local
commit leaves a recoverable journal. A power loss before local confirmation has
no recovery authority. Pre-confirmation TLS sessions never resume after restart.

The additive `pairing_completion_v1` table stores only public transcript and
receipts, behind `PairingCompletion`/repository transactions. Existing schema-v2
records and tables remain unchanged. The existing non-evicted, 10,000-session
replay ledger remains authoritative and bounds journal row count. Old profiles
are neither moved nor overwritten. No ephemeral TLS secrets are persisted.

## Bounds and lifecycle

| Resource | Bound |
| --- | --- |
| Active desktop pairing sessions | 1 per service |
| Accepted sockets being processed | 1; listen backlog 2 |
| Accepted attempts per offer | 12, including malformed attempts |
| Public offer/reply | 4,096 bytes, strict duplicate-free JSON |
| TLS carrier frame | 32,768 bytes |
| Carrier receive budget | 262,144 bytes / 3,000 frames |
| C2 TLS receive budget | Existing 131,072 bytes |
| Handshake deadline | 5 seconds |
| Idle read/write deadline | 2 seconds; header and body separately bounded |
| Ceremony lifetime | 120 seconds, wall and monotonic clocks |
| Confirmation application data | Exact confirmation plus 90 receipt bytes |
| Imported completion code | 12,288 bytes |
| Completion recovery | One explicit bounded code import; no recovery listener |

The listener is created only by explicit local pairing intent, bound to one
selected numeric interface, never `0.0.0.0`/all interfaces. It closes on success,
cancel, expiry, failure, disable and application shutdown. Cleanup interrupts
owned sockets and joins its worker; a worker that has not stopped prevents a new
session from reusing its owner. An idle/malformed peer can delay servicing by a
bounded read deadline, not indefinitely. A valid attacker who connects first can
occupy the ceremony until local cancel/expiry, but cannot win trust. Create a new
offer after rejecting that candidate. Network polling does not extend lifetime.

The original ceremony deadline is checked at protocol boundaries, including
confirmation storage. A blocked read/write may delay socket teardown by its
bounded I/O deadline. Durable recovery evidence does not extend pre-confirmation pairing or listener
lifetime. Both original confirmations must have occurred within the ceremony.

No firewall settings change. Loopback acceptance requires no firewall changes.
If a private LAN firewall blocks the temporary port, the UI suggests checking the
selected network and allowing OLIVE for that private-network session. It never
opens a permanent port range or uses C3/Ollama/Studio as a workaround.

Activity records bounded session/device IDs, times and state categories only.
No QR payload, comparison, certificate, signature, private key or peer content is
logged. Peer disconnect/cancel cannot always be distinguished after a lost
connection; the UI reports an interruption rather than inventing an authenticated
reason. A local mismatch has its own failure message.

## Acceptance and limitations

`tests.test_connect_desktop_pairing` runs ordinary services and C4 facades, plus
three independent spawned desktop processes with isolated synthetic vaults and
profiles. It exercises real loopback offer/reply/TLS, equal comparisons, waiting
on one confirmation, Off permissions, listener cleanup, subsequent C3 ping after
explicit local permission, and live revocation. The hostile third process copies
an offer, uses the same display name and joins first; it gains no trust. Tests
also cover malformed attempts followed by legitimate pairing, endpoint rejection,
redirection, receipt tampering, cancellation, expiry, dropped completion,
restart and idempotent recovery. Existing C2 split-handshake MITM tests continue
to verify different exporter comparisons and failed mismatched confirmation.

`desktop/tests/e2e/connect.spec.ts` uses the actual Electron Devices workspace and
a second ordinary desktop service in an isolated process. Its fixture control
pipe supplies local user actions only; it no longer pumps C2 TLS bytes. It covers
QR, pasted responder offer, candidate/comparison, one-sided waiting, completion,
Off permissions, expiry, cancel, mismatch and subsequent C3/Ask/revocation.
Portable CI includes the new process suite without mDNS, KWallet, GPU, Ollama,
Internet or KDE. Real host KWallet/mDNS and physical two-machine firewall testing
remain separate; native Windows behavior is not certified by a Linux run.

Known limitation: completion after loss/restart can require manually exchanging
public completion codes. Imports are bounded by message size and one local
transaction, with no persistent or automatically reopened recovery listener.
Confirmation evidence remains available so a one-sided committed record is never
stranded by an arbitrary recovery deadline. Explicit cancellation/revocation
remains authoritative; it intentionally prevents reconciliation. No sync, Mobile, capability expansion, release,
push or merge is included.

## Recorded local verification

| Check | Result |
| --- | --- |
| Full Python suite | 966 total: **958 passed**, 8 platform skips |
| Portable Connect C1–C4.1 suite | **112 passed**; ordinary three-process acceptance included |
| Unchanged C2 synthetic tests | **36 passed**, included above |
| Frontend unit tests | **40 passed**, 13 files |
| TypeScript, ESLint, renderer/Electron production build | Passed |
| Original C4 Linux desktop acceptance set | **9 passed**: GO, two Devices cases, Linux auto/Wayland, reminder restart, two Studio cases, media |
| Repository-source compilation | Passed |
| Exact whole-tree `python -m compileall -q .` | Existing ignored PySide6 Android Jinja template is not Python; this command is not marked passed |
| Diff/branding/secrets/user-data review | Passed |

Python used the existing project virtual environment and installed .NET toolchain
with `DOTNET_ROOT` configured. Without that setting, the unrelated OmniSharp test
exited during initialization; the correctly configured full rerun passed. An
extra `olive-core.spec.ts` probe hardcodes a Windows Python executable and is not
part of the portable/Linux acceptance set; it was left unchanged. The existing
26-object Python shutdown GC warning remains. No physical LAN, Windows host,
GitHub runner, KWallet or mDNS pass is inferred from these local results.

Reproduce the portable suite using the command in
`.github/workflows/connect-portable.yml`. Run the actual Devices acceptance with
`npx playwright test connect.spec.ts` from `desktop` after building. The original
nine-case regression command is `npx playwright test browser.spec.ts
connect.spec.ts linux-l1.spec.ts linux-l3.spec.ts studio.spec.ts media.spec.ts`.
Its Studio selector also includes `m2-studio.spec.ts`.

Local logs are `/tmp/olive-c41-python-verified.log`,
`/tmp/olive-c41-portable.log`, `/tmp/olive-c41-nine-desktop.log`,
`/tmp/olive-c41-ui-last.log`, `/tmp/olive-c41-frontend-final.log`,
`/tmp/olive-c41-build-last.log` and `/tmp/olive-c41-compile.log`.
