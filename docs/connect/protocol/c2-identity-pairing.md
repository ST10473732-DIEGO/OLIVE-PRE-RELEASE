# OLIVE Connect C2 — cryptographic identity and explicit pairing

C2 adds vault-backed device keys and mutual TLS 1.3 pairing through in-memory
buffers. It opens **no sockets** and provides **no authenticated action transport**.
The existing desktop owns and closes the pairing service. No UI, IPC route,
model tool, camera permission or background discovery worker was added.

## Protocol choice and dependencies

- `cryptography >=50.0.1,<51`: Ed25519 key generation/signatures, X.509 and SHA-256.
- `pyOpenSSL >=26.0,<27`: OpenSSL TLS 1.3, in-memory key/certificate loading,
  memory BIOs and the standard TLS exporter. Tested versions: 50.0.1 and 26.4.0.
- Existing `CredentialVault`: SecretStorage/KWallet on Linux; Windows Credential
  Manager with the preserved profile namespace and UTF-16LE contract on Windows.

TLS 1.3 was selected because its certificate-based mutual authentication,
ephemeral key agreement, transcript authentication and authenticated record
protection are implemented together by OpenSSL. It also gives C3 an established
transport rather than requiring an OLIVE encryption protocol. Noise was considered
but would add a different handshake/transport dependency and lifecycle to maintain;
raw Ed25519 plus X25519 was rejected because assembling them into a handshake
would require designing security-critical protocol details ourselves.

