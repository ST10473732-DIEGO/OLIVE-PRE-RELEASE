# OLIVE Connect C1 — desktop device foundation

C1 adds a backend device service and deterministic in-process fixture transport.
The ordinary desktop creates its local identity, with fixture mode **disabled**.
No Connect socket, listener, discovery worker, model call or remote tool endpoint
is created. OLIVE Connect is independent of OLIVE OS and OLIVE Mobile.

## Architecture and integration

`olive/connect/` contains contracts, validated metadata models, repository,
transport seams and `DesktopDeviceService`. `ServiceContainer.connect` owns the
service and closes it in the existing shutdown `finally` path. It uses the
container's already-resolved profile, including explicit configured paths,
Windows defaults, Linux XDG paths and existing legacy profile selection. No
platform-specific schema or migration of existing user profiles is introduced.
The shared code uses Python's standard library and existing permission types;
it does not import DBus, KWallet, DPAPI, Win32 or Wayland.

The existing CapabilityRouter, Agent ToolExecutor, filesystem tool host, Studio
controller, approval identity and ActionPreview paths were inspected. Connect
cannot dispatch to any of them in C1. Its fixed operations have no access to the
service graph, vault, filesystem broker or generic tool registry. Existing
Desktop Control, GO, Mail, model and external communication policies are
unchanged. Future consequential adapters must retain those services' own
permission, confirmation, observation and verification boundaries.

## Identity and repository

`DeviceIdentity` contains a random UUID4 `device_id`, editable `display_name`,
`platform`, `device_class`, UTC Unix-second `created_at`, allowlisted
`public_identity_metadata` (OS name only), structured `capabilities`, and positive
`revision`. The default name is “This device”; class defaults to desktop without
hardware probing. Renaming increments revision and preserves identity. Hostname,
IP, username and hardware serials are not identity inputs.

`DeviceRepository` stores version 1 in `connect/devices.sqlite3` beneath the
profile. SQLite transactions and a unique local-device index serialize first
creation across repository instances. Unknown schema versions or malformed
records fail closed. Version 0 initializes the new tables; future versions need
explicit migrations. Existing application stores are untouched. Do not copy the
identity database to enroll another installation: profile cloning/restore needs
an explicit future identity-reset procedure. Connect is not added to backup or
record-sync exports.

`PairedDevice` contains device ID, name, platform/class, trust state, paired time,
last seen, connection state/kind, advertised capabilities, permission rules,
revision and revocation time. There are no password, token or private-key fields;
unknown fields fail validation. Synthetic enrollment is named `enroll_fixture`,
requires explicit constructor fixture mode and records `connection_kind=fixture`.
It is not cryptographic pairing, and is not exposed in IPC or the UI.

Trust states are `unpaired`, `pairing`, `paired`, `revoked`. Connection states are
independently `offline`, `discovering`, `connecting`, `online`; future connection
kinds are represented without implementing their transports. Fixture records
remain offline, even when an in-process call succeeds. Last-seen and revision
advance on successful execution. Revocation clears permissions and records a
permanent tombstone; there is no re-pair/unrevoke API. Stale requests cannot
update trust or remove that tombstone.

## Capability and permission boundaries

Machine identifiers include chat, tasks, calendar, reminders, notifications,
files.receive, files.shared, filesystem.full, studio.view, studio.run,
models.remote, apps.launch, terminal, desktop_control and software.install.
Vocabulary membership does not mean implementation or authorization.

Each capability metadata entry separates `supported` from `policy_disabled`.
A local policy lock overrides permission. Peer advertisements never grant access.
Only three capabilities have C1 implementations:

| Capability | Operation | Fixed read-only result |
| --- | --- | --- |
| `connect.ping` | `ping` | `pong: true` |
| `device.status` | `read` | Core available; fixture transport; encryption false |
| `chat.metadata.read` | `read` | Content and inference access false |

