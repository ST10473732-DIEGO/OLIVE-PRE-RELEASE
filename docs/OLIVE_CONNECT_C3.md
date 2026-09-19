# OLIVE Connect C3 — local discovery and authenticated LAN transport

C3 adds the first real Connect listener. It is **disabled by default**, including
ordinary desktop startup. It communicates only between explicitly paired C2
identities, on an explicitly selected local interface. It exposes three existing
fixed read-only capabilities, not the application service graph or tool registry.
There is no schema migration, identity rotation, permission migration or new key.

## Enabling and inspecting the developer service

The existing `ServiceContainer.connect` owns `DesktopDeviceService`. Trusted local
Python code can inspect `olive.connect.discovery.interfaces()`, then explicitly
call `connect.enable_network(selected_address, port=0)`. No environment variable,
update, model output, advertisement or remote message enables networking. This
setting is intentionally session-only; C4 will provide the Devices settings UI.

The returned `LocalNetwork` exposes:

- `discovery.nearby()`: untrusted endpoints, each with `state=discovered`.
- `connect_discovered(paired_device_id, instance)`: select an advertised endpoint
  for an already paired identity; discovery never supplies the expected identity.
- `connect(peer, numeric_address, port, retries=0)`: explicit local endpoint flow
  and portable tests without multicast. No DNS hostname resolution or scanning.
- `status(peer)`: transient connection state, fixed error category, `connection`
  (`local` only online), authenticated encryption status and last measured latency.
- `Channel.request(encoded_C1_envelope)`: bounded synchronous request/response.
- `disconnect(peer)`: closes the channel and removes local reconnect intent.
- `connect.disable_network()`: withdraws discovery, stops the listener, reconnect
  worker and channels. Ordinary service/container shutdown calls it too.

`paired_devices()` remains persisted trust metadata; its historical connection
fields are not live telemetry. Combine it with `network.status(peer)` for live
status. Nothing persists an online channel across restart. A discovered endpoint
is not a paired device, and a paired offline device is not online. Unknown
advertisements never create records or change permissions. No polished UI is added.

## Discovery and interface policy

