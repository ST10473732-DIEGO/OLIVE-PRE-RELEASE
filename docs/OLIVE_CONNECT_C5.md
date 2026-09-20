# OLIVE Connect C5 — structured record synchronization

C5 adds manual, incremental, bidirectional record exchange over the existing C3
mutually authenticated TLS channel. Pairing and startup enable **nothing**.
`sync.tasks`, `sync.calendar`, `sync.reminders`, and `sync.chat` each use the C1
per-device Off / Ask / Allow policy. There is no master device, background poll,
cloud service, remote tool dispatch or database/file transfer.

## Native data and exclusions

| Wire kind | Native repository | Portable content |
| --- | --- | --- |
| `task` | PersonalStore | Native validated task fields, including completion/reopening, due kind/timezone and relationships |
| `calendar` | PersonalStore | Calendar identity, title, colour and visibility, required by events |
| `event` | PersonalStore | Native validated event, timezone, all-day boundaries, recurrence rule and exceptions |
| `reminder` | PersonalStore | Schedule, timezone and linked task/event identity |
| `conversation` | ChatRepository | ID, title, project reference and creation time |
| `message` | ChatRepository | ID, conversation ID, predecessor ID, user/assistant role, content and creation time |

Only explicit schemas are accepted. No SQLite/WAL/journal files, profile directory,
credentials, vault entries, private/pairing keys, OAuth/Mail secrets, browser state,
models, indexes, embeddings, Studio/terminal sessions, Desktop Control state,
approval tokens or permission/trust records are portable kinds or payload fields.
Task links to Agent attempts are excluded. Chat excludes prompts, drafts,
provider/grounding/tool metadata, sources, attachments and their paths, research
state and hidden reasoning metadata. Attachment bytes do not travel at all.
Ordinary user-authored task/chat text remains text: sync neither interprets it nor
calls a model, tool, shell, Mail, Discord or automation service. An explicit text
field can contain a secret that a user typed; this is not a content-redaction or
secret-detection product. Selecting such a conversation shares its visible text.

The previous `olive/sync/contracts.py` compatibility boundary is unchanged. C5's
narrower protocol lives in `records.py`; it does not turn the old DeviceGrant or
broader collection vocabulary into authority.

## Identity, revisions and provenance

Native personal record UUID hex IDs and native chat/message UUIDs are reused.
Native optimistic integer revisions still govern ordinary local edits. Additional
sync revision UUIDs distinguish two offline children of the same native revision.
Missing legacy chat/message IDs are derived deterministically and persisted on
the next ordinary save; source files are not rewritten merely by loading them.
The derivation uses the enclosing identity plus original content and position,
not a display name or row index alone. Existing IDs are never replaced.

Each wire record has exactly:

```
kind, record_id, schema_version=1, revision,
ancestry={device_uuid: semantic_change_counter},
origin_device_id, editor_device_id, updated_at,
deleted, payload, editor_identity, signature
```

Only an actual semantic local change increments that device's vector counter and
creates a new revision. Incoming accepted records retain their exact revision,
vector, signature and original editor. Vectors have at most 32 device entries;
reaching that bound fails closed rather than discarding ancestry. Timestamps are
presentation metadata, never ordering or conflict authority. Dominating vectors
advance records; incomparable or equal-but-different vectors create conflicts.
An older vector cannot overwrite a newer one. UUID revision receipts retain a
canonical SHA-256 fingerprint: same revision/same content is idempotent; changed
content for that revision is an integrity error, even if re-signed.

The request's `source_device_id` and `updated_by_device_id` must both equal the
actual authenticated C3 peer. The current peer is the only authority to deliver
the batch. Historical editor attribution is separate: revisions are signed using
the existing C2 vault-backed Ed25519 identity, with the domain separator
`OLIVE-SYNC-REVISION/1`. The signature covers every field except itself, including
the editor's public identity. No additional private key is created or transferred.
The certificate identity must match the editor UUID, and signatures must verify.
If that UUID is locally known, its public identity must match the existing pin.
Thus B can forward A's unchanged revision to C without pretending to be A or
creating a new revision. C does not need to pair A just to retain historical data.
An unknown historical certificate proves possession of its signing key, **not**
that C's user has independently verified that historical device/name. It grants
no trust, permission or network access. Origin is informational, not ownership.