These are fixtures, not chat history access or inference. All other capabilities
are unavailable, including when locally marked Allow.

Connect reuses `PermissionDecision` and `PermissionService.evaluate_device`:
Allow=`allow`, Ask=`ask`, Off=`deny`. A missing grant is Off. Rules are stored per
device with capability and optional exact opaque scope. More specific scopes
can override a device-wide rule; equal-scope conflicts select Deny then Ask.
C1 operations request no target, so a scoped Allow cannot authorize an unscoped
request. Local filesystem/application scopes and remembered local tool approvals
are never imported as remote authority.

The backend has local metadata, permission read/update and revocation methods.
No transport operation or bridge route can call setters. There is no Devices UI
yet; its future adapter must use the existing guarded local settings flow.
Ask fails with `confirmation_required`: C1 has no remote confirmation flow,
boolean approval flag or reusable remote approval token. Later approval handling
must bind source, request, exact operation/arguments, scope and revision and
recheck current policy/revocation using the existing confirmation architecture.

## Protocol and transport

Protocol version is exactly `olive-connect/1`. Requests are UTF-8 JSON bytes with
these exact required fields (no optional/unknown fields in v1):

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "protocol_version": "olive-connect/1",
  "source_device_id": "550e8400-e29b-41d4-a716-446655440001",
  "target_device_id": "550e8400-e29b-41d4-a716-446655440002",
  "capability": "connect.ping",
  "operation": "ping",
  "arguments": {},
  "timestamp": 1800000000,
  "expires_at": 1800000060
}
```

The maximum encoded request is 16,384 bytes, checked before JSON parsing or
capability logic. UUIDs must use canonical lowercase spelling. Duplicate JSON
keys, non-finite numbers, malformed UTF-8/JSON, wrong types (including boolean
timestamps), unknown fields/capabilities and other protocol versions fail closed.
The lifetime is at most 120 seconds, with five seconds of future-clock tolerance;
expired requests fail even if their result is cached. Only ping accepts an
optional string `nonce` of at most 128 characters. It is untrusted, ignored,
never echoed or stored. All other arguments and operations are rejected. Large
attachments require the future separate transfer mechanism.

Responses are bounded fixed JSON-compatible dictionaries with protocol version,
request ID, state and either the fixed result or a fixed error code. No Python
object serialization, exception text, tool names chosen by the sender, file
contents, messages or credentials are returned.

`ConnectTransport` defines `send`, `receive`, `close`, `status`.
`InProcessFixtureTransport` binds a synthetic peer at local construction, holds
at most 32 response objects and clears them on close. An envelope cannot choose
that bound peer. This is **not authentication** against an adversarial local
Python caller. Production mode refuses fixture construction and processing.
`DiscoveryProvider` is a protocol seam only, with no implementation or background
scanning. No crypto is implemented; future private keys must use a suitable
extension of the existing secure credential/key abstraction, never these tables.

C1 flow: bound fixture peer → bounded strict decode → peer/source match → current
pairing/revocation → target/freshness → operation schema/local capability policy →
current device permission → durable claim → recheck authority → fixed read-only
operation → result/activity. Full wire validation necessarily precedes use of
untrusted envelope fields. C2/C3 must replace fixture binding with authenticated
transport identity before accepting real remote messages.

## Replay, revocation and activity

Replay keys are `(source_device_id, request_id)`; canonical whole-envelope SHA-256
fingerprints detect changed arguments, target, operation or freshness fields.
Identical requests return the stored result after current authority checks.
Changed requests fail. Different peers have separate request namespaces.

A claim is committed before execution. The second transaction rechecks authority
and serializes execution/result storage against revocation and permission writes.
A crash or handler error leaves a claim with no response; duplicates return
`request_indeterminate`, never execute again. This favors at-most-once execution
over guaranteed delivery and does not claim exactly-once side effects. C1 has no
consequential handlers. Revocation is authoritative before cached-result access;
a revoke waits for an already-running fixed read-only transaction, then denies
all subsequent requests. Future long-running work requires cancellation and
additional execution boundaries.

The replay ledger has a 10,000-request ceiling and rejects new requests at capacity
without evicting claims. A future authenticated transport needs an explicit
retention/epoch and resource-budget design. Activity retains the latest 1,000
records with source device, request ID, locally recognized capability, UTC receipt
time and fixed result state only. Malformed envelopes use null request/capability
when validation cannot establish them; the fixture peer remains attributable.
Replay storage contains fingerprints and fixed fixture results, never arguments.
No remote message body, credential, file content or raw exception is logged.

## Sync foundation

The existing `olive/sync/contracts.py` remains the selective record boundary:
`record_id` is stable, `collection` is kind, `device_id` identifies the updating
device, and revision/base_revision provide ancestry. C1 adds `updated_at` UTC
seconds and `payload_version=1`. Additive defaults preserve old constructor and
serialized records (`updated_at=0` means unknown legacy time); the original
content hash remains compatible. Future persisted migrations must retain sources.
Existing conflict handling, collection allowlist, 256 KB bounds, depth limits and
credential/cookie/live-database/execution exclusions remain. The earlier
`DeviceGrant` contract is not pairing or a Connect authorization path. No records
or SQLite databases are actually synchronized.

## Deferred sequence

- C2: cryptographic identity and pairing.
- C3: local discovery and authenticated encrypted local transport.
- C4: per-device permission UX.
- C5: structured record sync.
- C6: file transfer.
- C7: remote AI.
- C8: remote Studio.
- C9: OLIVE Mobile.
- C10: direct remote / relay.

There is no listener (public or loopback), LAN exposure, Internet dependency,
remote terminal/control/install/communication, file access, live inference,
Studio execution, mobile application, OLIVE OS work or workspace redesign.

## Validation

Dedicated tests cover persistence/rename/restart, synthetic enrollment, trust and
capability locks, Off/Ask, untrusted content, protocol bounds and malformed types,
spoofing, all excluded sensitive operations, attribution/privacy, durable replay,
changed duplicates, concurrent repository instances, interrupted execution,
revocation, expiry, queue bounds, shutdown and sync compatibility. Fixtures use
owned temporary directories and no model, GPU, wallet or external network.

Final Linux verification:

| Check | Result |
| --- | --- |
| Complete portable Python suite | 877 total: 869 passed, 8 Windows-only skips, no failures |
| Dedicated Connect tests (included above) | 23 passed |
| Frontend tests | 33 passed in 12 files |
| TypeScript / ESLint / production build | Passed |
| Repository-source compilation | Passed |
| Exact whole-tree `python -m compileall -q .` | Existing ignored PySide6 Android Jinja template fails syntax compilation |
| Linux CI-equivalent offscreen Qt/WebEngine and Studio provider imports | Passed |
| Dependency consistency / launcher syntax / diff review | Passed |

The exact compile failure is the same third-party `__init__.tmpl.py` limitation
documented in L1–L3; it is not marked passed. Source compilation excludes ignored
environments/toolchains. The existing Python shutdown warning about 26
uncollectable objects remains. The first sandboxed full run stalled in an
existing threaded fixture and was interrupted; the final complete run used host
subprocess access with a fresh temporary profile. Local logs are
`/tmp/olive-c1-python-final.log`, `/tmp/olive-c1-compile.log` and
`/tmp/olive-c1-build.log`. They are not committed.

This exercises the installed Linux portable CI runtime and test/build commands;
it does not claim a fresh GitHub runner execution or reinstall dependencies.
Native Windows, physical CachyOS GUI/GPU, wallet, live Mail and model acceptance
were not rerun for this backend-only change. Their existing platform paths remain
unchanged and portable regressions pass; native release certification remains a
separate check. No model or runtime download was performed.
