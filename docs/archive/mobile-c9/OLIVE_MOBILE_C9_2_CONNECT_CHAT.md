# OLIVE Mobile C9.2 — Connect client and real LAN acceptance

**Status: COMPLETE — C9.2 real-device completion gate passed on 2026-09-27.**

The physical iPhone 15 Pro Max discovers and securely pairs with the real
CachyOS desktop through existing Connect, retains its Keychain identity and
trust, sends real C7 Chat, renders code, cancels desktop inference and sends new
requests afterward. Permission Off/Allow, revocation, unpair, explicit identity
reset, fresh pairing, wrong-pin rejection, both pairing cancellation directions
and cancellation boundary checks passed with the evidence distinguished below.

Persistent, opt-in listener ports and exactly scoped UFW allowances preserve
default-deny filtering. Unattended desktop restart now reconnects the phone
without firewall edits or re-pairing. After the Start status fix, the owner reports
connection in about **five seconds** and successful accumulated Fast Chat ending
with the multiplication answer **391**. No automatic request replay is introduced.

Final deployed desktop commit: `698b002e13ba76aef8bcd1a391b33280764e1bad`.
Fresh native CachyOS regression passed: **253 Connect tests**, **1,442 Python
tests (8 skipped)**, and **101 frontend tests**, plus type checking and build.
Physical iOS validation passed **43 unit tests and 8 UI tests**. The Mac Python
baseline failures and Electron timing limitations remain explicitly recorded;
completion does not assert that every test on every platform was green.

The chronological record below retains failed attempts and repairs. Its earlier
pending states and temporary per-port rules are superseded by the final closure
record. C9.3, C10 and OLIVE OS have not begun.

## Repository checkpoint

- `BASELINE_HEAD`: `9bc3185f1d19bf3b73fcc2632c0d3219eb919b97`
- `BASELINE_BRANCH`: `feature/olive-mobile-c9`
- `WORKTREE_STATUS`: clean at start; no later commits to preserve.
- `FINAL_HEAD`: the documentation checkpoint containing this report; resolve
  with `git log -1 --format=%H -- docs/OLIVE_MOBILE_C9_2_CONNECT_CHAT.md`.
  Final validated implementation: `f96b7f3e587bb91bae4931a5fa36070a6621c803`
  (earlier mobile admission checkpoint `5cafbfff631a11f9d5feb4c9db4457c7f1c5af2f`)
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
  Chat quota follow-up: `0788cdf` — owner-requested removal of C7's six-starts
  per minute admission quota; concurrency and transport budgets preserved.
  Rejection recovery: `5cafbff` — keep healthy mobile connections after rejected
  admission; distinct rate-limit error and cross-language error fixtures.
- No Git reset, stash, force push, branch deletion, merge, tag, release, or push.

Current source, especially C2/C3/C4.1/C7 implementations, takes precedence over
historical mobile design assumptions. Desktop changes comprise the requested C7
admission-quota removal, bounded model-context fitting, opt-in saved listener
ports/startup and the Start status correction. C2/C3 TLS and pairing trust
semantics, permissions and wire versions remain unchanged.
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
network service. See [native dependency build and scope](../../../mobile/ios/NativeConnect/README.md).
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
The owner subsequently confirms fresh pairing succeeds with Connected / Remote
AI Off, then a new desktop Allow decision permits a real arithmetic answer of
391. The new identity receives separately assigned permission; no restoration
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

### Rapid sequential Chat follow-up (2026-09-27)

The owner reported that several rapid questions were followed by a misleading
busy error and a need to reconnect. Source inspection found the existing C7
six-new-start-attempts per peer per rolling minute quota. Swift mapped
`rate_limited` to busy and attempted to cancel a rejected, nonexistent job.
The resulting `unknown_request` caused it to close the healthy transport.

At the owner's explicit request, desktop commit `0788cdf` removes that separate
question quota. Admission still enforces actual capacity: one unfinished job
per peer, one active remote generation, two waiting jobs, bounded approvals,
32 transient jobs and 10,000 durable receipts. C3 retains its 600 C7 frames per
peer/minute budget across reconnects. This enables continued sequential Chat
within resource bounds, not unbounded simultaneous work or additional authority.
The old quota test is updated for this requested policy change, with additional
tests for twelve completed requests in one frozen admission-clock window and
continued frame-budget enforcement across reconnects. Wire identifiers and
Off/Ask/Allow remain unchanged; old peers stay compatible.

Swift commit `5cafbff` distinguishes rate-limit rejection from resource busy.
An explicit initial `busy`, `rate_limited` or `model_unavailable` rejection no
longer triggers cancellation of a nonexistent job or closes the session.
Uncertain starts and failures after job admission still perform bounded cleanup
and close on failed cancellation. Drafts remain available for explicit retry;
no automatic request replay is introduced. This also works against older
desktop builds that still have the six-request quota.