An authorized malicious peer can deliberately edit data or lie about causal
counters in a newly signed revision. Signatures authenticate authorship and stop
alteration during forwarding; they do not establish the honesty of an authorized
editor. Trusted local resolution and retained receipts are not a distributed
consensus system or protection against a compromised endpoint/profile rollback.

## Storage and transaction boundaries

Additive `sync_*_v1` tables live behind SyncStore in the native personal database.
They retain current portable revisions, native revision associations, a monotonic
local change sequence, per-peer/domain cursors, revision fingerprints, unresolved
conflicts, last session status, reminder arrival cutoffs, and local chat selection
and predecessor metadata. No authority settings are stored in these tables.
The native PersonalStore `records`, `links` and `deliveries` remain authoritative.
Changed native revisions are captured in bounded groups; payload histories are
not accumulated. Current payloads and unresolved competing versions are retained.

Every batch is schema-validated before writes. The exact incoming target IDs are
recaptured inside the transaction, independently of inventory capture limits, so
a local edit beyond the current capture window cannot be overwritten. Conflict
resolution repeats the same exact-target check. Fingerprints, native writes,
links, conflict state and cursors share one SQLite transaction. A missing dependency
is an explicitly acknowledged staged conflict, not a half-written native record.
Every acknowledgement identifies the exact received revisions and per-record
outcome. Invalid records or exhausted ledger/conflict capacity roll back the whole
batch. The sender advances its cursor only after validating the response and
committing its corresponding local transaction.

Chat still uses its native atomic JSON repository. A durable SQLite materialization
journal bridges that file with sync metadata. A committed batch is materialized
before acknowledgement; restart flushes the journal before capturing local edits.
Reapplying message IDs is idempotent. Desktop capture/application/materialization
runs as a bounded operation on the owning event loop so it cannot interleave with
ordinary chat mutations. Transport and session waits run off the UI thread.
Active generation or a local incomplete message holds incoming chat changes for
review. No claim is made that SQLite and a JSON file participate in one filesystem transaction.

The protocol never exports storage files, even though its implementation uses
local SQLite transactions. Existing legacy profiles remain in place. Native
schema version 4 stays unchanged; new auxiliary tables have explicit v1 names.

## Conflicts, deletion and relationships

C5 conservatively conflicts on concurrent changes to an existing personal record
or message, including disjoint fields. There is **no generic JSON merge** and no
Merge button for those records. Native event exceptions and recurrence rules stay
intact; they are never flattened into generated instances. The record-specific
safe merge is concurrent chat **append**: separate message records retain stable
predecessors, with deterministic UUID ordering among siblings, independent of clocks.

A conflict retains record identity, source peer, original local snapshot/revision,
incoming signed version, timestamps and a fixed reason. Generic Activity never
shows those payloads. Local Review conflicts displays relevant record fields;
Keep this device / Use incoming version creates a new local signed revision whose
vector covers both parents. An intervening local edit requires another review.
A later dominating resolution retires the unresolved conflict while retaining
revision fingerprints, preventing the losing revision from reappearing.

Deletion sends an empty-payload tombstone. Tombstones and fingerprint receipts
are not garbage-collected. Stale live data cannot resurrect a tombstone; explicit
recreation of the same ID is unsupported. New objects require new IDs. A concurrent
delete/edit is retained for review. Once either parent is a tombstone, a live
version cannot be chosen as a same-ID recreation; the retained text can be used
in a separately created new local record. Deletion with live dependent links is held,
not applied with dangling references. Sync the dependent tombstones/updates or
resolve the relationship locally first. Revocation never deletes historical data.

Native relationship validation checks exact record kinds, calendars, task/event
links, contacts and project IDs. Projects, contacts and workspaces are not exported
in C5: missing dependencies are held in conflict state until the local dependency
exists and the user reviews the incoming version. An Agent-attempt link is never
portable. This deliberately avoids inventing project workspaces or copying files.

## Sessions, bounds, cancellation and reconnect