Both sides require certificates, pin the exact candidate certificate as the only
trust anchor, and retain OpenSSL verification. There is no accept-any-certificate
callback, public CA fallback or hostname-based trust. TLS is restricted to 1.3;
session caching and stateless tickets are disabled, each attempt gets a fresh
context, and no resumption or early-data API is used. OpenSSL versions can differ
in whether they emit unusable stateful tickets with this configuration; C2 neither
retains nor accepts resumable sessions. See the
[OpenSSL ticket option semantics](https://docs.openssl.org/3.5/man3/SSL_CTX_set_options/).
Fresh full handshakes use ephemeral agreement and OpenSSL's negotiated TLS 1.3
AEAD cipher suite. CertificateVerify and Finished authenticate the TLS transcript
and possession of both Ed25519 keys. Self-signature alone does **not** establish
that a key belongs to the device the user intended.

References: [TLS 1.3, RFC 8446](https://www.rfc-editor.org/rfc/rfc8446.html),
[pyOpenSSL memory BIO and exporter APIs](https://www.pyopenssl.org/en/stable/api/ssl.html),
[cryptography Ed25519 API](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/).

## Device identity and storage

The C1 UUID remains the stable `device_id`. Public identity contains that UUID,
`algorithm=olive-ed25519-x509/1`, `key_version=1`, creation time and a base64 DER
self-signed Ed25519 certificate. Its subject binds the UUID, not a display name.
Display name, account, IP and hostname cannot change or authenticate a key.
Certificate validity is ten years, with five minutes of initial clock tolerance;
certificate renewal is not implemented and TLS still checks certificate validity.

`DeviceKeyStore` is the shared adapter over the existing OS vault. The only new
credential reference is `connect-identity-v1`, under the existing profile-scoped
namespace. It stores the 32-byte Ed25519 private seed in a versioned representation
inside the vault. No private-key file, settings field, SQLite column, temporary
PEM file, audit payload or frontend key state exists. OpenSSL receives the key
in memory. The Linux backend still insists on an encrypted Secret Service session.
Missing, locked, duplicate or inaccessible secure entries fail closed.

Identity provisioning is **lazy**, on the first `cryptographic_identity()` or
pairing call. Ordinary local application startup does not contact the vault and
is not broken by a locked wallet. C1 metadata is not presented as a cryptographic
identity until provisioning succeeds. SQLite first reserves the public identity
in `pending`, then the vault writes and verifies its matching private key, then
SQLite marks it `ready`. The database serializes competing initializers. An
interrupted reservation requires recovery; it cannot overwrite a key. An existing
vault slot with a missing database is also refused. Once ready, every load must
match the persisted public key. Loss/corruption does not generate a replacement.

Schema 1 upgrades additively to schema 2: public-key provisioning and pairing
ledger tables, plus optional public identity/fingerprint fields in paired records.
Existing local metadata, permissions, request ledger, audit and revocation records
remain unchanged. C1 fixture records receive no cryptographic trust by migration.
Unknown schema versions fail. No legacy profile is copied, deleted or overwritten.

Rotation, recovery, certificate renewal, profile cloning, secure-store restoration
and database rollback recovery are future work. Do not clone a profile to enroll
a second installation. Reinstallation recovery must not assume that copied metadata
proves key possession.

## Fingerprint and human comparison

The public fingerprint is `C2/1:` followed by all 32 SHA-256 bytes in uppercase
colon-separated hex. Its canonical input contains algorithm, key version, UUID
and the raw public key. It is deterministic, contains no secret and is independent
of display metadata or certificate renewal. Public identity validation checks the
certificate self-signature, Ed25519 key type, UUID subject and creation-time binding.
It becomes an authenticated candidate only after successful TLS proof of possession.

The **session comparison value** is separate from that long-term fingerprint.
It is the full 256-bit TLS 1.3 exporter output using label
`EXPORTER-OLIVE-PAIRING-v1` and a SHA-256 context over the canonical ordered offer
and reply. Thus it binds both identities, roles, protocol, session UUID and times
in addition to the TLS handshake. This value is used only for human comparison,
never reused as an encryption key or written to storage. C2 deliberately uses a
full comparison value rather than claiming security for a novel six-digit SAS.
A shorter usability scheme requires a separate reviewed protocol decision.

Both humans must compare the **same session value on both intended devices**.
Comparing the different long-term peer fingerprints to one another is not the
ceremony. The preview includes authenticated candidate identity, fingerprint,
expiry, state and comparison value. The local `confirm` method requires the value
observed on the other device; a mismatch fails and destroys the session. It is
not reachable from remote messages or a model tool. As with any confirmation UI,
trusted local software cannot prove that a human actually performed the comparison.
No live encrypted connection is claimed after the fixture finishes.

## Offer and session lifecycle

`create_offer()` represents explicit local intent. QR payloads are UTF-8 JSON
bytes, at most 4,096 bytes, with exactly:

- `protocol`: `olive-pairing-tls13/1`;
- `session_id`: canonical UUID;
- `created_at` and `expires_at`: integer Unix seconds;
- `identity`: the strict public identity described above.

No discovery address is needed. No private/ephemeral key, permission, account,
credential, path, command or content is accepted. Duplicate/unknown fields,
nonfinite numbers, invalid encodings, malformed certificates, unsupported versions,
boolean timestamps and excessive lifetimes are rejected. `encode_offer` validates
through the same decoder. The reply has the same session/time fields with the
responder's public identity. The initiator fixes one candidate and rejects another
reply, including changed content under the same session ID.

The offer lifetime is 120 seconds. Each process also installs a monotonic deadline;
wall-clock rollback cannot extend an active session. Wall time is necessary for
cross-device offer decoding, with five seconds of future-clock tolerance. Restart
never resumes an unfinished session. The durable ledger consumes each UUID before
TLS starts; failed, cancelled or completed offers remain consumed across restarts.
There is no automatic re-pairing. A copied expired QR cannot recreate a session.

States are `offer_ready`, `peer_received`, `fingerprint_pending`, `confirmed`,
`completed`, `cancelled`, `expired`, `failed`. Each active in-memory session holds
its local offer/reference, remote candidate, deadline, TLS context, transcript
binding and separate local/peer confirmation flags. The fixture passes TLS bytes
between `exchange` calls; no networking abstraction creates a socket. TLS input
is bounded to 32 KiB per call and 128 KiB per session. At most 32 sessions are active;
terminal memory entries are pruned when a new session starts. The durable ledger
has a fail-closed 10,000-entry limit, with no unsafe replay eviction.

Local confirmation sends one fixed confirmation message over the authenticated
TLS record layer, bound to the offer/reply digest. Both local intent and receipt
of the peer's authenticated confirmation are required before `complete`. TLS
record authentication and sequence numbers reject changed or replayed confirmations.
There is no unencrypted peer-confirmed boolean or remote permission field.

Completion atomically binds the peer public identity/fingerprint and paired state
in the repository, records the completed session and writes a bounded audit event.
Repeated local completion is idempotent even after restart; changed completion
content is rejected and revocation is rechecked. This retrieves a prior result,
it does not reactivate the handshake. All wire/session reuse is rejected.

Cancellation/expiry/failure discard candidate metadata and drop the TLS object.
There is no pre-confirmation paired record. Expiry is checked on every operation;
`expire()` also provides explicit idle cleanup, and service shutdown cancels all
unfinished sessions. There is no background timer: a completely idle in-process
session is released on cleanup, the next operation or shutdown. OpenSSL owns the
ephemeral key lifecycle; Python object/allocator memory cannot promise complete
zeroization. Private identity objects are not cached outside an active TLS context.

## Authority, permissions and revocation

Pairing defaults to **all capabilities Off**, with no advertised support inferred
from the peer. This is intentionally more conservative than the example profile:
C1 has only three fixed fixture operations. The existing local permission setter
can select an initial policy after completion. Pairing messages cannot call it.
Unsupported/platform-forbidden capabilities remain unavailable even if a local
permission rule says Allow. Ask still needs a separate operation-specific approval.

A C2 peer has `connection_kind=none` and stays offline. It cannot use the C1 fixture
identity shortcut, even in a fixture-enabled service. `require_paired_identity`
checks a persisted binding and revocation; **it is not proof of possession** and
is not an action-dispatch API. C3 must authenticate its live channel, bind the peer,
and recheck current trust and permission at dispatch. C1's explicit synthetic
fixture transport and strict request/replay tests remain unchanged.

Same UUID with a different key is rejected. Existing identities, including revoked
ones, cannot be overwritten by another pairing. Re-pairing a revoked identity is
**not supported in C2**, even with fresh offers. Revocation also blocks the same
public key under another UUID. A new key and UUID need fresh explicit intent and
human confirmation; C2 cannot identify a physical device that replaces both.
Revocation does not rely on display name, IP, account or connection state.

There is no distributed atomic commit: after both confirmations, one repository
can complete while the other process crashes. This does not bypass either user's
confirmation and cannot grant action access in C2. Resumable distributed completion
and reconciliation belong to future transport work.

Audit records use opaque device/session IDs, timestamp and fixed event/result
labels: created, cancelled, expired, failed, completed, revoked. They contain no
certificate, QR payload, comparison value, private key, credential or user content.
The existing 1,000-entry audit bound is retained.

## Threat model

| Threat | Classification | Mechanism / limit |
| --- | --- | --- |
| Copied old QR | Mitigated | Expiry, persistent consumed UUID, no handshake resumption after restart |
| Offer/key substitution | Mitigated with correct human comparison | Mutual TLS pins, proof of possession and different exporter value; mismatch never completes |
| Attacker on same Wi-Fi | Mitigated in C2 | No listener/discovery; hostile transport handling and denial-of-service beyond bounded fixture inputs remain C3 work |
| Known GitHub/OLIVE account | Mitigated | Account/username fields have no pairing role and are rejected in offers |
| Display-name spoofing | Mitigated with correct human comparison | Names are local labels; keys and TLS-bound comparison establish the candidate |
| IP/hostname spoofing | Mitigated | Neither is an identity/trust input; neither is accepted in payloads |
| Old/revoked device | Mitigated for known keys | Persistent tombstone, no un-revoke, key aliases rejected; genuinely new keys need human pairing |
| Malformed messages | Mitigated within tested contract | Strict bounded JSON/certificate decoding, fixed TLS version, byte budgets and generic errors |
| Offer / TLS-record / completion replay | Mitigated | Durable session ledger, TLS sequence authentication, idempotent local completion with changed-content rejection |
| Pairing screenshot stolen before expiry | Partially mitigated | Screenshot contains public material, not authority; attacker can consume/occupy an attempt, but needs both human confirmations with matching values |
| User confirms an attacker's device or skips comparison | Not mitigated | Human ceremony and trusted local UI are essential; no account-based substitute |
| Compromised OS/current-user process | Deferred | Vault does not isolate against every same-user process; local caller can drive backend methods; no endpoint-compromise claim |
| Profile/database rollback or cloning | Deferred | No anti-rollback hardware counter or recovery system; restoration requires explicit future design |

C2 does not claim an independently audited pairing protocol, endpoint-compromise
protection, universal memory erasure, anonymity or safety when users compare only
names. TLS forward secrecy protects past ephemeral sessions against later identity
key disclosure under TLS assumptions; it does not protect a currently compromised
endpoint. Real transport denial-of-service, discovery poisoning and operational
certificate renewal still require C3 design/review.

## Validation and reproduction

Portable tests use controlled clocks and synthetic vaults but real secure random
Ed25519 keys, real OpenSSL TLS handshakes, real exporters and real encrypted
confirmations. No crypto methods are mocked. Synthetic second devices own separate
profiles, keys and state. Tests include split MITM handshakes, wrong keys, transcript
changes, TLS corruption/replay, missing and malformed keys, interruption/orphaned
storage, permissions, revocation, migration, privacy and socket prohibition.

```bash
.venv/bin/python -m unittest tests.test_connect tests.test_connect_pairing -v
.venv/bin/python scripts/check_connect_vault.py
```

The second command is opt-in real OS vault acceptance. It creates two temporary
profile namespaces and removes their synthetic vault entries afterward. It never
uses personal provider credentials, model downloads, GPU or live Mail.

Implementation commit: `ff3ccbb`, on `feature/olive-connect-c2`, based on C1
`2ef2461` and `a37a6d7`. Final verification on the CachyOS host:

| Check | Result |
| --- | --- |
| Full portable Python suite | 913 total: **905 passed**, 8 explicit Windows-only skips, zero failures/errors |
| Dedicated Connect tests, included above | **59 passed**: all 23 C1 tests plus 36 C2 tests |
| Frontend unit tests | **33 passed** in 12 files |
| TypeScript / ESLint / production renderer and Electron build | Passed |
| Repository source compilation | Passed |
| Exact whole-tree `python -m compileall -q .` | Existing ignored PySide6 Android Jinja `__init__.tmpl.py` syntax failure; not marked passed |
| Installed Linux CI-equivalent offscreen Qt/WebEngine and Studio imports | Passed |
| Dependency consistency / launcher syntax / diff review | Passed |
| Real KWallet synthetic acceptance | Passed: creation, restart, two-sided TLS pairing, revocation; synthetic slots removed |
| Shutdown | Pairing context cleanup tests passed; no Connect socket, worker or child process is created |

The final complete Python run is `/tmp/olive-c2-python-final.log`; dedicated tests,
compile and build logs are `/tmp/olive-c2-connect-final.log`,
`/tmp/olive-c2-compile.log` and `/tmp/olive-c2-build.log`. Logs are not committed.
The existing full-suite warning about 26 uncollectable Python objects remains;
it is not classified as a new Connect shutdown failure. The earlier full runs
also passed; the final total comes from one complete run after the last code change.

These checks exercise the installed portable CI dependencies and commands, not a
fresh GitHub runner or a dependency reinstall. Installing the missing pyOpenSSL
package required package-index access during development; pairing and tests need
no external service/network, cloud account, model download or GPU.

Native Windows vault acceptance cannot run on this Linux host; the existing Windows-only tests
are retained, and C2 adds a portable mocked Credential Manager contract test.
No native GUI/GPU L3 re-certification is inferred from backend/portable tests.

## Explicitly not implemented / next phase

No real LAN discovery, real network transport, iPhone app, camera scanner, relay,
remote AI, remote Studio, file transfer, sync, remote control, Devices page or
OLIVE OS work is included. There is no new public or loopback listener, and no
Ollama, Studio or filesystem exposure.

**C3 = local discovery + authenticated encrypted local transport.** Use established
TLS peer authentication with the paired public identity, keeping the trust,
capability, permission and operation-confirmation layers distinct. C2 exporter
comparison values are not reusable transport keys.
