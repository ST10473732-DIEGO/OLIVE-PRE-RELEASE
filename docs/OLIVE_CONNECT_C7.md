# OLIVE Connect C7 — Remote AI

C7 lends local-model **text inference capacity**, not machine authority. The
requesting desktop selects a paired device separately from its public OLIVE
preset. The target generates visible text using its existing local runtime. The
requester renders and persists the answer in its existing Chat. Connect stays
Off at startup; pairing and sync/file permissions enable no inference.

Starting checkpoint: `a9cd078`, the completed C6 portable repair, on
`feature/olive-connect-c7`. The branch and clean worktree were checked before
edits; C6 ancestry was verified locally. C1–C6 reports, platform reports, Chat,
semantic/action routing, native persistence, approval, TLS and model ownership
were inspected. No C6 transfer behavior was changed.
Implementation and acceptance harness commit: `6967117`.

## Authority and public presets

The existing capability **`models.remote`** now means Remote AI. Missing
permission is Off (`deny`); Ask and Allow are independent per paired identity.
Pairing identifies a device. C3 mTLS proves possession of its pinned identity.
Permission admits this narrow capability. Trusted local Ask approves one exact
request. The local preset catalog selects the actual model. None grants tools.

| Public ID | Public preset | Existing target mapping |
| --- | --- | --- |
| `fast` | OLIVE FAST | `qwen3:8b` |
| `normal` | OLIVE NORMAL | `gpt-oss:20b` |
| `max` | OLIVE MAX | `qwen3-coder:30b` |

Mappings and local defaults are unchanged. The **target's** PresetCatalog and
ModelCapabilityRegistry resolve availability. Current inventory is checked again
before generation. Missing models return `model_unavailable`; there is no pull,
download, substitution, alternate target or local-answer fallback.

Remote **DEEP is unavailable**: its existing semantics include bounded document
retrieval/extraction and optional vision. C7 does not expose target-private
sources or silently reinterpret DEEP. **REIMAGINE is excluded**; no ComfyUI,
images, video, media generation or remote vision capability is added.

## Dedicated protocol

`olive-inference/1` uses C3 frame types **9 / 10** (request / response). C1,
C5 and C6 retain their own versions, limits and dispatch. Ollama HTTP is never
forwarded. Older peers may reject the new frame types; no compatibility bypass
or unauthenticated fallback exists.

Exact envelope fields:

```
request_id, protocol_version, source_device_id, target_device_id,
job_id, operation, arguments, timestamp, expires_at
```

IDs are canonical UUIDs. The TLS channel supplies source identity; a claimed
source or target mismatch fails. Strict duplicate-free UTF-8 JSON rejects unknown
fields, invalid types, booleans as integers, non-finite numbers, invalid roles,
invalid timestamps and unsupported versions. Frame length is bounded before body
allocation. No peer-supplied system/developer fields, model tags, provider URLs,
tools, function schemas, executable paths, commands or approval flags exist.

| Operation | Exact arguments |
| --- | --- |
| `start` | `preset`, `messages`, `input_fingerprint`, `max_tokens`, `max_output_bytes`, `seconds` |
| `poll` | `after` (last accepted sequence number) |
| `cancel` | Empty object |
| `status` | Empty object |

For start, request ID equals job ID. Other operations have separate correlation
IDs. Messages contain exactly `role` (`user` or `assistant`) and `content`;
the final message must be user. SHA-256 of canonical messages must match the
input fingerprint. The full start-envelope fingerprint additionally binds the
target, preset, bounds, IDs and times.

Authenticated status returns exactly FAST/NORMAL/MAX availability booleans,
the target's effective permission for this peer, and busy/idle. It requires
pairing and live authentication but can report Off without inference permission.
No raw tags, endpoints, hardware, GPU details, paths, secrets or model inventory
enter this status. mDNS is unchanged and contains no model metadata.

## Context, runtime and actions