C3 framing adds dedicated types 5/6 for `olive-sync/1` requests/responses. Ordinary
C1 request frames retain their existing 16,384-byte limit and dispatch vocabulary.
Sync uses strict duplicate-free JSON, not pickle/eval/marshal or arbitrary RPC.

One exchange is a bounded push batch plus a pull cursor for exactly one domain.
The receiver checks the C3 source/target, freshness, current trust/key, local
capability policy and per-device permission; applies the push transaction; returns
exact revision acknowledgements and the next bounded delta after the pull cursor.
The same checks occur before the initiator commits the returned data. This cursor
summary supports initial union and progressive exchange without exporting a whole
database on every connection. New records are unioned; divergent matching IDs
follow the same conflict rules. Independent pairwise cursors support many devices.

| Resource | Limit |
| --- | --- |
| Encoded signed record | 72,000 bytes |
| Batch | 8 records, within 256,000-byte sync frame |
| Outgoing session | 8 exchanges, 90 seconds, one worker per desktop |
| In-flight outgoing sync exchanges | One per session; C3 also caps all channel requests at eight |
| Local capture | Up to 256 changed personal records and 256 message positions per exchange (unchanged conversations are skipped) |
| Inventory scan | Up to 512 ledger entries per exchange, skipping unselected conversations |
| Revision vector | 32 devices |
| Current portable records | 10,000 and 64 MiB of encoded records, fail closed at capacity |
| Durable revision fingerprints | 100,000, fail closed at capacity |
| Unresolved conflicts | 128, fail closed at capacity |
| C3 network rate/concurrency/timeouts | Existing C3 limits, including 60 messages/peer/minute and five-second request wait |

Payloads bigger than a record limit fail visibly; C5 does not split an individual
oversized message. Long conversations progress as separate message records across
batches/sessions. Repeated Sync now resumes from acknowledged cursors. Limits do
not evict tombstones/conflicts or silently discard message content. Limits on
revision receipts bound storage and can require future explicit archival tooling;
no unsafe automatic compaction is implemented.

Cancellation stops subsequent batches. Already committed batches remain, and
status reports cancelled/partial rather than full success. A connection loss after
commit but before acknowledgement causes an idempotent retry. Requests recheck
current permission even when records are duplicates. Revocation commits local
policy and interrupts C3 immediately; fresh handshakes cannot revive the peer.
Shutdown cancels the sync worker, joins it, then closes C3 through its existing
lifecycle. No aggressive automatic sync/reconnect polling was added.

Ask uses the existing C4 trusted local approval registry. Its prompt identifies
device, domain, bidirectional scope and maximum batch size. Approval binds the
exact request fingerprint, peer public identity, permission revision and expiry.
The identical request is retried while awaiting local approval. Completed Ask
responses are frozen in a bounded transient cache (32 responses, at most 120
seconds), so repeating an approval cannot disclose a fresh batch. Local initiating
approvals use a distinct, non-wire operation binding and cannot authorize an
incoming reflected request. Cache loss on restart also loses pending approvals;
record fingerprints still make committed data retries idempotent. No wire approval
flag or conflict winner is accepted. Local Ask is checked on the initiator too;
clicking Sync now does not rewrite Ask to Allow. C3 limits can end a long wait;
status then remains partial and the user may explicitly retry.

## Reminder behavior

C5 synchronizes reminder **definitions** and linked task completion/reopening.
Notification delivery, snooze and dismissal are local per-device state in the
existing delivery ledger. Each intended device independently notifies once per
occurrence; acknowledging a popup on A does not acknowledge a popup on B.

A durable cutoff at each accepted incoming reminder or linked schedule change
suppresses already-overdue occurrences on a receiving device, including after restart. Existing delivered/dismissed/snoozed occurrences
retain their native deduplication IDs and are not reset by duplicate revisions.
Future occurrences notify normally; linked task completion cancels pending local
deliveries. No stale imported definition fabricates catch-up notifications. The
Devices Sync panel explains this policy explicitly.

## Selected Chat continuity

