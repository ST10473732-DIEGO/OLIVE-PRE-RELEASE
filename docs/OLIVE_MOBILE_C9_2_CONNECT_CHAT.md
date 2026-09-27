# OLIVE Mobile C9.2 — Connect client and real LAN acceptance

**Status: in progress; completion gate has not passed.** Real iPhone Bonjour
acceptance passed. After identifying UFW admission as the initial TCP blocker
and providing phone-only rules for the existing listeners, the owner reports
that the phone shows Connected / Remote AI Off. With Off unchanged, the harmless
arithmetic draft stays visible and Send is disabled. After the desktop Allow
workflow, the owner confirms the correct arithmetic reply on the phone and a
second Swift answer rendered in a distinct code block. The owner also confirms
remote cancellation (0.09 s acknowledgement) and a complete subsequent answer.
App relaunch, background/foreground reconnection and Wi-Fi interruption recovery
also pass, with no automatic draft submission. After desktop restart and a
phone-only firewall rule replacement for its changed listener port, the owner
confirms reconnect, retained Remote AI Allow and another arithmetic answer with
no new approval. After desktop revocation and an explicit phone Reconnect,
the owner confirms the phone remains offline/disconnected with Chat unavailable.
The owner also confirms mobile unpair removes the computer from Paired while
the displayed phone identity remains unchanged, followed by an explicitly
confirmed identity reset that shows a different Identity value. Unattended
desktop restart recovery, fresh pairing and remaining security acceptance are pending.
Isolated protocol tests and successful builds are not substitutes for those checks.

## Repository checkpoint

- `BASELINE_HEAD`: `9bc3185f1d19bf3b73fcc2632c0d3219eb919b97`
- `BASELINE_BRANCH`: `feature/olive-mobile-c9`
- `WORKTREE_STATUS`: clean at start; no later commits to preserve.
- `FINAL_HEAD`: the documentation checkpoint containing this report; resolve
  with `git log -1 --format=%H -- docs/OLIVE_MOBILE_C9_2_CONNECT_CHAT.md`.
  Validated implementation: `ac2f3ab63cb52e962032da7b05fe6837b3b4995a`
  (Connect implementation `004c72f`, Stop control `e1dc9c1`, identity recovery
  and clear-on-send/Stop draft follow-up `ac2f3ab`).
- `COMMITS`: `004c72f` — native Connect client, UI and interop tests; followed by
  `docs: record C9.2 implementation and LAN acceptance blocker` — this report
  and the appended project journey. The exact final checkpoint is also reported
  in the handoff; it cannot contain its own commit hash.
  Subsequent documentation checkpoint: `docs: record desktop SYN arrival and next read-only checks`.
  Follow-up: `docs: record UFW input filtering evidence`.
  Confirmed cause: `docs: identify UFW admission blocker for real LAN pairing`.
  Owner action: `docs: record phone-only main-listener UFW allowance`.
  First connection report: `docs: record owner-reported LAN connection and pending policy check`.
  Permission check: `docs: record connected Remote AI Off and pairing-rule cleanup`.
  First real Chat: `docs: record real iPhone arithmetic and Swift code replies`.
  Composer follow-up: `ios(chat): turn the send control into remote Stop while busy`.
  Recovery/composer follow-up: `ac2f3ab` — explicit identity reset with receipt
  invalidation, interrupted-reset tests and draft revision/cancellation fixes.
- No Git reset, stash, force push, branch deletion, merge, tag, release, or push.

Current source, especially C2/C3/C4.1/C7 implementations, takes precedence over
historical mobile design assumptions. C1–C8 runtime sources remain unchanged.
No C10, cloud account, model download, mobile Owner Mode or remote desktop tools.

## iOS and native dependency

Project: `mobile/ios/OLIVEMobile.xcodeproj`, scheme `OLIVEMobile`, iOS **17.0**,
Swift 6, bundle `io.github.st10473732-diego.olive.mobile`. Host: macOS 26.7
(25G229), Xcode 27.0 (27A266a). Physical device: iPhone 15 Pro Max; C9.1 recorded
iOS 27.0 (24A437), also verified for C9.2. Signing uses the existing local development identity;
credentials, team/device identifiers and provisioning profiles are not committed.
No simulator runtime is installed. Both simulator architectures compile.