The requester deliberately shares up to the last 24 complete visible Chat
messages, including its new user message. The UI explains that window. A request
over the byte bound fails rather than truncating an individual message. Hidden
reasoning, summaries, custom system prompts, notes, tool state, credentials,
Memory/Knowledge metadata and unselected files are excluded. Attached documents
or images require removal before remote sending; C7 never reads/transfers their
bytes. C6 Inbox is not an inference source.

`RemoteInferenceRuntime` takes the existing preset catalog and OllamaService.
It does **not** use GenerationPipeline's Memory, retrieval, preferences, files,
documents or summarizer. Static trusted OLIVE system behavior plus text-only
framing precedes the explicit messages. There is no target Agent, tool registry,
Studio, Mail, browser, screen, clipboard, filesystem or permission dispatcher.
Text asking for commands, secrets, local files or external communication remains
text; model output is never parsed as executable authority.

The requester's existing semantic interpreter still separates answers from
actions. With a remote target selected, only `conversation.answer` proceeds to
remote inference; actions, document access and Research explain that the user
must select This device. No action is converted into a claimed remote completion.
The existing local classifier may itself require a locally installed model for
requests outside its deterministic answer fast path. Remote inference does not
replace that classifier or grant its output execution authority.

OllamaService streams visible `message.content` only; provider thinking,
reasoning, tool calls and internal metadata are not transported. Existing
completion-marker and output-length failure checks remain. The runtime only
accepts a loopback Ollama host and reuses its existing client, ModelResidencyService
lease, model unloading, keep-alive and optional external GPU handoff guard.

**No Ollama LAN exposure:** no bind/proxy change, no arbitrary API route, no new
server. Existing `LocalOllamaRuntime` still owns only a process it started and
binds owned Ollama to `127.0.0.1:11434`. External servers are not killed. C7 has no
model installation path. Host acceptance used the existing installed models.

## Approvals and execution boundaries

Ask reuses C4 ConnectApprovals, Host.confirm, the pending registry and
`approval.respond` ID/fingerprint check. The renderer presents, but cannot create
approval authority. The local preview shows paired name, public preset, message
count and input bytes, without prompt text. All peer labels render as escaped
text. Allow once leaves Ask unchanged; there is no Remember or remote approval
field.

Approval binds authenticated public fingerprint, source/request/target, full
immutable envelope fingerprint, preset/input/limits/expiry and paired-record
revision. Exact start retries wait for that approval; changed duplicates reject
and withdraw pending approval. Denial invokes no model and occupies no active
generation slot. New IDs require new approval. The durable receipt prevents a
second execution after Allow once completes.

Queued jobs recheck authority and the committed receipt before transitioning to
starting. Permission writes conservatively invalidate that peer's pending and
running jobs, including changes to its other permission rules. Every accepted
output batch rechecks current trust, policy and saved permission rules. The short
C3 framed response write shares the device repository transaction with this
check: a policy removal cannot commit before an already-authorized output write
finishes. No subsequent output uses old authority. Existing C3 write deadlines
still bound this transaction; it is not an indefinite generation transaction.
Blocking transport/repository synchronization runs off the model/UI event loop.

## Bounds, scheduling and timeouts