Discovery uses **python-zeroconf >=0.151.3,<0.152**, the maintained cross-platform
mDNS/DNS-SD implementation, rather than a custom UDP protocol, Avahi/DBus dependency
or subnet scan. See its [API reference](https://python-zeroconf.readthedocs.io/en/stable/api.html)
and [project](https://github.com/python-zeroconf/python-zeroconf).

Service type: `_olive-connect._tcp.local.`. Each enable creates a new random
instance and `.local.` server label. TXT has exactly `product=OLIVE`, `version=1`.
SRV/A/AAAA contain the selected port/address, necessarily visible for discovery.
There is no device UUID, personal name, permission, capability list, credential,
public certificate, project, model prompt or user content in advertisements.
The directory retains at most 64 entries. Zeroconf owns TTL expiry/removal; our
announcements use 30-second TTLs. Advertisements are separate from persistent
audit, avoiding a disk event per discovery refresh. Malformed/extra TXT fields,
public or off-subnet addresses and invalid ports are ignored. Service names,
addresses, hostnames and TXT fields never select a trust anchor.

`psutil` enumerates active interface addresses/netmasks on Windows and Linux.
There is **no automatic interface selection**. The local caller must select one
exact address from the candidates. Wildcard binds are refused. Candidates permit
IPv4 RFC1918 and loopback, IPv6 loopback and ULA; public addresses and scoped
IPv6 link-local are excluded. Common VPN/container/bridge/virtual adapter names
are filtered. Name filtering cannot reliably classify every custom adapter:
explicit selection must be a reviewed physical LAN or loopback interface. It
is not a network trust heuristic. IPv6 uses the same sockets/protocol; multicast
availability and host interface configuration remain platform dependent.

Inbound and outgoing endpoints must be numeric addresses in the selected subnet.
Connect TCP binds only that address. Outgoing sockets bind the same local address.
Reviewed Zeroconf behavior: its shared mDNS UDP 5353 receive socket uses a wildcard
bind, as is conventional for coexisting multicast responders, while membership
and responder sockets are selected explicitly. OS multicast delivery/firewall rules
can still deliver other traffic to that UDP socket. This does not create a
wildcard Connect TCP listener or make discovery trusted; do not treat the UDP
socket as an interface privacy boundary. The
listener uses an OS-selected port by default; an explicit port fails on collision,
with no reuse-port option, root requirement or alternate public listener.
Interface disappearance fails connections; changing interfaces requires disable
and explicit enable. There is no Internet routing, relay or fallback interface.

## Identity, TLS and certificate lifetime

C2 and C3 now share `tls_identity.identity_context`; C2's single-candidate policy
and tests are preserved. C3 uses the same vault-held Ed25519 key and public X.509
certificate. Explicit enable loads the existing vault identity into service memory;
workers reuse that material to construct fresh contexts without making network
handshakes wait on wallet access. Disable releases the service reference after
workers exit. No private material is written to a file, database or log; Python
and OpenSSL cannot promise allocator-level zeroization. The listener trusts only exact certificates from current paired,
non-revoked records. An outgoing connection trusts only the selected peer's exact
certificate. OpenSSL chain/validity verification must succeed AND DER must match
an allowed certificate at depth zero. No public CA store, hostname trust or
accept-any callback is installed.

Every socket gets a fresh TLS 1.3-only context. Session caching and tickets are
disabled as in C2; no saved session, early data or resumption API is used. Both
sides must present certificates and prove key possession. After the handshake,
Connect maps the actual certificate to a persisted identity and rechecks pairing,
revocation and certificate validity. Both sides exchange a fixed encrypted hello
frame **before** becoming online. This handles TLS 1.3's client-side handshake
completion before the server's client-certificate rejection has been received.
C2 comparison/exporter values are never used as transport keys.

Expired/not-yet-valid certificates fail closed, with local category
`certificate_expired_or_not_yet_valid`. Check the local system clock; if the
certificate expired, renewal/recovery remains future work. Trust records stay
intact. A failed live handshake reports a bounded TLS/connection failure; it can
indicate a changed identity, revoked peer, bad certificate or network failure.
The local caller must check pairing, certificate lifetime and firewall. There is
no automatic accept-changed-key or renewal action, even for the same UUID/name/IP.

## State, collision and reconnect

Local outgoing states are offline → connecting → authenticating → online;
failures become failed/offline with a fixed category. Inbound connections remain
unattributed until their actual TLS identity is verified. Closing immediately
removes online authority and latency. Pairing states are independent.

If two sockets compete, both peers prefer the one initiated by the
lexicographically smaller stable C2 UUID. Same-direction duplicates retain the
existing channel. A sole channel in either direction is valid. Replacing a
competing channel closes it and fails its pending requests; callers never migrate
an authenticated socket or pending authority. A stopped channel cannot win a
collision. Hostname/IP/display name ordering is never involved.

An explicit successful outgoing connection records an in-memory reconnect target.
Ordinary loss allows at most three background attempts with bounded exponential
backoff (approximately 0.5-second initial eligibility, then 1/2/4 seconds).
Success does not refill this budget: a flapping device cannot retry forever.
Explicit `connect(..., retries=N)` also permits 0–3 foreground retries with
0.25/0.5/1-second backoff. Both paths share the connection-attempt budget. Every
retry repeats fresh TLS and current trust checks. Explicit disconnect, revocation
and shutdown cancel reconnect intent. Another explicit local connect can start a
new budget. Discovery returning alone does not reconnect or grant permission.

## Protocol, dispatch and limits

TLS application messages have a six-byte header: unsigned big-endian 32-bit
payload length, unsigned byte framing version `1`, unsigned byte type. Types are
`request=1`, `response=2`, `close=3`, `hello=4`. Hello/close have zero payload;
hello is accepted exactly once during establishment. No raw object RPC, pickle,
marshal, eval or newline framing exists. Unknown versions/types fail closed.

Request payload is the unchanged strict UTF-8 JSON C1 envelope, including
`protocol_version=olive-connect/1`. Response payload is the bounded C1 structured
result/error object. Duplicate JSON keys, invalid numbers/UTF-8, unknown fields,
unknown capabilities and remote approval fields fail validation. Frame length
is checked before allocating its declared body. Fragmentation and multiple frames
per TLS read are handled explicitly.

| Resource | Bound |
| --- | --- |
| Accepted/connecting/authenticated sockets combined | 8 per service |
| TCP listener backlog | 8 (OS controls pending TCP handshake details) |
| Accepted/outgoing attempts combined | 12 per rolling 60 seconds |
| Application messages, including responses | 60 per peer per rolling 60 seconds, across reconnects |
| Peer rate buckets | 256, fail closed at capacity; never evicted to bypass limits |
| Pending outgoing requests / queued writes | 8 each per channel |
| Incoming execution | Serial, one fixed read-only operation per channel |
| Frame payload / C1 envelope | 16,384 bytes |
| TLS application read | 16,384 bytes; partial-frame accumulator below 32,774 bytes |
| Socket connect / TLS handshake / encrypted hello | 3 seconds each |
| Incomplete frame / idle channel | 3 seconds / 60 seconds |
| One framed write | 2 seconds, including all partial writes |
| Local request wait | At most 5 seconds; timeout closes channel |
| Network dispatch database lock wait | 0.25 seconds per transaction |
| Request execution admission | Rechecked at execution, within 5-second monotonic dispatch lifetime |
| Join budgets on shutdown | 4 seconds listener, 4 seconds reconnector, 4 seconds aggregate channels |
| Connection audit event rate | 30 per rolling 60 seconds |
| Durable request ledger / retained activity | Existing 10,000 claims / latest 1,000 events |

Timers use monotonic time except certificate validity and C1 wall-clock freshness.
C1 retains maximum 120-second request lifetime, five-second future tolerance and
expiry checks before cached-result access. Clock synchronization never supplies
identity; wall-clock rollback cannot erase durable claims. No replay eviction is
introduced. Capacity exhaustion is an actionable failure, not silent authority
reset. Kernel TLS/TCP buffers and Zeroconf's DNS cache are library/OS managed;
these application limits do not promise immunity to network-level denial of service.

The channel, not request metadata, supplies authenticated source identity.
Dispatch rechecks exact stored public identity and revocation, strict envelope,
source/target/freshness, safe operation, availability and current permission. A
durable claim commits before execution; a second transaction rechecks authority.
Permission writes/revocation serialize with that execution transaction. Tests
change permission and revoke through the real local setter after claim commit.
The existing fixed service operations remain authoritative; transport duplicates
no action implementation. `device.status` accurately reports local encrypted
transport only on this authenticated path.

Only `connect.ping`, `device.status` and `chat.metadata.read` are available.
The last returns only fixed `content_access=false`, `inference_access=false`.
Initial permissions remain Off. Ask returns `confirmation_required` and executes
nothing: C3 does not introduce a remote approval token or a local approval UI.
Until an operation-specific trusted local approval adapter exists, Ask cannot
succeed. A peer cannot approve itself, and an Allow decision is never cached.

Identical duplicate requests retrieve the existing result after current authority
checks; changed duplicates fail. At most one execution occurs, including after
reconnect/restart. A crash after claim without result leaves the existing
`request_indeterminate` state. There is no exactly-once side-effect claim.
Latency is measured only from a real successful Connect ping round trip, retained
as the last measurement and cleared on disconnect; it is never a mock value.

## Revocation, errors and shutdown

Local revocation first commits the tombstone/clears permissions, then signals all
matching active/connecting sockets. Pending requests fail and no permission cache
survives. Worker checks also observe changes from another repository instance.
A request that already completed its fixed read-only execution transaction may
finish before the revoke transaction; not-yet-authorized work cannot execute.

Wire errors contain fixed categories, never exception text, paths, stack traces,
vault errors, certificate material or request content. TLS/framing/abuse failures
can close the channel without an application response. Locally retained activity
contains opaque peer/request IDs, capability IDs, times and result/event labels.
Connection events include started, authenticated, failed, closed and
revoked_connection_closed. Audit failures emit only a fixed local warning.

Shutdown stops reconnect/acceptance, withdraws mDNS, interrupts sockets, fails
pending futures and joins owned workers. Only a socket's TLS worker performs its
final descriptor close; other threads signal shutdown. This prevents a descriptor
from being recycled while OpenSSL might still access it. A join failure is an
explicit shutdown error, not a false cleanup success. No application worker pool,
model, subprocess or GPU is owned by production Connect networking.

## Firewall and platform boundaries

Acceptance used **loopback only**. No firewall was modified. Same-LAN acceptance
on another physical machine was not performed or required. A deliberately enabled
same-LAN service may need inbound TCP to the selected interface address and the
reported single Connect port, plus mDNS UDP 5353 on that interface/local subnet.
Do not open Ollama's port or Studio IPC, and do not add an all-interface rule.

For a stable explicit port `P`, the exact intended rule scope is inbound TCP
`local-address=selected-address`, `local-port=P`, `remote-address=selected-subnet`,
limited to the OLIVE/Python executable. The discovery exception is UDP local port
5353 to that executable/interface, local-subnet sources, with mDNS multicast
224.0.0.251 (IPv4) or ff02::fb (IPv6) permitted on that interface. Windows Defender
Firewall should additionally restrict the rule to the selected Private profile;
this profile is not authentication. Linux nftables/firewalld rules should match
the chosen input interface/address/subnet and exact TCP port, plus scoped mDNS.
Concrete command syntax depends on the user's actual firewall/backend and selected
port; C3 does not execute or persist any rule. Dynamic ports require a fresh rule
scope or explicit managed port, not a broad permanent port range.

Shared code uses Python sockets/threads, OpenSSL, psutil and Zeroconf. No DBus,
KWallet, DPAPI, Wayland or Win32 dependency enters the transport; those stay behind
C2's existing vault adapter. Synthetic tests work without a vault or KDE. A new
portable CI matrix runs C1/C2/C3 and real spawned socket processes on Linux and
Windows, with no multicast requirement. Adding that workflow is not a claim that
GitHub or native Windows acceptance has run here.

## Threat model

| Threat | Classification | Concrete mechanism / remaining limit |
| --- | --- | --- |
| Malicious same-Wi-Fi device / unknown TLS client | Mitigated for authority | Exact paired certificate pins, mTLS proof of possession, no CA/hostname fallback |
| Spoofed mDNS / discovery poisoning | Partially mitigated | Untrusted bounded directory, local addresses, explicit expected paired identity; attacker can hide/fill/redirect discovery and deny availability |
| Port scan | Partially mitigated | Explicit interface/opt-in, TLS-only dedicated listener; port presence remains observable |
| Known revoked peer | Mitigated | Current tombstone checks, channel interruption, execution-time recheck and fresh reconnect authentication |
| Paired malfunctioning peer / request flood | Partially mitigated | Per-peer rate limits across reconnects, bounded writes/pending requests, fixed safe operations and bounded audit; shared CPU/network remain finite |
| Slowloris / non-reading peer | Partially mitigated | Connection ceiling, handshake/hello/frame/write/idle deadlines; kernel backlog contention remains possible |
| Frame-length attack | Mitigated | Header length limit before body allocation, bounded reads and no object deserialization |
| Request replay / changed duplicate | Mitigated | Durable claim/fingerprint, at-most-once execution and current authority before cached results |
| Identity substitution / same UUID or name with new key | Mitigated | Exact certificate and persisted C2 identity; no replacement path |
| Disconnect/reconnect and collision races | Mitigated within transport | Fresh contexts, deterministic collision preference, no stale channels/futures, finite retry budget |
| Revocation/permission race | Mitigated for C3 fixed operations | Recheck after durable claim in serialized execution transaction; immediate channel interruption after revoke commit |
| Certificate expiry | Mitigated for authority; recovery deferred | OpenSSL validity plus local checks, fail closed, preserve identity and trust records |
| Compromised endpoint / malicious local Python caller | Deferred | Trusted local process can drive backend APIs; TLS does not secure an already compromised endpoint |
| Profile rollback, cloning or key recovery | Deferred | C2 restrictions remain; no anti-rollback hardware counter or automatic key rotation |
| LAN anonymity / traffic analysis | Deferred | Addresses, service presence and traffic timing are observable; no anonymity claim |

## Acceptance and reproduction

`tests.test_connect_network` exercises real loopback sockets with separate profiles,
real keys and C2 confirmation. `tests.test_connect_process` spawns three isolated
processes and tests portable socket transport without assuming CI multicast.
`scripts/check_connect_lan.py` runs the same acceptance through **actual loopback
mDNS**. Failure to discover is a failure, not a substituted fixture success.

The harness prepares distinct identities, vault namespaces, databases and request
ledgers, completes both C2 confirmations, then hands synthetic test-vault data to
owned processes through local multiprocessing pipes. Those fixture pipes are not
Connect endpoints and are never reachable through TCP. Synthetic private keys
remain test-process memory; no key file or personal profile is used.

```bash
.venv/bin/python -m unittest tests.test_connect tests.test_connect_pairing tests.test_connect_network tests.test_connect_process -v
.venv/bin/python scripts/check_connect_lan.py
```

Verification results are recorded below. Tests require
host local socket/interface permissions; the development sandbox denies interface
inspection and socket operations, so real acceptance runs used host access.

## Remaining sequence and unavailable functionality

- C4: per-device permission UX / Devices UI and trusted local approval adapters.
- C5: structured record sync.
- C6: file transfer.
- C7: remote AI.
- C8: remote Studio.
- C9: OLIVE Mobile.
- C10: direct remote / relay.

No file transfer or filesystem access, terminal, application launch, installation,
Desktop Control, Mail/Discord send, remote model call, remote Studio, cloud/OLIVE
ID routing, Internet direct connection, mobile application or OLIVE OS is exposed.
The Connect listener cannot reach Ollama, Electron preload, Studio IPC, ComfyUI,
Mail credentials or arbitrary Python objects. Neither enabling Connect nor running
its security tests requires a model or GPU.

## Final Linux verification

Implementation commit: `605c38e`, on `feature/olive-connect-c3`, based on verified
C2 commits `ff3ccbb` and `e48577e`.

| Check | Result |
| --- | --- |
| Complete portable Python suite | 944 total: **936 passed**, 8 Windows-only skips, no failures/errors |
| C1/C2/C3 included in that run | **90 passed**; original 59 C1/C2 tests unchanged |
| Real local discovery acceptance | Passed actual loopback mDNS, three independent processes, two paired identities plus spoofed third endpoint |
| Real socket acceptance | TLS 1.3 mutual authentication, ping/status, duplicate/reconnect, spoof rejection, revocation and clean process shutdown passed |
| IPv6 | Real `::1` authenticated ping passed; scoped link-local/multicast IPv6 acceptance not claimed |
| Frontend tests | 33 passed in 12 files |
| TypeScript / ESLint / production renderer and Electron builds | Passed |
| Focused native Linux smoke | 6 passed: OLIVE GO navigation/isolation/restart; auto and Wayland Chat/pages/security/owned shutdown; two Studio journeys; REIMAGINE import/edit and honest unavailable-generation status |
| Repository-source compilation | Passed |
| Exact whole-tree `python -m compileall -q .` | Existing ignored PySide6 Android Jinja `__init__.tmpl.py` syntax error; not marked passed |
| Installed Linux CI-equivalent offscreen Qt/WebEngine and Studio provider imports | Passed |
| Dependency consistency / diff whitespace and secret/data review | Passed |

Logs are local `/tmp/olive-c3-python-final.log`, `/tmp/olive-c3-mdns.log`,
`/tmp/olive-c3-l3-smoke.log` and `/tmp/olive-c3-compile.log`. The historical full-suite
warning about 26 uncollectable Python objects remains; owned Connect worker/socket
and native application process cleanup checks passed independently. Initial failing
runs exposed lifecycle/test synchronization issues and were corrected; they are not
counted as successful acceptance. The final full run above contains no network
worker exceptions. Real mDNS was rerun after the final connection lifecycle changes.

This is host Linux acceptance plus installed portable CI-equivalent checks, not a
fresh GitHub runner result. No native Windows network run, physical second-machine
Wi-Fi test, live model/GPU re-certification, release, push or merge is claimed.
C2's vault/pairing contracts remain covered by the unchanged tests; C3 synthetic
acceptance does not access the user's real vault or data.