`NativeConnect/OliveTLS.c` is a small memory-BIO adapter linked to locally built,
checksum-pinned OpenSSL **3.5.8**. It does not implement a second wire protocol or
network service. See [native dependency build and scope](../mobile/ios/NativeConnect/README.md).
The Apache license is included in the app. Libraries/build outputs are ignored;
Xcode itself performs no dependency download. Bonjour/TCP use Network.framework.

Apple's native identity APIs require a Security identity, while C2 specifically
requires Ed25519 and a TLS engine whose records the C4.1 carrier can frame.
The adapter implements those exact operations using the same TLS implementation
family as desktop. No CA fallback, accept-any-certificate callback, protocol
translation, plaintext inference or ATS exception is present. Apple documents
its [identity wrapper](https://developer.apple.com/documentation/security/sec_identity_create_with_certificates(_:_:))
and [framing above a transport](https://developer.apple.com/documentation/network/framerprotocol).

## Protocol matrix

| Desktop implementation | Swift/native equivalent | Exact wire/validation | Fixture evidence |
| --- | --- | --- | --- |
| `identity.py` | `ConnectPublicIdentity`, `ConnectIdentityStore`, `OliveTLS.c` | `olive-ed25519-x509/1`; canonical lowercase UUID; key_version 1; integer created_at; base64 DER certificate, CN=UUID, self-signed Ed25519, notBefore=created_at−300 s | Python-produced public certs validated on iPhone; generated native cert validated by Python |
| `identity.fingerprint` / `contracts.canonical` | `ConnectJSON`, public identity fingerprint | SHA-256 of sorted UTF-8 JSON `{algorithm,key_version,device_id,public_key}`; `C2/1:` + uppercase colon-separated 32-byte digest | Byte-for-byte fixture comparison |
| `pairing_wire.py` | `PairingOffer`, `ConnectTLS` | `olive-pairing-tls13/2`; exact offer fields, 4096-byte ceiling, 120 s expiry, numeric local endpoint; responder echoes endpoint/times/session and replaces only identity/name | Python offer/reply, transcript SHA-256 and receipt-message fixtures; malformed/expired validation |
| `pairing_transport.py` | `ConnectPairingClient`, `ConnectSocket` | Separate temporary TCP listener; public reply then `!I` length-prefixed TLS records; ≤32768 bytes/frame, ≤262144 received bytes, ≤3000 frames, bounded deadlines | Full Swift/desktop memory-BIO pairing fixture; real paired connection and Chat confirmed by owner |
| `tls_identity.py` | `OliveTLS.c` | TLS 1.3 only; exact self-signed peer pin with OpenSSL validity verification; Ed25519 client certificate; no system roots, tickets or session cache | Real TLS adapter vs desktop `PairingTLS`; wrong pin rejected |
| `PairingTLS.comparison` | `ConnectTLS.comparison` | `EXPORTER-OLIVE-PAIRING-v1`, 32 bytes, SHA-256 canonical `[offer,reply]` context; full 256-bit comparison | Swift/desktop exporter equality |
| `pairing.py`, `pairing_completion.py` | pairing state and `ConnectTrustRepository` | Explicit local comparison on each side; `OLIVE-CONFIRM/1:` + 32-byte binding; newline + 88-character base64 Ed25519 receipt + newline; `olive-pairing-completion/1` signed canonical message | One confirmation creates no desktop trust; full signed receipts complete the fixture |
| `discovery.py` | `ConnectDiscoveryService` | `_olive-connect._tcp.local.`; opaque instance; TXT exactly `product=OLIVE`, `version=1`; actual SRV port; directory bounded to 64 | Real Mac browse/resolve and real iPhone UI acceptance |
| `network_wire.py`, `network.Channel` | `ConnectFrame`, `ConnectTransport` | `!IBB` header: payload length, version 1, kind; encrypted empty HELLO kind 4 before online; inference 9/10, CLOSE 3 | Python/Swift exact header/frame bytes, malformed lengths/version/kind tests |
| `inference_protocol.py` | `InferenceWire` | `olive-inference/1`, `models.remote`, start/poll/cancel/status; public `fast`, `normal`, `max`; exact source/target/job/request UUIDs; start request_id=job_id | Independent Swift encoders decoded by Python; Swift decodes Python responses |
| `inference_client.py`, `inference.py` | `RemoteInferenceClient`, accumulator | Status: presets/permission/busy. Ordered pull batches at 250 ms; ≤8 events, ≤4096 UTF-8 bytes/event; consecutive sequences; 64000 aggregate bytes | Incremental/duplicate-sequence/terminal suppression tests; owner confirms arithmetic, code and hash-function replies |
| C7 cancellation/release | client Stop and C3 close | Cancel exact job; successful target terminal response follows actual coroutine/provider/residency release; uncertain loss closes channel, never replays start | Swift lifecycle fixture and unchanged desktop C7 regression; real Stop acknowledged in 0.09 s and subsequent request succeeds |
| C3 reconnect/revoke | `ConnectSession` | Fresh pinned handshake each connection; finite 0/1/2/4/8/15 s attempts, at most eight candidate routes; remote revoke is rejection/loss, not an invented revocation notification | Relaunch, foreground and Wi-Fi recovery passed; desktop restart passed after exact-port firewall repair; owner confirms revoked phone remains disconnected after explicit Reconnect, with Chat unavailable |

Mobile implements C9.2's client subset. It rejects unsolicited file/Studio
frames and does not advertise an inbound capability dispatcher. C3 has no
separate advertised capability handshake: fixed HELLO completes mutual
verification; C7 `status` returns actual public roles, busy state and Off/Ask/Allow.
There is no mobile permission setter. Default mobile role is **Normal**, because
C7 has no Automatic role. Actual local model tags are intentionally not on the
wire; internal attribution retains Connect runtime, public role, peer and job.

## Identity, pairing and trust persistence

One atomically stored Keychain envelope contains the Ed25519 seed and matching
public identity. Service is app-scoped `.connect`; item is nonsynchronizing,
`WhenUnlockedThisDeviceOnly`. Concurrent loads share provisioning work. Corrupt,
locked or mismatched existing material fails closed and is never automatically replaced.
A separate public Keychain reservation distinguishes interrupted creation or lost
private material from first installation. Existing trust history also prevents
silent identity regeneration. No seed enters UserDefaults, files, stdout,
analytics or network messages.

Secure Enclave is not used because the iOS 17 signing API supplies P-256, whereas
Connect requires Ed25519. See Apple's [Secure Enclave key constraints](https://developer.apple.com/documentation/security/protecting-keys-with-the-secure-enclave).
Keychain restart/signature verification is tested on the actual iPhone.

Public trust state and signed receipts use an atomic, versioned, protected,
backup-excluded file behind `ConnectTrustRepository`. A consumed session ID
cannot be replayed. Pending sessions never appear as trusted peers. Only original
local confirmation plus a verified peer signature over the same transcript can
commit trust. Unpair removes peer public/pin material including saved receipt
transcripts, retains replay tombstones and preserves the iPhone's own identity.
No remote desktop trust removal is claimed. Unsupported/corrupt storage is kept
without overwrite. Session and peer capacities fail closed.

The existing desktop pairing manager refuses an already-known device identity
and rejects previously revoked keys, including aliases under new device IDs.
To support explicit recovery after unpair/revocation, Settings → Advanced
connection diagnostics now offers **Reset this iPhone's Connect identity**.
It is disabled until all local peers are unpaired and no Chat is active; a
destructive confirmation explains the need for new pairing and permissions.
Reset cancels pairing, invalidates old completion receipts while keeping replay
tombstones, and replaces the Ed25519 identity in Keychain. It does not change
desktop records or permissions, or erase the Chat draft. If replacement is
interrupted between the reservation and identity writes, ordinary loading fails
closed; only another explicit reset repairs it. Tests use separate disposable
Keychain services. On 2026-09-27, after completing the revocation and local
unpair checks, the owner explicitly confirmed reset on the production app and
reported both the Identity reset notice and a changed displayed Identity value.
Fresh pairing and desktop permission assignment remain pending; no restoration
of the revoked identity's authority is claimed.

Discovery cannot authenticate names or expose a pairing offer: desktop mDNS
contains neither. Nearby therefore says **OLIVE computer — identity not yet
verified**, rather than inventing a name. The existing desktop **Connect a device**
QR is scanned with VisionKit, or its public offer is pasted. The authenticated
pairing transcript supplies the display name. Both users enter the complete value
observed on the other device and confirm. No short PIN, TOFU or automatic pairing.
The mobile network path rejects loopback offers even though the portable desktop
codec permits them for tests.

## Chat, cancellation and lifecycle

The desktop runs inference and owns model selection/policy. Mobile sends only
its explicit user/assistant context: ≤24 messages, ≤16000 bytes/message,
≤48000 aggregate bytes; 2048 max tokens, ≤64000 output bytes, ≤120 s generation.
No target-private context or tool authority is requested. C7 batches render as
received; no timer-generated text. Fenced code uses the existing native code block.

The composer prevents duplicate submit and retains/restores a failed draft.
It clears the submitted input once the desktop admits the request, while the
sent message remains in the conversation. Draft revisions ensure that later
response updates cannot clear a new draft, even when its text matches the sent
question. Stop leaves the cleared composer empty; a genuine request failure
restores the submitted text only if the user has not edited the composer since
it was cleared. No failed draft is automatically resent.
Completed visible turns supply subsequent context; failed/incomplete output does
not. Each request has unique IDs and exact response correlation. Failure and
incomplete status remain visible. Stop sends the actual C7 cancellation and waits
for acknowledgement; late polls cannot append after Stop. Lost acknowledgement
is labeled unknown/interrupted, never successful cancellation. New jobs use new IDs.

Foreground enables discovery/reconnect. Background saves drafts, cancels pairing,
closes active channels and marks active Chat interrupted. No arbitrary background
networking mode, internet fallback or silent replay is added. Reconnect verifies
the original exact pin. A paired unavailable computer stays listed Offline.
Remote revocation is not distinguishable from every other TLS rejection in C3,
so the app does not invent an authenticated “Revoked” notification.

Chat presentation/history currently stays in app memory; drafts and trust are
durable. Full history sync, files, Tasks, Studio and broader C9.3 UI remain deferred.
Advanced settings expose fixed diagnostic stages, public request IDs and measured
request/Stop timings, without prompts, responses, keys or certificates.

At the owner's request, the composer now uses one 44-point circular action
control: send arrow when idle, square Stop icon while a request is active. It
uses Grove colors and the same `AppState.stop()` C7 cancellation path. While
awaiting acknowledgement, the square remains visible and disabled, with a
Stopping response accessibility label. Completion/failure/cancellation restores
the send control. The separate Stop text button is removed; no transport or
permission behavior changes.

## Real device acceptance log

| Check | Result |
| --- | --- |
| Desktop LAN setup | Owner selected non-loopback Ethernet interface, enabled Nearby discovery and Connect; iPhone on same LAN |
| Mac browse | Actual `_olive-connect._tcp.local.` instance discovered; exact TXT validated; dynamic SRV port resolved |
| iPhone discovery | **Passed**, production app on physical iPhone, actual Nearby card; XCTest screenshot reviewed |
| Discovery timing | Nearby element found **1.098 s** after opening Devices in the opt-in test; app launch/permission/bootstrap are not included in this number |
| Pairing attempt 1 | Owner scanned real desktop QR; phone reported Offline before comparison. No successful pair or trust grant claimed |
| Connect restart observation | Original mDNS instance withdrawn, new instance advertised; no address/port hardcoded in app |
| Mac new endpoint check | Fresh mDNS discovery resolves valid TXT, but TCP connect times out before TLS. Mac has direct same-subnet route |
| Desktop clipboard | Owner reports **Could not copy the public offer**; existing desktop clipboard bug retained as evidence, not treated as a TLS failure |
| Desktop listener inspection | Owner returned one LAN listener with backlog 8 on the advertised main C3 port. The separate temporary pairing listener was not established by that snapshot |
| Diagnostic build attempt | Phone reports `pairing_tcp` and the current QR endpoint, then `peer offline`; no TLS comparison reached. Exact public endpoint retained locally, not hardcoded |
| TCP versus IP reachability | Scoped Mac TCP checks of both observed main and temporary ports timed out at 3 s. Two ICMP replies succeeded in 4.433/3.568 ms. This does not identify which hop drops TCP |
| Firewall service check | Owner reports `systemctl is-active firewalld` → `inactive`; no claim that all filtering is absent, no firewall changes |
| Fresh listener evidence | Owner confirmed main listener (backlog 8) and temporary pairing listener (backlog 2), both on the selected LAN address in the same Python process. Scoped Mac TCP checks to both timed out again |
| Desktop packet trace, 22:29 SAST | Owner captured 15 seconds on the selected Ethernet interface during Mac connection attempts to the existing main listener. Eight incoming SYN packets, no SYN-ACK or RST in either direction, zero capture drops; all eight packets share one source port and initial sequence number |
| Listener and return route | Owner confirms the existing main listener remains in the same process; the route to the Mac from the desktop LAN source uses the selected Ethernet interface |
| Installed filtering | IPv4 INPUT has policy drop in an iptables-nft-managed table containing UFW chains. mDNS UDP 5353 has an explicit accept rule; the sole user TCP allow rule has zero matches and its multiport details are opaque in the nft listing. IPv4 OUTPUT has policy accept |
| Decoded UFW rules | Owner reports UFW active, incoming deny/outgoing allow. The only user allowances are KDE Connect TCP/UDP 1714–1764; `iptables-nft -S` confirms those exact destination ranges. They do not admit OLIVE's observed main or temporary pairing ports |
| Main-listener allowance | Owner supplied the iPhone's current DHCP IPv4 address and executed the proposed rule limited to that source, the selected desktop LAN interface/address and TCP 47235. After removing an accidental extra `prototcp` argument, owner reports `Rule added`; subsequent phone state is Connected / Remote AI Off |
| Fresh pairing listener | Owner returned main TCP 47235 and temporary TCP 52643, both in the existing OLIVE process on the selected LAN interface. Provided a phone-only rule for that exact temporary port, followed by immediate scan/two-sided confirmation instructions |
| First connection report | Owner first reports “ok they connected,” then confirms the phone shows Connected / Remote AI Off. This is owner-observed production UI evidence; no Chat response or pairing/session timing is claimed |
| Pairing-rule cleanup | Owner initially reported deletion of the phone-to-temporary-port 52643 rule. However, the later numbered UFW output on 2026-09-27 still lists that exact rule. Cleanup is therefore not verified; exact-rule deletion has been requested again. The main-listener allowance remains and the Mac remains excluded |
| Both confirmations / denial / abort | The owner followed the two-sided confirmation flow and obtained an authenticated paired connection. Separate denial/abort checks on the real devices remain pending |
| Paired record / app relaunch | **Passed, real-device screenshot reviewed:** after installing the composer update and relaunching the normal app, Devices shows the retained desktop under Paired with Connected / Remote AI Allow. No new pairing ceremony was performed |
| Background / foreground reconnect | **Passed, owner-observed:** after about ten seconds in the background, the phone returns to Connected / Remote AI Allow without re-pairing, and an explicitly submitted hash-function question receives another answer. Reconnection described as almost instant; no numeric timing claimed |
| Remote AI Off | **Passed, owner-observed mobile UI:** while Connected / Remote AI Off, the arithmetic question remains visible and the Send arrow is disabled. This verifies the normal mobile submission path; it is not a live malicious-client bypass test |
| Remote AI Allow | Following instructions to enable Allow through desktop Devices → paired iPhone → Permissions and explicitly submit the preserved draft, owner reports successful replies. No mobile policy setter or Owner Mode was used |
| Arithmetic reply | **Passed, owner-observed real iPhone Chat:** “391 - multiplying 17 by 23 gives 391.” This is the correct answer to the supplied harmless arithmetic prompt |
| Swift code rendering | **Passed, owner-observed:** the subsequent even-number Swift function reply displays in a distinct code block. Exact function text has not been returned, so this verifies rendering rather than executable correctness |
| Response timing / delivery | Owner describes the first reply as instant. This is qualitative only: no numerical latency, per-chunk observation, model role confirmation or cross-device request-ID receipt has yet been collected |
| Updated Send/Stop control | **Passed, owner-observed on the installed update:** send arrow becomes a square inside a circle, tapping it cancels the request, and the arrow returns afterward |
| Hash prompt / new request after Stop | **Passed, owner-observed:** after cancellation, “Explain in two sentences what a hash function does” returns a complete answer. Exact answer text has not been collected |
| Remote Stop | **Passed, owner-observed C7 cancellation:** phone output stops, desktop activity reports Remote AI cancelled, and phone diagnostic reports Stop acknowledgement **0.09 s** for request `e3a9bd09-bef4-4faf-bc2f-d89d9009ca93`. This is the displayed rounded acknowledgement duration, not a separate provider-internal timing |
| Wi-Fi interruption / offline draft | **Passed, owner-observed:** Wi-Fi Off produces Offline with disabled Send and a preserved draft; restoring Wi-Fi reconnects with the draft still unsent; pressing Send explicitly produces an answer |
| Desktop restart | **Retained trust and Chat passed after host rule repair:** main listener moved from TCP 47235 to TCP 33823 in a new process; phone initially Offline. Owner confirms the phone-specific rule for 33823 was added and the old 47235 rule deleted, then the phone reconnected with Remote AI Allow and answered the arithmetic prompt without another approval. Unattended restart recovery is not certified; no numeric reconnect time measured |
| Desktop revocation | **Passed, owner-observed 2026-09-27:** after following desktop Revoke device and phone Reconnect instructions, the phone remains offline/disconnected with Chat unavailable. The mobile pairing record was retained during this check; no key reset or new pairing was performed. This is real UI acceptance, not an independently captured TLS rejection trace |
| Mobile-local unpair | **Passed, owner-observed 2026-09-27:** the owner confirms the computer disappears from Paired after Unpair and the displayed Identity value stays unchanged. This verifies the visible removal and identity preservation; automated repository tests separately verify removal of peer pin material. No removal of the desktop's revoked record is claimed |
| Identity reset | **Passed, owner-observed 2026-09-27:** after explicit confirmation in Settings, the phone shows Identity reset and a different displayed Identity value. This follows successful unpair; the old desktop trust record remains revoked |
| Fresh pairing after reset | Pending. Owner confirms the same phone address; `ss` shows only main TCP 33823 in the existing desktop process, and numbered UFW output confirms its phone-only allowance. The old temporary 52643 rule is also still listed despite the earlier cleanup report; requested removal before a fresh QR/listener check. New identity requires full two-sided confirmation and a fresh desktop Remote AI permission decision |
| Fresh reset-recovery offer | Owner subsequently reports temporary TCP 50703 alongside main 33823, both in the same OLIVE process. Provided an allowance limited to the current phone, selected LAN interface/address and TCP 50703, with immediate scan and full two-sided confirmation. Pair result and old-rule deletion result remain pending. The temporary 50703 allowance must be removed after this attempt |
| Wrong peer | Native wrong-pin tests pass; real cross-device wrong-peer check remains pending |

No proxy, simulator, fixture response or mock peer was substituted for these
pending steps. No SSH, extra remote-access method or exposure of Ollama was
introduced. The owner's explicit main-listener firewall exception is recorded
above; there is no blanket LAN or port-range allowance. Public routing
diagnostics stay local in ignored logs.

The real replies are owner-observed acceptance results from the production
phone/desktop path. They are not generated fixtures or locally substituted
answers. No exact reply latency is inferred from “instant.” The owner performed
the requested Stop test and supplied the request ID, acknowledgement time and
desktop Remote AI cancelled event, then confirmed a complete new answer. The
owner did not independently inspect runtime objects or provider telemetry.
C7's audited terminal acknowledgement is withheld until provider-stream closure
and task/lease release; desktop activity alone would not establish that release.
Early/completion-race/drop-during-cancel cases still need live-device coverage.

### SYN trace interpretation (owner-supplied, 2026-09-26)

The capture spans incoming packets at 22:29:44.809855 through 22:29:55.812874
SAST. These are one connection attempt and its seven retransmissions, not eight
independent connections. The first SYN has ECE/CWR flags; the retransmissions
are plain SYNs. None receives a captured SYN-ACK or RST on that interface.

This proves the Mac's SYN reaches the desktop capture point. It does **not**
prove delivery to the listening TCP socket or identify a dropping rule. No
desktop response is visible on the selected interface, so desktop input/output
filtering, routing (including a different egress interface), and local TCP
handling remain to be distinguished. TLS, pin validation, two-sided confirmation
and inference have not started. This trace observes the Mac/main-listener path;
it does not independently certify the iPhone/temporary-listener path.

The next read-only checks preserve OLIVE's running process: verify current `ss`
listener state, inspect `ip -4 route get` to the Mac using the desktop LAN source,
and list the existing nftables ruleset. An inactive firewalld service does not
establish the absence of other installed packet-filter rules. If route/rules
do not explain the evidence, a bounded capture on `any`, still restricted to
this Mac and Connect port, can test whether a reply leaves another interface.
No rule insertion, flushing, tracing rule, sysctl write, extra port or service
restart is part of these checks.

The owner's Mac command used `nc -w 3`; its trace still covered one attempt
retransmitting for over eleven seconds. The installed Mac `nc -h` documents
`-G` as its connection-timeout option. Future manual probes use `nc -vz -G 3`
to bound each connect; this is a diagnostic correction, not a transport change.

The subsequent owner-supplied listener/route/rules output confirms that UFW-managed
input filtering is installed despite firewalld being inactive. The ordinary return
route uses the same Ethernet interface. The IPv4 INPUT policy is `drop`, while
mDNS is explicitly accepted; this explains how discovery can remain available
without general TCP admission. The user TCP allow rule has zero matches. Taken
with incoming SYNs and absent replies, desktop input filtering is the leading
explanation. A cumulative ruleset snapshot is not a per-packet verdict trace,
and the `xt match "multiport"` representation does not reveal allowed ports.
The next two read-only commands decode that rule through its existing management
tools. No direct nft edits to the iptables-nft-managed tables, UFW disable/reset,
broad port-range allowance or application protocol changes are proposed.

The owner then decoded the rules through UFW and iptables-nft: UFW is active
with incoming deny/outgoing allow, and the only user TCP/UDP allowances are
KDE Connect destination ports 1714–1764. The observed OLIVE main port and
temporary pairing ports are outside that range. With the live listener,
incoming SYN capture, correct ordinary return route and absence of TCP replies,
the installed UFW input policy accounts for the observed connection failure.
This establishes the current admission blocker; successful TCP, TLS, pairing
and Chat still require fresh acceptance after any owner-authorized repair.

No additional broad packet capture or protocol change is needed to explain this
blocker. The next proposal will use the iPhone's actual Wi-Fi IPv4 address, the
selected desktop interface/address and only current OLIVE listener ports, with
explicit removal commands. A new pairing QR should be created only when ready
to apply an authorized rule because its listener is temporary. An ordinary UFW
allow rule has no automatic expiry; it must be removed explicitly, and a rule
for one OS-assigned port must not be described as covering future restarts or
fresh pairing offers. At that checkpoint no UFW rule, security setting or
listener had been changed.

The owner subsequently attempted the exact main-listener rule and supplied the
failed command. An extra `prototcp` token explained UFW 0.36.2's argument-count
error. After correction, the owner reports `Rule added`. This is an explicit
owner-applied exception for the current iPhone address to the existing main
TCP listener only, on the selected desktop interface/address. It grants no
Connect trust or Remote AI permission. DHCP remains enabled; a changed phone
address or main-listener port requires reviewing/removing the now-stale rule.
The Mac remains excluded. The fresh QR's separate temporary port must be
handled before any real pairing/TLS success can be claimed. No app, desktop
runtime, TLS policy or protocol was changed during this diagnostic repair.

The later desktop restart reproduced the port-lifetime limitation: the new main
listener is TCP 33823, whereas the phone-specific rule allowed the previous
TCP 47235. The phone correctly reports Offline. The requested repair adds the
same interface/source/destination-scoped permission for the new existing port
and deletes the old exact rule; it does not allow a range or add a listener.
The owner confirms both rule changes, reconnection, retained Remote AI Allow
and a subsequent arithmetic answer without another approval. This establishes
retained trust but not unattended firewall compatibility across future restarts.
Source inspection confirms C3
supports an explicit listener port internally, but the existing Devices enable
workflow passes only address/discovery and therefore selects an OS-assigned
port. No desktop listener, persistence or startup behavior was changed to mask
this host-configuration limitation.

## Validation so far

- Pinned TLS libraries built for iPhone arm64 and both simulator architectures.
- `xcodebuild -list` succeeded. Final simulator app/test build and generic iOS
  Release build passed after the identity recovery and draft update
  (`olive-c92-recovery-composer-simulator.log`,
  `olive-c92-recovery-composer-generic.log`). The initial sandboxed recovery
  build could not run Xcode's Observation macro plugin; the same source built
  successfully with the required host Xcode access.
- Final physical signed build/install/test: **34 unit tests + 8 UI tests passed**
  in `/tmp/olive-c92-device-tests-8.xcresult` (unit 2.409 s, UI 72.749 s),
  including real-LAN discovery. The app was reopened normally without test
  arguments. The two new identity tests cover durable replacement and
  interrupted replacement; receipt tests also prevent old trust recovery after
  reset. Four new Chat tests cover Stop keeping input empty, preservation of a
  new identical draft, failed admission and explicit retry after connection loss.
  Earlier runs 3/4/5/6/7 remain as evidence, with 23/25/28/28/30 unit tests and
  eight UI tests each. The owner then confirmed that sending clears Message
  OLIVE while retaining the question in the conversation, and Stop leaves the
  input empty. Both live composer checks passed.
- Run 6 screenshot `artifacts/mobile-c9-2/device-6/4401A306-2E53-4CC7-8720-F0FC1133C33D.png`
  was reviewed: retained real pairing, Connected and Remote AI Allow after
  relaunch. Screenshots stay ignored locally. The same run checks multiline,
  disabled Send, large text and landscape. The owner additionally confirmed
  the real busy-button transition, cancellation and return to Send.
- First physical attempt failed to compile a throwing test assertion. Next run
  exposed an invalid assumption that repeated Ed25519 signatures must have
  identical bytes on this platform, and an obsolete C9.1 UI text assertion.
  The test now verifies both signatures under the preserved public key; identity
  equality remains asserted. No trust/security check was removed.
- Python→Swift and independent Swift→Python C2/C3/C7 fixture checks passed.
- Native TLS adapter vs desktop: mutual authentication/exporter/confirmation and
  wrong-pin and same-key/different-certificate rejection tests passed (three
  native TLS tests). Full Swift/desktop C4.1 two-sided receipt fixture passed.
- Canonical artifact: `tests/fixtures/mobile_connect/vectors.json`, SHA-256
  `79fb23c90e6a59a6c6e7c25c63ac2f4f2e1cce304cd90747baac10d978d9bcba`.
  Contains disposable public certificates only, no private seeds or user data.
- `python -m compileall -q .`: passed using disposable writable bytecode cache.
- Earlier full Python regression after the Stop control update: **1439 run, 1377
  passed, 58 skipped, 2 failures, 2 errors**, 191.512 s
  (`/tmp/olive-c92-composer-python.log`). The extra opt-in Swift-process test is skipped during
  ordinary discovery and passes separately in the interop harness. The same
  four failures/errors were already reproduced against a fresh `git archive`
  of exact `BASELINE_HEAD`; no desktop source change or test weakening.
- Latest full Python regression during the recovery/composer follow-up:
  **1439 run, 1376 passed, 58 skipped, 2 failures, 3 errors**, 196.638 s
  (`/tmp/olive-c92-reset-python.log`). In addition to those four failures/errors,
  Studio's `test_save_receipt_commit_precedes_success_acknowledgement` hit
  `connection_closed` after injected SQLite contention. It also failed in an
  isolated current run. Baseline initially passed, then reproduced the same
  error in one of three bounded repeats
  (`/tmp/olive-c92-reset-studio-baseline-repeat.log`). The test and Connect
  runtime source are unchanged from C9.1. No test expectations were weakened.
- First Python run used `/tmp` instead of canonical `/private/tmp` for temporary
  files, causing path equality failures. Retained as failed evidence; corrected
  environment rerun above is the comparison run.

Within the earlier full discovery, the Connect subset ran **238 tests: 237 passed, one
baseline Studio descendant timeout**. The final focused Python/native protocol
run passed all eight tests.

Remaining baseline failures: Connect Studio descendant timeout and intermittent
receipt/SQLite contention, Linux ELF check on macOS, Owner Chat project run,
and missing-toolchain JDK wording. The desktop
gate is **not fully green on this Mac**. No native CachyOS regression is claimed.

## Reproduction

See [iOS README](../mobile/ios/README.md),
[native adapter build](../mobile/ios/NativeConnect/README.md), and:

```sh
OLIVE_PYTHON=/path/to/project/python bash mobile/ios/scripts/check-connect-interop.sh
python -m unittest tests.test_mobile_connect_vectors tests.test_mobile_connect_tls -v
```

The standalone `scripts/check_mobile_connect_acceptance.py` reads only the
selected iPhone's desktop Connect receipt metadata through a read-only SQLite
connection. It never instantiates the service, opens a listener, loads keys,
reads chat contents or modifies state. Use the configured profile explicitly if
both legacy and current profiles exist. Desktop runtime-release evidence still
requires C7 acknowledgement/actual job cleanup, not just a terminal database row.

## Completion gate

C9.2 remains **incomplete**. Real pairing, permission-respecting Chat/code,
Stop, subsequent requests and mobile interruption recovery have passed as
recorded above. Desktop revocation also prevents reconnect and Chat in the
owner's real-device check. Mobile-local unpair removes the paired device while
preserving the displayed phone identity. Explicit identity reset then produced
a changed displayed identity. Fresh pairing, remaining security acceptance and
final relevant tests remain. Desktop restart retains trust and permission,
but its changing port requires host firewall rule repair in this setup.
This is not classified as an Apple platform limitation. No C9.3/C10 work
begins and no release claim is made.