| Resource | Bound |
| --- | --- |
| Inference frame payload | 72,000 bytes |
| Messages / accepted roles | 24 / user and assistant only |
| One message / total input UTF-8 | 16,000 / 48,000 bytes |
| Context estimate | Newest whole requester turns fitting the existing character/4 estimate, static framing and output reserve within the target's effective local context window; latest question alone must fit |
| Requested generated tokens | 1–2,048 |
| Visible output | 1–64,000 UTF-8 bytes, enforced independently of token limits |
| One visible event | At most 4,096 UTF-8 bytes |
| Pending visible events | 8 per job; bounded provider backpressure |
| Active remote generation | 1 globally |
| Waiting generation jobs | 2 globally; busy when full |
| Peer jobs | 1 total active, queued or awaiting approval per peer |
| Pending Ask | 4 globally, also within C4's shared 32-approval registry |
| Transient jobs including completed tails | 32 globally |
| New admitted/admission-attempt requests | Capacity-based; no separate per-minute question quota (C9.2 usability follow-up) |
| Rate-accounting identities | 256, no eviction to reset abuse accounting |
| C7 request/response frames | 600 per peer/minute across reconnects |
| Durable metadata receipts | 10,000, fail closed without eviction |
| Generic Activity | Existing latest 1,000 events; no per-token writes |
| Request/approval lifetime | At most 120 seconds; five seconds future-clock tolerance |
| Queue wait | 30 seconds, also checked against immutable start expiry |
| Model start / provider inactivity | 60 / 30 seconds |
| Generation including model start | Requested 1–120 seconds |
| Client stream wait after acceptance | 155 seconds maximum (queue + generation margin) |
| Poll without requester acknowledgement | 15 seconds before cancellation |
| Requester poll cadence | 250 ms, one exchange in flight |
| Cancellation exchange / actual ownership release wait | 5 / 5 seconds |
| Disconnect grace | None; cancel immediately when channel loss is observed |
| Terminal request/tail retention | 30 seconds in RAM only; cleared on disable |

Requests use preset temperature and thinking defaults. Peers cannot select GPU
layers, loading options, arbitrary `num_ctx` or runtime internals. Byte and token
bounds are independent; the existing token estimate is heuristic, not tokenizer
proof. Output overflow stops before the offending delta; already visible content
stays incomplete.

No autonomous scheduler exists. Remote work waits while local residency is
active or has waiters. A running remote lease can delay local Chat by its bounded
lifetime; local work then uses the same lease. There is no remote model preloading,
infinite residency or claim of instant VRAM release. Target Devices shows active
remote jobs and Stop. This is bounded priority, not preemptive GPU isolation.

## Streaming, cancellation, replay and persistence

This is real incremental streaming via bounded **pull batches**, not one blocking
model request or one packet per character. Start returns an explicit state;
poll returns ordered `{sequence, text}` events and current state. Batches flush
after 256 characters, 100 ms observed during provider output, or completion;
larger output is split conservatively. Acknowledgements release the old tail.
The receiver accepts only consecutive sequence numbers and bounds aggregate
visible bytes. Unsolicited/late replies cannot attach to a Chat; changed job
identity and invalid response fields fail validation. The requester stops polling
at terminal state, so completion cannot append another answer.

States are awaiting_approval, queued, starting, streaming, completed, cancelled,
failed, timed_out, connection_lost and revoked. Errors remain bounded categories:
permission_denied, model_unavailable, busy, rate_limited, input_too_large,
output_limit, generation_timeout, cancelled, connection_lost, inference_failed,
and strict identity/schema/replay errors. Known guidance passes the existing
bridge error allowlist; raw exceptions, paths and provider diagnostics do not.

Requester Stop sends cancellation for its exact peer/job. Target Stop uses the
trusted local Devices route. Both cancel the runtime coroutine, close the existing
provider stream and release its residency lease. Repeated cancellation is inert.
Cancel responses, terminal stream responses and the trusted target Stop call wait
for the actual task's release acknowledgement, outside service/database locks.
Logical terminal state suppresses output immediately; it alone is not proof of
runtime release. The five-second release deadline returns a bounded timeout on
failure instead of a successful cancellation acknowledgement.
Another peer cannot cancel, poll or recover this job. Connection loss cancels the
exact channel's jobs, so old cleanup cannot cancel work on a replacement channel.
Revocation also closes C3 and prevents fresh authentication and result recovery.
Unacknowledged work is cancelled after 15 seconds even if a socket remains open.
Shutdown/Connect disable cancel jobs, clear transient context and stop monitoring;
ordinary async shutdown waits for actual active ownership release.

The `(authenticated peer, job ID)` durable ledger records the whole-request hash
before invocation. Exact duplicate start returns the same state and never starts
another model run; changed content/preset/limits reject. Claims survive restart;
unfinished receipts become `connection_lost / request_indeterminate`. Lost final
acknowledgements **do not rerun** inference. Full completed-result recovery is
not implemented: duplicate start returns terminal metadata only. The same original
channel may drain its unacknowledged transient tail for at most 30 seconds, with
current authority. No distributed stream resume exists. Explicit retry is a new
request and follows current permission/quota policy.