Selection is per peer, local and never a portable record. Off remains default.
The sender explicitly selects conversations; enabling `sync.chat` alone does not
export its entire history. Receiving a selected conversation enables continuity
back to that source, subject to local `sync.chat` permission, but never selects it
for a third peer. Explicit deselection is retained and cannot be overwritten by
an incoming update. Updates targeting an existing local conversation that is
not selected for that peer are held for review, rather than replacing it.
Deselecting does not remotely erase data already shared.

Stable conversation/message IDs and deterministic predecessor ordering support
opening the native conversation on another desktop. Concurrent append preserves
both messages without duplication. Existing-message edits/deletes use ordinary
conflict/tombstone rules. Local conversation deletion emits its message tombstones
before the conversation tombstone; receiving that deletion never authors new
child revisions. A local unsynchronized append, draft, note or attachment holds
an incoming conversation deletion for review instead of discarding local content.
Model choice and system prompts remain local; receiving a conversation does not invoke inference or open a UI. Remote opening, mobile
handoff and file/attachment transfer remain later phases.

## Devices UI and activity

The accepted Devices workspace has a small Sync panel on each paired device:
per-domain Off/Ask/Allow, real last-session status and counts, Sync now, Cancel,
Select conversations and Review conflicts. No redesign or synthetic progress.
Generic Activity stores only peer/request IDs, known capability IDs, timestamps
and fixed sync state labels. Detailed conflict text is fetched only by local
review. Sync selection/resolution routes are strict local IPC methods and are
absent from all network dispatch paths.

## Threat model

| Threat | Classification | Mechanism / boundary |
| --- | --- | --- |
| Malformed records, future schemas, duplicate JSON keys | Mitigated | Exact schemas, native validators, version refusal before writes |
| Huge batch / unbounded pending work | Partially mitigated | Record/frame/batch/session/receipt/conflict limits plus C3 rate/concurrency/timeouts; authorized peers can exhaust finite quotas |
| Same revision with altered content | Mitigated | Editor signature plus durable full-record fingerprint; re-signing does not bypass receipt integrity |
| Stale resurrection | Mitigated | Retained tombstones and vector ordering; no same-ID recreation |
| Clock skew | Mitigated for record ordering | No timestamp winner; C3 request freshness and certificate validity can still reject skewed devices |
| Concurrent/offline edits | Mitigated | Vector conflict retention, explicit local resolution, append-specific ordering |
| Task/Chat prompt injection or executable text | Mitigated at sync boundary | Data-only native adapters; no model, tool, shell or communication dispatcher |
| Permission escalation / pairing / unrevoke | Mitigated | No authority record kinds; only trusted local setters, current transactional checks |
| Credential/private-state export | Mitigated for structured state | Hard allowlisted kinds/fields, no paths/files/vault adapter; voluntarily typed text is not automatically redacted |
| Revoked peer sync | Mitigated | C3 interruption, persisted trust tombstone, execution-time checks |
| Replay across reconnect | Mitigated | Durable revision fingerprints and native IDs, transactional cursors, expiry/current authority before retries |
| Three-device loops / revision amplification | Mitigated | Relay keeps signed revision/vector unchanged; duplicate apply creates no semantic revision |
| Forged editor / altered relay provenance | Partially mitigated | Signed C2 public identity and known-key pin comparison; an unknown historical identity is not independently paired trust |
| Conflict-resolution spoofing | Mitigated | No network resolution operation or winner field; local IPC creates the new signed revision |
| Dishonest authorized edits / ancestry counters | Partially mitigated | Authenticated and attributable editor, concurrent honest edits protected; authorized malicious editors can intentionally change permitted data |
| Endpoint compromise, profile rollback/clone | Deferred | Same boundary as C1–C4; no hardware anti-rollback or distributed consensus |

## Validation

Portable tests use synthetic profiles/vaults, actual native repositories and real
C3 TLS loopback. No GPU, Ollama, KDE/KWallet, mDNS, Internet or personal credentials
are required. `test_connect_sync_process` uses three independent ordinary backend
processes with controlled C2 pre-pairing. It covers A→B→C propagation, offline
conflicts and resolution, calendar recurrence/DST representation, reminders,
selected chat append, deletion and revocation. `test_connect_sync_security` uses
the actual Host trusted approval registry, cancellation and loss after commit
before acknowledgement. Unit contracts cover signatures, changed duplicates,
strict schemas, private fields, atomic invalid batches, quotas and relationship
staging. Reminder restart and selected/unselected chat tests use real repositories.