The phone fix is installed and the normal app reopened. The owner confirmed
a clean CachyOS checkout on `feature/olive-mobile-c9` at exact `BASELINE_HEAD`,
then reported that the patch installer completed and committed the update.
The available desktop test interpreter is the checkout's `.venv/bin/python`.
The owner subsequently reports native C1–C8 regression completed successfully:
243 tests in 92.708 s, OK. The owner subsequently supplied exact desktop
HEAD `25e0cf9f9ce5f070456f638b6eba20e608ee0c97` and an empty `git status --short`.
The restarted desktop was listening on TCP 54981, Python PID 403444.
The final numbered UFW output at this checkpoint was active with exactly:

- KDE Connect IPv4, Allow In, Anywhere;
- TCP 54981, input interface `enp111s0`, destination `192.168.10.196`,
  source phone `192.168.10.37`, Allow In;
- KDE Connect IPv6, Allow In, Anywhere (v6).

The earlier pairing exceptions for 52643 and 50703 and main-listener rules for
47235 and 33823 are absent. The previously verified incoming-deny/outgoing-allow
policy was not changed by the scoped rule replacements. The phone uses DHCP;
its source address is a firewall restriction, not a Connect identity.
No new pairing is needed or requested. Desktop-only patch
`/tmp/olive-c92-desktop-chat-quota.patch` has SHA-256
`483f59137556598f6fc04e4f6adac20cf5b4828ff055da203c06689455ce43b4`.
It applies cleanly with `git am` to an isolated checkout of that exact baseline,
producing identical runtime, regression tests and C7 documentation. The prepared
copy/paste installer checks the baseline, clean worktree, patch checksum and
patch applicability before committing it locally. No remote access, push or
firewall change is part of this installer. The installer does not run tests.
Native CachyOS C1–C8 regression passed according to the owner's terminal summary.
Desktop restart is owner-confirmed by the new main listener/process.
After the rule-replacement and eight-questions-within-one-minute instructions,
the owner confirms all eight requests work without reconnecting. Real
sequential-Chat acceptance therefore passed as owner-reported evidence;
per-request timestamps were not independently captured. Compilation
confirmation, corrected desktop HEAD and numbered UFW output after the main
rule replacement remain outstanding. Successful Chat establishes reachability
but does not independently verify removal of the old 33823 rule.

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
| Pairing-rule cleanup | Owner initially reported deletion of the phone-to-temporary-port 52643 rule, but a later numbered UFW output still listed it. Cleanup was requested again. The final owner-supplied numbered output after fresh pairing now confirms both temporary rules (52643 and 50703) are absent. Only the phone-specific main 33823 allowance remains alongside the pre-existing KDE Connect rules; the Mac remains excluded |
| Both confirmations / denial / abort | Real two-sided pairing passed. With a separate test identity, desktop Cancel before either confirmation left the paired-device list unchanged and the phone reported connection loss. Phone Cancel on a fresh attempt also cancelled on desktop, returned the phone to unpaired, and left the desktop paired-device list unchanged |
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
| Desktop restart | **Retained trust and Chat passed after host rule repair:** main listener moved from TCP 47235 to TCP 33823 in a new process; phone initially Offline. Owner confirms the phone-specific rule for 33823 was added and the old 47235 rule deleted, then the phone reconnected with Remote AI Allow and answered the arithmetic prompt without another approval. This initial workaround was superseded by saved listener ports; unattended restart later passed with no firewall edit, and the final owner-reported reconnect was about five seconds |
| Desktop revocation | **Passed, owner-observed 2026-09-27:** after following desktop Revoke device and phone Reconnect instructions, the phone remains offline/disconnected with Chat unavailable. The mobile pairing record was retained during this check; no key reset or new pairing was performed. This is real UI acceptance, not an independently captured TLS rejection trace |
| Mobile-local unpair | **Passed, owner-observed 2026-09-27:** the owner confirms the computer disappears from Paired after Unpair and the displayed Identity value stays unchanged. This verifies the visible removal and identity preservation; automated repository tests separately verify removal of peer pin material. No removal of the desktop's revoked record is claimed |
| Identity reset | **Passed, owner-observed 2026-09-27:** after explicit confirmation in Settings, the phone shows Identity reset and a different displayed Identity value. This follows successful unpair; the old desktop trust record remains revoked |
| Fresh pairing after reset | **Passed, owner-observed 2026-09-27:** after the fresh QR and full two-sided confirmation instructions, the owner reports the phone connected again with Remote AI Off. The new identity does not inherit the old identity's Allow setting. After a new desktop Allow decision, the owner confirms the phone answers the arithmetic question with 391 |
| Fresh reset-recovery offer and cleanup | Temporary TCP 50703 was confirmed alongside main 33823 in the same OLIVE process and admitted only for the phone on the selected LAN interface/address. After pairing, the final numbered UFW output confirms its deletion and removal of stale 52643. UFW remains active; main TCP 33823 is still restricted to the same phone and selected interface/address. Existing KDE Connect IPv4/IPv6 rules remain |
| Wrong peer | **Passed, physical iPhone → real CachyOS:** opt-in test authenticates the saved correct pin, then requires `certificateMismatch` for an in-memory wrong expected certificate at that same endpoint. Saved trust and phone identity remain unchanged. Run 10: 0.230 s; run 11: 0.249 s for the complete positive/negative check |
| Rapid sequential Chat after quota update | **Passed, owner-observed 2026-09-27:** following instructions to send eight short questions within one minute and wait for each response, the owner reports all work without reconnecting. The desktop had been patched, passed 243 native Connect tests and restarted with main TCP 54981. No exact per-request timings are claimed |