Only the requester owns durable Chat. ChatController uses its current stream
events, atomic ChatRepository, IDs, regeneration branches, and completion_state.
One assistant message receives additive bounded provider metadata: OLIVE Connect,
preset, paired device ID/name and request ID. Interrupted visible output is
`incomplete`, not complete; no output creates no fabricated assistant answer.
Legacy text-only branch switching clears attribution because it cannot prove
which device produced that branch. The target creates no conversation.

C5 remains independent. Selected Chat may subsequently sync under its existing
permission; incomplete messages retain the existing hold/exclusion behavior.
C5's current text-only schema still excludes provider attribution metadata.
No native persistence migration is needed for the existing additive provider
dictionary; `remote_inference_v1` is a new metadata-only repository table.

## Chat and Devices UI

The existing Chat header adds **Run on** separately from Model: This device or a
paired device, with Online, Ask, Off, Offline, Model unavailable, Busy or Revoked
status. Selection is per conversation for the current desktop session. Restart
defaults to This device; failure/revocation within a session never changes the
chosen target. Explicitly selecting This device is the local fallback decision.

Chat retains its current renderer, Stop, conversation switching and error path.
It shows Thinking on the named peer and retains Answered by peer / OLIVE preset.
No hardware/token-rate animation is invented. Devices enables the existing
Remote AI permission row and adds coarse local preset availability, privacy-bounded
active jobs and Stop. The normal UI never shows raw tags. Narrow local bridge
methods are `chat.run_on`, `connect.model_targets`, `connect.inference_stop` and
the existing Chat/Devices/approval routes; no raw model/channel/vault API is added.

## Threat model

| Threat | Classification | Mechanism / remaining boundary |
| --- | --- | --- |
| Malicious or compromised paired peer | Partially mitigated | Exact TLS identity, Off default, narrow compute-only schema, per-peer quotas; an authorized peer can still consume its finite allocation |
| Prompt injection / generic tool escalation | Mitigated at execution boundary | No target tool/context/action dependencies, trusted static system framing, text-only output; model prose accuracy is not guaranteed |
| Resource exhaustion / GPU denial of service | Partially mitigated | One remote lease, two queued jobs, per-peer admission/frame rates, input/output/lifetime bounds and local Stop; GPU/OS scheduling is not a sandbox |
| Request replay / changed duplicate | Mitigated | Durable committed hash claim, changed-request denial, no second execution |
| Result replay / stream injection | Mitigated within protocol | C3 integrity, exact correlation, consecutive event numbers, strict content-only output, no unsolicited Chat append |
| Third-peer hijack | Mitigated | TLS-bound peer/job namespace and exact channel binding; display names confer no authority |
| Connection drop | Mitigated within lifecycle | Immediate observed-loss cancellation, 15-second acknowledgement deadline, no resume |
| Revocation during inference | Mitigated | Persistent tombstone, C3 close, coroutine cancellation, per-batch authority transaction |
| Permission change during inference | Mitigated | Queue/start recheck, invalidation, current rules per batch and serialized transmission |
| Oversized prompt/output | Mitigated within application bounds | Pre-parse frame limit, exact message bounds, independent streamed-byte limit and bounded buffers |
| Unknown model / substitution | Mitigated | Public enum only, target preset resolution/current inventory, no pull/fallback |
| Target-private context / secrets / environment leakage | Mitigated at C7 context boundary | No retrieval/files/Memory/Knowledge/Mail/browser/screen/clipboard/tool access; only explicit text plus static framing |
| Hidden reasoning leakage | Mitigated for current provider contract | Existing OllamaService consumes visible content only; reasoning/tool metadata excluded from protocol, persistence and Activity |
| Approval self-grant / stale approval | Mitigated | Strict schema, C4 trusted local registry and complete binding, no remote approval field, permission revision invalidation |
| Local profile/OS compromise or rollback | Deferred | Existing C1–C6 endpoint trust boundary; no hardware anti-rollback or same-user isolation claim |
| Arbitrary secrets typed into visible Chat | Partially mitigated | Explicit target/context notice and bounded visible-only sharing; C7 is not automatic secret redaction |