The Electron Devices acceptance extends the existing paired second-process flow
with Off-by-default Tasks sync, Sync now, actual received counts and local conflict
review/resolution. The portable CI matrix includes C5 and its dateutil/tzdata
requirements on Linux/Windows. Native Windows and physical-LAN acceptance are not
inferred from a Linux portable run.

Verification on Linux, 2026-09-20 (final implementation commit `40bf0e1`):

| Check | Result |
| --- | --- |
| Full Python suite | 986 run: 978 passed, 8 platform skips, no failures |
| Portable Connect CI command | 132 passed, including 20 C5 tests |
| Frontend unit tests | 41 passed in 13 files |
| TypeScript / ESLint / production build | Passed |
| Application source compilation | Passed |
| Exact `python -m compileall -q .` | Failed only on the existing ignored PySide6 Jinja template in `.venv` (`__init__.tmpl.py`) |
| Focused Linux desktop acceptance | 9 passed: desktop launch, GO, Devices, Linux startup/reminder restart, Studio and REIMAGINE |
| Final Devices acceptance after target-capture fixes | 2 passed, including actual sync and conflict resolution |
| Diff / data-safety review | No accidental branding regressions, credentials or user-data files added |

The full suite also exercises Chat and shutdown paths. The broader desktop run
preceded the final incoming-status and exact-target capture fixes; the complete
Python/Connect suites and Devices acceptance were rerun after those fixes.
Frontend code was unchanged after its successful checks. The existing full-suite
shutdown warning about 26 uncollectable Python objects remains; it is not a test
failure and is not claimed fixed by C5. Native Windows and the hosted CI runners
were not executed here. The portable CI workflow was updated and its test command
passed locally over real loopback transport.

## Known limits and operating guidance

- Both endpoints need C5 for sync frames. C1–C4 operations retain their original
  protocol and limits; there is no database-export or cloud fallback for an older
  peer.
- Sync is manual and resumes through Sync now. Quotas or unresolved dependencies
  can leave a partial session. No automatic conflict/tombstone eviction makes a
  blocked session appear successful.
- Personal disjoint-field edits are conservatively reviewed, not automatically
  merged. Chat append is the only automatic record-specific merge.
- Project/contact dependencies must already exist locally. Their identities,
  files, permissions and workspaces are not silently imported.
- At most 500 native conversations are listed in the current selection surface.
  A single oversized message fails visibly; message fragmentation and attachment
  transfer are not C5 features.
- Native repository loading/materialization still follows the current JSON Chat
  architecture. Network history transfer and message capture are progressive;
  this does not claim an incremental native JSON file format.
- A peer with Allow can intentionally modify permitted records or exhaust bounded
  resources. Signature verification is not a proof of honest ancestry counters.
  An unpaired historical editor is signed provenance, not independently verified
  local trust.
- Delivery/snooze/dismiss are per-device. Cross-device notification arbitration,
  same-ID recreation, tombstone collection, profile rollback recovery and key
  rotation are not implemented here.
- No native Windows, physical-LAN/firewall, real wallet, model/GPU, Internet relay
  or mobile acceptance is claimed by these Linux synthetic-profile runs.

Reproduce the portable CI command directly from
`.github/workflows/connect-portable.yml`. Full repository checks use:

```sh
python -m compileall -q .
python -m unittest discover -s tests -v
npm --prefix desktop run typecheck
npm --prefix desktop run lint
npm --prefix desktop test
npm --prefix desktop run build
cd desktop
npx playwright test browser.spec.ts connect.spec.ts linux-l1.spec.ts linux-l3.spec.ts studio.spec.ts media.spec.ts
```

Use the repository's existing Python/Node toolchains and configure `DOTNET_ROOT`
for the unrelated .NET regression tests. On Linux, source-only compilation can
exclude ignored `.venv`, `node_modules`, `.toolchains` and `.git`; that is reported
separately from the exact whole-tree command.