No proxy, simulator, fixture response or mock peer was substituted for the
real-device acceptance steps. No SSH, extra remote-access method or exposure of Ollama was
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
Physical run 11 subsequently passed early, repeated, completion-race and
connection-loss-during-cancel checks, detailed in the closure results below.

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
- `xcodebuild -list` succeeded. Earlier simulator app/test build and generic iOS
  Release build passed after the identity recovery and draft update
  (`olive-c92-recovery-composer-simulator.log`,
  `olive-c92-recovery-composer-generic.log`). The initial sandboxed recovery
  build could not run Xcode's Observation macro plugin; the same source built
  successfully with the required host Xcode access.
- Earlier physical signed build/install/test: **34 unit tests + 8 UI tests passed**
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
- Latest physical signed build/install/test: **38 unit tests + 8 UI tests passed**
  in `/tmp/olive-c92-device-tests-9.xcresult` (unit 2.461 s, UI 72.574 s).
  Added rejection tests verify no cancel/close on rejected admission, explicit
  retry over the same client, cleanup for uncertain starts, cancellation after
  admitted-job errors, and preserved draft without automatic retry. Simulator
  app/test and generic-device Release builds also passed
  (`olive-c92-chat-limit-simulator.log`, `olive-c92-chat-limit-generic.log`).
  The updated app was reopened normally with its production pairing preserved.
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
  `d37903c75fdc6997906b877666e6ff44b2b821a97f9d7b732fc8417ef2b0c75c`.
  The follow-up adds canonical `busy`, `rate_limited`, `model_unavailable` and
  `unknown_request` responses without replacing the original public identities.
  Production Python validation and independent Swift re-encoding passed, along
  with the full two-sided pairing harness (`olive-c92-chat-limit-interop.log`).
  Contains disposable public certificates only, no private seeds or user data.
- `python -m compileall -q .`: passed using disposable writable bytecode cache.
- Earlier full Python regression after the Stop control update: **1439 run, 1377
  passed, 58 skipped, 2 failures, 2 errors**, 191.512 s
  (`/tmp/olive-c92-composer-python.log`). The extra opt-in Swift-process test is skipped during
  ordinary discovery and passes separately in the interop harness. The same
  four failures/errors were already reproduced against a fresh `git archive`
  of exact `BASELINE_HEAD`; no desktop source change or test weakening.
- Earlier full Python regression during the recovery/composer follow-up:
  **1439 run, 1376 passed, 58 skipped, 2 failures, 3 errors**, 196.638 s
  (`/tmp/olive-c92-reset-python.log`). In addition to those four failures/errors,
  Studio's `test_save_receipt_commit_precedes_success_acknowledgement` hit
  `connection_closed` after injected SQLite contention. It also failed in an
  isolated current run. Baseline initially passed, then reproduced the same
  error in one of three bounded repeats
  (`/tmp/olive-c92-reset-studio-baseline-repeat.log`). The test and Connect
  runtime source were unchanged from C9.1 at that checkpoint. No test
  expectations were weakened to hide that failure.
- Latest full Python regression after the quota/recovery changes: **1441 run,
  1379 passed, 58 skipped, 2 failures, 2 errors**, 197.038 s
  (`/tmp/olive-c92-chat-limit-python.log`). These are the four previously
  reproduced baseline issues; the intermittent SQLite test passed this run.
  Separate full C1–C8 discovery ran **243 tests: 242 passed, one baseline Studio
  descendant timeout**, 101.942 s (`olive-c92-chat-limit-connect.log`). Focused
  C7 ran **35 tests, all passed**, 19.964 s (`olive-c92-chat-limit-c7.log`).