## Validation and known limitations

Portable tests replace only the inference engine under the real OllamaService.
The deterministic engine controls multiple deltas, delayed/long generation,
failure, cancellation and overflow; inventory controls unavailable presets. It
asserts tool-free invocation and emits hidden-thinking/tool metadata to verify
filtering. It exists only under `tests/`; no production flag/bridge/remote message
can enable it. Tests retain actual TLS, C2 identities, native repositories, Host
approval, permissions, request/replay/rate handling and model residency.

The two-process portable test proves Off, Ask/Deny with zero calls, exact Allow
once, requester-only native persistence/attribution, Allow, cancel and cleanup.
Additional tests cover hostile fields, context exclusion, action refusal, sequence
validation, queued/running permission changes, third-peer isolation, missing
models, provider privacy, receipt recovery, quotas and model transitions.

Real CachyOS acceptance uses two ordinary complete ServiceContainers in separate
processes, synthetic vault identities and isolated profiles. Actual existing
FAST/NORMAL/MAX each returned “OLIVE remote inference works.” The real target
called exactly `qwen3:8b`, `gpt-oss:20b`, `qwen3-coder:30b`, respectively. Deny
invoked none; permission remained Ask after each Allow once; requester inference
count was zero; target Chat stayed empty; shutdown passed. No model download was
performed. Native Electron also exercised real remote FAST, real cancellation,
incomplete text and local Chat afterward.

Final local evidence (2026-09-20, CachyOS; project Python 3.14 venv):

| Check | Result |
| --- | --- |
| Full Python discovery | 1,050 run: **1,042 passed, 8 Windows platform skips, 0 failures** |
| Exact Connect workflow command, C1–C7 | **196 passed**, 0 skipped, 0 failures |
| C7 subset, including independent processes | **31 passed** within the above totals |
| Frontend unit tests | **49 passed in 14 files** |
| Frontend typecheck / lint / production build | All passed |
| Focused real Linux Electron regression | **10 passed**: Chat/Connect, Devices pairing/approval/C6 files, OLIVE GO, Linux auto/Wayland, L3 reminders, Studio and media smoke |
| Final expanded C7 Electron check | **1 passed**: incoming Ask/Deny/Allow once, target Devices Stop, outgoing streaming/Stop, incomplete persistence, local Chat and no offline fallback |
| Final real-model Electron check | **1 passed**: remote FAST, real cancellation and local Chat afterward |
| Final two-process real FAST / NORMAL / MAX | All completed on their exact existing target models; Deny zero calls, Ask unchanged, target Chat empty, clean shutdown |
| Repository-source compilation | **641 Python files passed**, using tracked and unignored new source files |
| Literal `python -m compileall -q .` | Exit 1 solely for the known PySide6 Android Jinja `__init__.tmpl.py` inside the venv; no OLIVE source failure |
| Final diff whitespace / data review | Passed; no user conversations, credentials, model files or personal absolute paths added |

These counts are separate runs, not additive unique-test totals. The full Python
run still reports the pre-existing 26-uncollectable-object shutdown
ResourceWarning. Electron reports the existing NO_COLOR/FORCE_COLOR environment
warning. Neither is hidden or counted as a new C7 pass. Actual backend exits,
stream/lease release and owned Ollama shutdown passed; final process inspection
found no remaining C7 worker or Ollama process.

Detailed local logs are temporary `c7-python-final.log`, `c7-connect-final.log`,
`c7-frontend-final.log`, `c7-desktop-final.log`, `c7-desktop-target-stop.log`,
`c7-desktop-live-final.log`, `c7-live-final.log` and
`c7-compileall-final.log`. Screenshots are in ignored `artifacts/connect-c7/`.
No test profiles or prompt/response archives are committed. During acceptance,
the real protocol caught cancellation after a denied start closing its channel;
the cancellation handling was corrected and the complete retry flow retested.
The real renderer also caught bounded remote reasons being hidden by the bridge
error filter; the fixed-message allowlist now preserves those reasons.

The GitHub workflow retains Ubuntu and Windows and `fail-fast: false`; it now
includes C7 using loopback TLS, synthetic vaults and the deterministic engine.
No hosted runner success or native Windows GPU acceptance is inferred from Linux.
Hosted Ubuntu/Windows verification requires a later authorized push. Physical
two-machine LAN/firewall, arbitrary provider behavior and older-peer negotiation
remain outside this host acceptance. Local semantic classification dependency,
heuristic token sizing, bounded non-preemptive residency, manual retry, metadata
ledger capacity and absent completed-answer recovery are explicit limitations.

Reproduce with the project venv, existing Node toolchain, and the exact command
in `.github/workflows/connect-portable.yml`. Full checks are `python -m unittest
discover -s tests -v`, frontend test/typecheck/lint/build, source-only compilation
and literal whole-tree compileall separately. Opt-in live acceptance is
`OLIVE_START_OLLAMA=1 python scripts/check_connect_inference.py`; existing Ollama
must be on PATH. Electron C7 cases are `connect-inference.spec.ts` and opt-in
`OLIVE_C7_LIVE=1 OLIVE_START_OLLAMA=1 ... connect-inference-live.spec.ts`.

Next stages remain **C8 Remote Studio**, **C9 OLIVE Mobile**, **C10 Internet
direct / relay**. None is implemented here. No remote shell, project execution,
Desktop Control, browsing, Research, Mail, media, target-private retrieval or
automatic multi-device scheduling is exposed by C7.

## Windows portable cancellation repair

The first hosted run was reported as Ubuntu green and Windows 195 passed / one
failure out of 196. The failing two-process assertion was
`assertFalse(call(1, 'counts')['active'])`. This repair is local evidence only;
hosted Windows must verify the repair after a separately authorized push.

### Root cause and synchronization

`counts.active` is exactly `bool(service.inference.active)`. It is not a logical
request-state flag. `_admit` sets it to the owning job; `_run` clears it through
`_release` after closing the remote runtime stream. OllamaService closes the
engine stream before leaving ModelResidencyService's lease.

Previously, the cancel dispatcher committed `cancelled`, called the
`run_coroutine_threadsafe` concurrent Future's `cancel()`, and immediately sent
the response. That Future becomes cancelled before its actual asyncio task has
finished unwinding. The fixture's engine `stopped` event was also too early to
prove outer lease/job release: it is emitted inside the engine generator's
`finally`. Thus both the response and that fixture event could precede
`active = None`. No cross-thread/process happens-before relationship prevented
the Windows pipe command from observing the still-active job. Linux usually
completed cleanup before that observation. There is no evidence requiring a
Windows-specific event-loop, pipe or provider workaround.

A test-controlled engine cleanup Event reproduced the same premature response
on Linux before the fix: the response was `cancelled` while active ownership
remained true. The original assertion was preserved and strengthened.

Each scheduled job now has a `threading.Event` acknowledgement set by the actual
asyncio Task's done callback, after provider close, residency release, active-slot
release and task exit. The scheduled-owner registry also covers work cancelled
before its coroutine starts. Job futures are not prematurely cancelled; a shared
helper requests actual Task cancellation once, and repeated cancellation does
not interrupt asynchronous provider cleanup a second time.

The protocol waits for this event before sending a terminal result. It commits
the logical cancellation immediately to stop output, releases its repository
transaction and service lock while waiting, then rechecks current authority and
rebuilds the result inside the existing transmission transaction. Target Stop
waits for the same event. Disconnect, revocation, permission removal, monitor
expiry, Connect disable and shutdown use the same cancellation helper and job
completion signal. Authority removal remains immediate; shutdown explicitly
awaits outstanding owners. A release timeout is a bounded failure, not a false
successful completion. Counts continue to report actual state.