- Native CachyOS C1–C8 regression after applying the desktop patch:
  **243 tests passed**, 92.708 s, **OK**, as reported by the owner from the
  terminal summary. Command used the checkout's `.venv/bin/python`, isolated
  `OLIVE_DATA_DIR` and `unittest discover -s tests -p 'test_connect*.py' -v`.
  Requested log destination: `/tmp/olive-c92-desktop-connect.log` on CachyOS.
  The full log has not been independently read; this is owner-reported evidence.
- First Python run used `/tmp` instead of canonical `/private/tmp` for temporary
  files, causing path equality failures. Retained as failed evidence; corrected
  environment rerun above is the comparison run.

Within the earlier full discovery, the Connect subset ran **238 tests: 237 passed, one
baseline Studio descendant timeout**. The final focused Python/native protocol
run passed all eight tests.

Remaining baseline failures: Connect Studio descendant timeout and intermittent
receipt/SQLite contention, Linux ELF check on macOS, Owner Chat project run,
and missing-toolchain JDK wording. The desktop
gate is **not fully green on this Mac**. Native CachyOS C1–C8 nevertheless passed
all 243 tests as reported above; no full native Python-suite result is claimed.

## Reproduction

See [iOS README](../../../mobile/ios/README.md),
[native adapter build](../../../mobile/ios/NativeConnect/README.md), and:

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

C9.2 is **complete** for the tested physical iPhone and local CachyOS desktop.
All functional items in the requested completion gate have evidence: discovery,
secure pairing, durable identity/trust, truthful connection/capability state,
real Chat and code rendering, actual remote cancellation and subsequent requests,
interruption/restart recovery, permission Off/Allow, revocation and unpair.

The persistent listener architecture removes manual per-restart firewall edits
on the selected LAN. It retains UFW default deny, exact source/interface/address
scope, mutual identity verification and existing Connect capability permissions.
Both manual pairing cancellation directions and automated physical wrong-pin,
early/repeated/completion-race/socket-loss cancellation checks passed. Native
CachyOS and physical iOS regression results are recorded below. Known Mac
baseline failures and unrelated Electron transfer timing failures remain visible.

This closes C9.2 only: no C9.3/C10, cloud relay, mobile Owner Mode, release, push,
merge or tag is part of this checkpoint.


## Final closure follow-up and evidence

The owner requests completion of C9.2, including unattended restart through
UFW, rather than proceeding to C9.3. The latest Mac starting HEAD is
`e83be43e325189af5df5b6c6120e8c2e488fcfb8`; its worktree was clean.
The independently patched CachyOS starting HEAD is
`25e0cf9f9ce5f070456f638b6eba20e608ee0c97`, also clean.

### Persistent listener design

A new trusted-desktop checkbox, **Keep Connect available after restart**, is
explicit opt-in. Existing installations and calls without this option remain
session-only and start off. Enabling it selects two OS-assigned unprivileged
ports once and saves them with the exact interface name, address, subnet and
Nearby-discovery setting in the profile's `connect/network-v1.json`.
This versioned, bounded, atomic local settings store contains no trust or keys;
absence preserves legacy behavior and malformed data is preserved and fails
closed. It does not change the Connect database schema or wire protocols.

At subsequent application startup, after runtime services are attached, the
service reopens the same main port only on that exact currently available
interface/address/subnet. Port conflicts or unavailable interfaces fail closed
with a diagnostic. There is no random-port fallback or wildcard bind.
Explicit **Turn Connect off** clears startup intent before closing the listener;
normal process shutdown preserves the owner's opt-in. Changing the selected
interface requires a new explicit enable and firewall scope review.

The saved pairing port is not a permanent listener. Each owner-created C4 offer
opens it for that bounded pairing session and closes it on completion, abort,
expiry or disable. The QR still carries the actual address/port. TLS, mutual
identity checks, two-sided confirmation, signed receipts and permission defaults
are unchanged. A conflicting pairing port fails rather than advertising another.

On POSIX, listeners use SO_REUSEADDR for restart after TIME_WAIT; no SO_REUSEPORT
is enabled. Windows uses SO_EXCLUSIVEADDRUSE, never the permissive Windows
SO_REUSEADDR behavior. Real socket tests check concurrent-listener exclusion and
same-port reuse after an accepted connection is actively closed. Windows can
still report a port temporarily unavailable; it must never substitute another
port. See [Linux socket options](https://man7.org/linux/man-pages/man7/socket.7.html)
and [Microsoft exclusive address binding](https://learn.microsoft.com/en-us/windows/win32/winsock/using-so-reuseaddr-and-so-exclusiveaddruse).

The firewall design is two exact inbound TCP rules, scoped to the selected
interface, desktop address and authorized phone address. The existing mDNS rule
already works and needs no change. UFW remains default-deny. OLIVE does not run
sudo, modify firewall rules, introduce a privileged helper, open Ollama/SSH,
or request an ephemeral-port range. UFW cannot pin these input rules to the
Python executable; exact socket binding plus unchanged Connect authentication
remain necessary. DHCP address changes fail closed and need a scoped rule update;
this design certifies process restarts on the same selected LAN, not arbitrary
network/address changes. No live firewall change for this architecture has yet
been reported.

### Mobile reconnect and Chat follow-up

A new Bonjour service instance can restart an exhausted mobile recovery cycle.
Announcements are coalesced to at most one new cycle per minute, with the existing
six bounded attempts and eight candidate endpoints. A successful session resets
the retry budget for later disconnection. Every connection still requires the
saved peer certificate. No inference is replayed after interruption.

Owner reports Fast failing with “Connect received an invalid message,” request
`ead0de10-2f68-44ce-bf97-cb746e0904d8`, then another role answering. The exact desktop
receipt subsequently confirmed `input_too_large`, detailed below. Inspection found
that valid `inference_failed`, input/output-limit and stream errors all mapped to
that generic message. They now have distinct typed messages. Conversation
context now selects a recent suffix of whole completed turns within C7's
24-message, 16,000-byte/message and 48,000-byte total bounds. Visible messages
are retained. This removes an avoidable long-conversation input failure without
changing desktop protocol limits or adding a usage quota.

Validation and deployment results for this follow-up will be recorded as they
complete. Wrong-peer acceptance has an explicit opt-in physical-iPhone test:
a correct pinned handshake selects the real endpoint before testing a wrong
expected certificate; TCP failure alone cannot pass it. The test does not change
saved identity or trust. Pairing denial/abort remain pending. The cancellation
race/loss cases were separately tested in physical run 11, not inferred from
the earlier generic Stop acceptance.


The owner's read-only receipt query resolved the Fast failure:
`('fast', 'failed', 'input_too_large', 10429, 0, 71)` — preset, state, error,
input bytes, output bytes and duration ms. Source inspection confirms the model
adapter rejected its context estimate before calling the provider. This was
not a per-minute quota. A desktop follow-up now fits the newest complete supplied
turns to the selected model's effective context window, preserving static
framing and the requested output reserve. Oversized latest questions still fail
explicitly. The phone error mapping and byte-bounded context changes alone would
not fix the model-specific history limit; the desktop adapter change is required.

Physical test run 10 passed 42 unit tests (2.666 s) and 8 UI tests (73.223 s),
including the real LAN wrong-pin test (0.230 s) with positive authentication first.
The saved production identity and trusted peer records were unchanged; the normal
app was reopened afterward. This is actual iPhone-to-CachyOS certificate rejection,
not just a canonical vector or a simulated endpoint.


### Closure validation and deployment checkpoint — 2026-09-27

Local implementation commits:

- `5c3b373b3e25bff7da1ab3e34c0449575026f3a0`: opt-in persistent listener ports,
  exact-interface startup, trusted desktop control and regression tests.
- `3f74e26ef45456747d3b4f17a4112521ef00b298`: fit requester history to the actual
  selected-model context, with oversized-latest-question rejection retained.
- `875dee8004a96c52a8e82fa3ef4a4fc739425383`: mobile discovery recovery, bounded
  history, distinct model errors and physical wrong-pin test.
- `c8a23cf640d8af330be46bbe8a9101735b554349`: real physical cancellation boundaries
  and debug-only isolated pairing acceptance mode.

The desktop-only two-commit patch has SHA-256
`a04585a5c94991da86e264ea0cb6d6b08f38aecac3512d2a4a55f9e8cbba1b83`.
It was verified by applying the original quota patch and both new commits in an
isolated C9.1 baseline worktree, then comparing affected desktop files with the
Mac implementation (no differences). The copy/paste installer requires exact
CachyOS starting HEAD `25e0cf9f9ce5f070456f638b6eba20e608ee0c97`, a clean worktree,
the expected patch digest and a successful applicability check before `git am`.
It creates local commits only. No restart, firewall change, network download,
remote-access setup, push or trust edit is performed by the installer.

The owner reported **PATCH COMMITTED** and returned the complete native
verification summary:

| Native CachyOS check | Result |
| --- | --- |
| Python compile (`olive`, `tests`) | Exit 0 |
| Connect C1–C8 | **253 tests, 93.338 s, OK** |
| Full Python | **1,442 tests, 168.131 s, OK; 8 skipped** |
| Desktop TypeScript | Exit 0 |
| Desktop unit tests | **98 passed, 19 files** |
| Desktop production build | Exit 0 |

This is owner-supplied native terminal evidence, not a claim of remote shell
access. The new exact desktop HEAD and clean status have been requested. The
native full-suite count differs from the Mac checkout because the desktop-only
patch does not install the mobile-specific Python fixture tests.

Final Mac checks at this checkpoint:

- Python compileall over the checkout passed.
- Full Python: **1,451 run, 1,389 passed, 58 skipped, 2 failures and 2 errors**,
  200.615 s. All four are the previously recorded baseline/platform results:
  Connect Studio descendant reaping timeout, Linux native process readiness on
  macOS, owner-workspace project execution, and installed-JDK discovery.
  Native CachyOS full regression above passed; no all-green Mac Python claim.
- Dedicated pre-context-fix Connect run: 252 tests, one known Studio descendant
  error. After the model-context change, all **45 focused C7/listener tests**
  passed; the final full Python run included the new regression as well.
- Desktop types and production build passed; **98/98 frontend tests** passed
  using canonical `/private/tmp` to avoid macOS `/var` symlink path assertions.
  The initial noncanonical-temp run had two path-equality failures, retained
  in its log; no test assertions were weakened.
- Dedicated persistent Devices UI acceptance passed (2.9 s test / 3.2 s total):
  explicit default-off checkbox, exact saved ports, temporary pairing abort,
  explicit Off and an actual application relaunch remaining Off.
- Existing combined C4/C5/C6 Electron workflow reached the unrelated C6 transfer
  cancellation timing check and failed; its separate expiry/mismatched-comparison
  test passed. The unchanged C9.1 baseline also failed in that workflow's C6
  transfer-progress timing check. These are retained limitations, not a claim
  that the complete Electron end-to-end suite is green. The pairing-abort check
  now observes listener cleanup after the UI acknowledges cancellation instead
  of racing its in-flight IPC; production cancellation logic was unchanged.
- Python/Swift canonical interoperability and signed C4 TLS pairing harness passed.
- Final simulator-SDK build and generic iOS **Release** build passed. No simulator
  runtime execution is claimed. Debug fault-injection and isolated-identity launch
  controls are excluded from Release.

Physical iPhone test run 11 passed **43 unit tests** (8.556 s) and **8 UI tests**
(72.770 s), followed by reopening the normal application with its original
production Keychain identity and pairing. The full cancellation boundary test
ran for 5.866 s against the actual CachyOS model stack using harmless prompts:

| Physical iPhone → CachyOS check | Request evidence and result |
| --- | --- |
| Early Stop immediately after admission | `fb7fef41-9abf-406d-aaf3-2dc2e6137e77`: target `cancelled`, acknowledgement 0.092667958 s; repeated cancel remained `cancelled` |
| Completion-race Stop | `ceba172e-6552-4a45-a25a-f04c0691b259`: complete real answer polled, immediate cancel preserved `completed` |
| Connection lost during cancellation | `b7ad252a-3201-48fa-b667-5ca98198028b`: actual C7 cancel written, then the phone closed its socket without awaiting acknowledgement |
| New request after that loss | Fresh exact-pin TLS connection, desktop status returned idle, and `48f17696-ebbc-47e2-9add-977604f0f7ba` completed the hash-function request |
| Wrong expected certificate | Positive real pinned handshake followed by required `certificateMismatch`; no TCP-timeout substitute; saved trust and identity unchanged |

The loss test deliberately cuts the phone's actual Connect socket; it does not
claim to time a physical Wi-Fi toggle within the 93 ms acknowledgement window.
No uncertain start is replayed. Target cancellation acknowledgements and admission
of the new real request exercise actual provider/task/residency release. No
independent GPU telemetry is claimed.

A debug-only pairing acceptance launch mode has separate app-scoped Keychain,
trust and draft storage and a visible test-identity banner. This permits real
owner denial/phone abort checks without unpairing or resetting the working phone.
It is now being used for the owner-assisted negative pairing checks recorded
below. Cleanup is explicitly confined to that test namespace; normal production
state is retained.

**Gate status at this checkpoint:** accumulated Fast Chat and the deployed
Welcome label still required real-device confirmation. Both subsequently passed
in the final closure record below.

### Saved endpoints confirmed by owner

After restarting the rebuilt desktop and following the opt-in setup instructions,
the owner reports the Devices UI displays **Connect port 44795** and **Pairing
port 34537 opens only during pairing**. The supplied terminal output confirms
desktop HEAD `00940235d5edf24c33a294555f107f970d1b34e9` on
`feature/olive-mobile-c9`, with empty `git status --short`.
This is the deployed desktop-only history; it is not the Mac mobile branch HEAD.

The requested one-time UFW replacement is inbound TCP on `enp111s0`, source
phone `192.168.10.37`, destination desktop `192.168.10.196`, exact ports 44795
and 34537, followed by deletion of the superseded identically scoped 54981 rule.
Both saved-port rules persist. The pairing listener remains session-bound even
though its firewall rule persists. The owner returned **Rule added** for each new
port and **Rule deleted** for 54981. Verbose UFW output confirms active filtering,
low logging, **deny incoming / allow outgoing / routed disabled**, exactly the
two phone/interface/address-scoped OLIVE TCP rules, and the existing KDE Connect
1714–1764 TCP/UDP IPv4/IPv6 allowances. No other OLIVE port rule remains.

The initial post-rule check **passed, owner-observed**: after instructions to
leave the phone open without tapping Reconnect, the owner reports it connected
and answered the explicit multiplication prompt with **391**. Successful Chat
establishes Remote AI admission; no separate permission-label observation or
numeric connection duration was supplied. No server IP or port is configured in
the mobile app.

### Unattended restart passed; stale Welcome label found

Following instructions to quit OLIVE while leaving Connect enabled, wait one
minute, reopen normally, and avoid both firewall edits and phone Reconnect, the
owner reports: **“it reconnected automatically and as soon as olive ran it
connected”**, and Chat answered again. This passes the owner-assisted unattended
application-restart/automatic-reconnect check on the selected LAN. No numeric
duration or before/after listener PID output was supplied; “as soon as” remains
qualitative evidence, not a measured TLS or startup duration. No firewall change
was requested or reported during this restart.

The owner also observed Start → Your devices displaying **iPhone paired · Connect
is off** while phone Chat worked. Source diagnosis: `Welcome.tsx` fetched
`connect.snapshot` only once, 300 ms after mounting, before saved network startup
could finish; the app's shared poll previously began only after entering Home.
The correction runs that existing non-overlapping five-second poll throughout
Welcome and Home and passes the same snapshot to Welcome. Pairing and live
connection remain distinct: a paired offline phone with the listener on says
Connect is on; an authenticated online peer says connected. Unknown/failed
status is not represented as an explicit Off. No transport or permission change.

The fix is committed as `f96b7f3e587bb91bae4931a5fa36070a6621c803`.
Fresh Mac validation: type checking and production build pass; **101 desktop unit
tests across 20 files pass**. The Electron regression uses actual paired Python
Connect peers and verifies Off → On → Connected → Off while Welcome remains
open: **1 passed, 16.9 s test / 17.2 s total**. No Python or iOS runtime changed.
The desktop patch SHA-256 is
`3fd635d269c174e990f23736c686f5340789f4bff61faf7ce62b700d6bed3153`;
its installer requires the recorded clean desktop `00940235` checkpoint and
runs fresh native frontend type, unit and build checks. Deployment is pending.

### Real desktop pairing denial with separate identity

The physical phone was explicitly launched in the debug-only pairing acceptance
namespace. The owner scanned a fresh desktop QR, reached the comparison step,
and clicked **Cancel on the desktop before confirming on either side**. The
owner reports that the desktop paired-device list **stays unchanged** and the
phone displays **“Connection lost. The request will not be sent again
automatically.”** This records the actual close/error behavior, not a claimed
typed denial message. No new desktop trust was added. The working production
pairing is retained in its separate namespace.

### Real phone-side pairing abort and return to normal identity

On a fresh desktop QR attempt, the owner cancelled on the physical phone before
confirmation. The owner reports that this **also cancelled on the desktop**, the
phone **returned to an unpaired state**, and the desktop paired-device list
**remained unchanged**. Both owner-assisted pairing cancellation directions have
now passed without adding trust.

The app was subsequently launched successfully with the debug-only
`--c92-cleanup-pairing-check` flag. This requests removal of only the isolated
acceptance Keychain accounts, preferences and directory, and opens the normal
production identity/trust store. The owner subsequently confirms the phone again
shows **Connected / Remote AI Allow**, demonstrating return to the preserved
working pairing. This observation does not independently certify every
best-effort cleanup operation.

The first Start status installer attempt failed in Fish with unknown command
`L npython3`; inspection found the same stray prefix in the Mac text file.
The command was regenerated from the prepared installer, with its one-line shell
argument structure and decoded Python syntax checked. No desktop patch success
is inferred from the failed attempt. The corrected handoff is
`/tmp/OLIVE-C92-START-STATUS-CLEAN.txt`; native frontend results remain pending.

### Start status patch installed and native checks passed

The corrected installer applied successfully on CachyOS as
**`698b002e13ba76aef8bcd1a391b33280764e1bad`**, with subject
`desktop(connect): refresh Welcome status as the saved listener starts`.
The owner returned the complete **ALL START STATUS CHECKS FINISHED** summary:

- Desktop TypeScript check: **PASS**.
- Desktop unit tests: **101 passed across 20 files**, duration **423 ms**.
- Desktop production build: **PASS**.

These are fresh native CachyOS results for the UI-only follow-up. The earlier
native Python compile, Connect **253 tests** and full Python **1442 tests with
8 skipped** remain the applicable backend regression: this patch changes no
Python runtime. No firewall, identity or permission changes were made by the
installer. Normal desktop restart with the phone open is now requested to verify
the corrected Start label and automatic reconnection in the deployed build.
Accumulated Fast Chat acceptance remains pending; C9.2 is not yet marked complete.


### Final real-device confirmation and C9.2 closure — 2026-09-27

After successful installation and native regression of desktop
`698b002e13ba76aef8bcd1a391b33280764e1bad`, the owner was asked to restart OLIVE
normally with Connect enabled, leave the phone open, and verify Start → Your
devices within five seconds. The second requested check used **Fast**, eight
sequential requests in one conversation for “Explain hash functions in about
250 words, with one simple example,” waiting for each response, then
“What is 17 × 23?” without reconnecting. The owner reports **“ok it works and
connects after 5 seconds, the answer i got is 391.”** This is owner-observed
acceptance of those requested checks. No per-turn transcripts, exact response
lengths, role receipts or independently instrumented five-second timing were
supplied; none are fabricated. The earlier native context-fitting regression
separately verifies keeping recent complete turns and rejecting an oversized
latest question.

The corrected Start label, restart recovery and accumulated Fast conversation
check now pass. The normal phone identity previously returned to **Connected /
Remote AI Allow** after the isolated negative pairing checks. There are no
remaining C9.2 functional acceptance items in the completion gate.

Final firewall configuration remains the owner's supplied active UFW policy:
**deny incoming / allow outgoing / routed disabled**, unchanged KDE Connect
rules, and only these OLIVE inbound TCP exceptions:

| Interface | Source phone | Destination desktop | Saved port | Listener lifetime |
| --- | --- | --- | --- | --- |
| `enp111s0` | `192.168.10.37` | `192.168.10.196` | `44795` | Enabled Connect main listener |
| `enp111s0` | `192.168.10.37` | `192.168.10.196` | `34537` | Explicit bounded pairing session only |

No new firewall changes were requested for either final restart. The mobile app
continues to discover endpoints; these addresses/ports are host acceptance
configuration, not mobile constants or authentication credentials.

Final implementation checkpoints are Mac `f96b7f3e587bb91bae4931a5fa36070a6621c803`
and deployed desktop `698b002e13ba76aef8bcd1a391b33280764e1bad`. The final local
closeout commit contains only this report and the project journey. Resolve its
exact hash with the `FINAL_HEAD` command above; it is also supplied in the handoff.
No push, merge, tag or release was performed.

### Measurement and scope limits at closure

- Discovery: measured Nearby appearance **1.098 s** in the physical test, excluding
  initial permission/app bootstrap. Pairing and initial TLS/session durations
  were not separately measured.
- First Chat reply: owner described it as instant; first-visible and complete
  response latencies were not instrumented. Wire polling delivers real incremental
  events; no timer-generated token presentation is used.
- Stop: owner diagnostic **0.09 s**; physical early-cancel test **0.092667958 s**.
  These are acknowledgement timings, not independently measured GPU teardown.
- Foreground reconnect: owner described almost instant. Final desktop restart
  reconnect: owner-reported **about five seconds**, including app startup and
  discovery rather than a separately measured TLS handshake.
- DHCP remains automatic. If either scoped address or the selected interface
  changes, host admission must be reviewed; no broad subnet rule or silent
  fallback is added. Process restart on the tested LAN requires no firewall edit.
- No simulator runtime is installed; simulator-SDK and generic device builds pass
  and physical iPhone tests pass. Mac full Python retains the four recorded
  baseline/platform failures; native CachyOS full Python passes. The complete
  Electron end-to-end suite is not claimed green because of the recorded C6
  transfer timing behavior also seen on baseline.
- Expiry/malformed-message checks use protocol and isolated integration tests;
  wrong-peer rejection also ran against the real LAN desktop. No spoofing
  campaign against unrelated LAN devices was performed.
- The public-offer clipboard failure from initial acceptance remains a recorded
  fallback limitation; the normal real QR pairing path passes. Broader Chat
  synchronization, files/Studio/task UI, notifications, cloud accounts, relay,
  C10 and OLIVE OS remain outside C9.2.