### Regression evidence

The engine-only fixture can hold its `finally` behind an `asyncio.Event` while
the real C3 protocol and model-service/residency stack remain running. Tests prove
requester cancellation and trusted target Stop remain pending while cleanup is
held, ownership stays visible, and release permits completion. A repeated
invalidation cannot skip the held cleanup. Existing disconnect, revocation and
permission tests now also assert the release signal and empty task/owner state.

The ordinary-process command waits for the existing requester Chat task's full
cancellation/persistence flow, just as the original test's subsequent `wait_chat`
did. Immediately afterward the regression asserts active false, residency
inactive, zero queued jobs, zero inference tasks and provider stopped, without
waiting for the earlier engine event. It checks no subsequent stream event and
a successful next inference. The separate processes, real TLS, approvals,
permissions, quotas and native Chat ownership are unchanged.

The strengthened ordinary-process acceptance passed **50 consecutive independent
repetitions**, each with fresh processes/profiles and unchanged quotas, in 97.025
seconds. The runner was fail-fast; no failing acceptance was retried or counted
as a pass. An initial stdin-based runner could not spawn its child main module;
that launch error was excluded and replaced by a spawn-compatible `python -c`
runner. The intentionally failing pre-fix reproduction is also excluded from
passing regression totals.

Final local repair validation (project Python 3.14 venv, Linux):

| Check | Result |
| --- | --- |
| C7 inference and ordinary-process tests | **33 passed**, no skips/failures |
| Exact C1–C7 Connect workflow command | **198 passed**, no skips/failures |
| Full Python discovery | **1,052 run: 1,044 passed, 8 platform skips, 0 failures** |
| Frontend tests | **49 passed in 14 files** |
| Frontend typecheck / lint / build | All passed |
| Source compilation | **641 repository Python files passed** |
| Literal whole-tree compileall | Only the known venv PySide6 Android Jinja template failure; no OLIVE source failure |
| Ordinary-process stress | **50/50 passed**, separate from the suite totals |

The existing 26-object Python shutdown ResourceWarning remains documented; it
is not counted as an ownership-release pass. Temporary evidence logs are
`c7-cancel-red.log`, `c7-cancel-repeat-50.log`, `c7-cancel-c7-final.log`,
`c7-cancel-connect-final.log`, `c7-cancel-python.log`, frontend/typecheck/lint/build
logs with the same prefix, and `c7-cancel-compileall.log`. No profiles or secrets
are included in the repair diff. No hosted repair success is claimed.

This is a lifecycle-only change: no permission defaults, approval bindings,
identity checks, fingerprints, model mappings, quotas, tool/context boundaries
or Ollama exposure policy changed. No C8 work is included.


### C9.2 repeated-Chat context correction

A real Fast request failed with `input_too_large` after accumulated history:
10,429 input bytes, no output, 71 ms. This is distinct from the removed request
admission quota. Model-specific context can be smaller than C7's wire-size limit.
The compute-only adapter now omits oldest complete requester turns until the
newest suffix plus static framing and requested output reserve fits the actual
model window. The latest user question is never split or discarded. If it alone
does not fit, `input_too_large` still rejects before provider execution. Wire
limits, request fingerprints, permissions and receipt semantics are unchanged;
no target-private context, fallback model or extra request is introduced.
Regression retains the oversized-single-question rejection and adds accumulated
history followed by another request on the same channel.

### C9.3 remote FAST answer-reserve correction

A brand-new iPhone FAST chat failed with `input_too_large`, even for "hi". Remote AI
reserved the full 4,096-token answer cap inside FAST's 4,096-token role window. The
remote runtime now applies Desktop Chat's rule through the shared
`reserve_ceiling()` (an answer reserves at most half the window), for both the
context budget and `num_predict`. NORMAL/MAX budgets, wire limits and the
oversized-request rejection are unchanged. Regression: `tests/test_remote_fast_context.py`
(Direct and forced World). See `docs/OLIVE_CONNECT_WORLD.md` §14.
