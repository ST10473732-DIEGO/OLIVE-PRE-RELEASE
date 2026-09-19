# M4 Native Mail — implementation and internal acceptance

Status: **M4 implementation and internal acceptance complete.**
No final release approval, new tag, Qt removal or default-launcher switch.

## Baseline and scope

Actual baseline `2eaabbd1f77432d17f5eb4c9d31f797205df7837`, clean branch
`development/3.5.1-electron-experience`. It already included M3, rebrand, animated
Core, C# Studio and caption corrections. Nothing was reset to an older checkpoint.
M4 implementation checkpoint: `15c89a2`; subsequent recovery/parity/QA repairs are
recorded by the final commit. Existing historical bad tree
`726faf9e19f6fb906b35a45cdd04f1f30cbde5cd` still causes automatic Git maintenance
warnings; active source/commits remain readable. No history repair was attempted.

OLIVE remains 3.5.1 development, canonical `olive` / `window.olive`, one supervised
Python runtime and existing profile locks. Green desktop icon, blue animated
Core, approved Electron design, models and all 125 original M2 mappings remain.
M4 introduces no public mail server, external account or provider dependency.

## Implemented actions and boundaries

Native Mail provides folders, account-scoped reference threads, local/cached
search and filters, message detail, safe HTML/plain text, read/starred annotations,
archive/trash, custom folders, draft autosave/manual save/conflict comparison,
reply/reply-all/forward/duplicate, immutable attachments, outbox history, EML
preview/dedup/import/export, project references and direct Compose Mail command.
Selection/drafts survive navigation and restart. Unconfigured Mail is useful and
never invents a sender, inbox, connection or successful send.

`olive/mail` uses existing tools, permissions, confirmations, interaction context
and shared natural-language routing. React cannot read databases/vaults or open
mail sockets. Explicit direct form actions still respect Deny. Exact sending
previews bind draft/connection revisions, canonical envelope/content/attachment
hashes and a bounded-lifetime immutable preparation. Each recipient's acceptance
is recorded; BCC is omitted from transmitted headers. Cancel before submission,
partial rejection, uncertainty, interruption and separate Sent-copy outcomes are
distinct. No startup/restore/IPC retry blindly submits or repeats an uncertain send.

Windows current-user Credential Manager is reused with opaque profile-scoped
references, no generic secret getter or plaintext fallback. The existing pywin32
write boundary was corrected to use its documented Unicode value; new UTF-16LE
records and legacy UTF-8 records remain readable. Secret-entry provider exception
chains are not retained in protocol task state. This is not protection against
every same-user process, full-data encryption, or end-to-end email encryption.

Real stdlib SMTP/IMAP adapters require certificate-validated TLS or secure
STARTTLS before authentication. Settings supports SMTP/IMAP/combined connections,
masked credentials, separate tests/capabilities, disconnect/reconnect, credential
removal and explicit cached-body removal. Test never sends. SMTP supports exact
recipient results and SMTPUTF8 checks. IMAP supports bounded incremental headers,
body PEEK, UIDVALIDITY changes, flags/conflicts, search, advertised MOVE, folder
create/rename and separate Sent APPEND. No broad EXPUNGE/permanent remote delete.
Optional permission-preserving read sync runs only while the runtime is active.

Mail composes with Contacts, Calendar, Tasks, Projects and selected Knowledge.
Natural requests search/read/summarise bounded cached threads, resolve people,
draft/reply/forward, correct, attach and cancel through shared tools. Source-linked
Calendar/Task proposals require review and deduplicate accepted creation. Calendar
context becomes an unsent draft. Explicit Knowledge sources use existing local
indexing, with portable source snapshots; no automatic mailbox indexing/Memory.

## Fresh validation

| Class | Actual result / evidence under `artifacts/ui-review/M4` |
| --- | --- |
| Baseline only | 699 Python; 23 frontend; 31 ordinary Electron / 3 opt-ins; compilation/typecheck/lint/build passed, `baseline/` |
| Final Python including security/protocol | **732 passed**, 59.624 s, `final-python-02.log` |
| Final frontend | **25 passed**, TypeScript/lint/production build exit 0, `final-frontend-03/` |
| Compilation | Complete `python -m compileall -q .` exit 0, `final-compilation-03.log` |
| Harness unit | **7 passed**, `final-harness.log` |
| Qt fallback controlled smoke | **49 passed**, no errors, `final-qt/results.json`; no live desktop-control campaign |
| Existing local-model interpretation regression | **12/12 passed**, `final-language-regression.log`; interpretation only, no action execution |
| Real Mail local-model Electron workflow | **1 passed**, 20.7 s, `final-live-language.log`, `language-ui/`; installed qwen3:8b, not injected intent |
| Complete ordinary Electron | **37 passed, 4 documented opt-in skips, exit 0**, 5.3 minutes, `final-electron.log`; one complete run after final presentation corrections |

Intentional ordinary opt-ins: `live-chat` (real model streaming), `m2-closeout-live`
(local Agent/public Research), `m3-language-live` (native model workflow), and
`m4-language-live` (run separately above). They are not silent missing tests.
Existing deterministic language/security coverage remains in the Python suite.

The first integrated full Electron run had **36 passes, 4 opt-ins and one failure**
(`full-electron-before-final-repairs.log`). A task assertion mistook approval-overlay
closure for transaction completion. It now waits for the actual saved record,
retaining content/ID assertions. No product error was swallowed. The forwarding
regression additionally exposed empty Message-ID incorrectly linking a forwarded
draft to its source thread, and duplicate ownership references rejecting an
unchanged forwarded attachment. Both guards were narrowly corrected and tested.

Warnings: existing Qt styling/geometry warnings, Python's shutdown warning about
26 uncollectable objects, aiosmtpd's deprecated session attribute and implicit-TLS
authentication warning, and Node NO_COLOR/FORCE_COLOR conflict. The implicit-TLS
fixture listener itself requires TLS before SMTP; no production plaintext mode
was introduced. These warnings are not failures or independent audit evidence.

## Real application demonstrations (synthetic profiles only)

| Brief | Evidence and result |
| --- | --- |
| A | `local-ui/`: actual Compose/autosave, Home/Mail retention, restart and exact draft ID/body; no connection/model, no outbox entries |
| B | `content-ui/`: multipart Unicode EML, CID raster/attachment, local search, byte-identical raw EML export; actual opaque iframe has no bridge/scripts/forms and emits no tracking requests |
| C | `language-ui/`, `content-ui/`: native Contact resolution, reply/draft recipient/body corrections and cancellation; selected fixture attachment snapshots; no unapproved send |
| D | `smtp-ui/*/connections.png`, `test_mail_vault`: real current-user dummy vault, masked UI, actual TLS test with no DATA, reconnect/disconnect and owned credential cleanup |
| E | `smtp-ui/accepted/`: exact delegated approval through actual Electron controls to independent aiosmtpd STARTTLS sink; envelope/subject/body/attachment bytes checked and BCC header absent; local server acceptance only |
| F | `smtp-ui/partially_accepted/`, `smtp-ui/outcome_uncertain/`: production adapter receives recipient rejection / loses final reply after bytes accepted by sink; actual UI reports correct state and locks blind resend |
| G | `imap-ui/`: actual Electron refresh/body retrieval/restart/disconnect through production adapter and scripted TLS peer; one header then on-demand body, same cached ID, no implicit STORE/EXPUNGE. Expanded UIDVALIDITY/partial/conflict/MOVE/Sent-copy cases in Python protocol tests |
| H | `content-ui/`: actual Mail-to-Calendar/Task reviewed creations and Calendar-to-unsent-draft; `backup-ui/` project relationships; explicit Mail-to-Knowledge indexing passed with unavailable model |
| I | `test_mail_local/policy/security`: draft/connection/attachment ownership/revision/fingerprint rejection, immutable source-file snapshots and explicit Deny; controlled tests, not live external sends |
| J | `backup-ui/`: actual native backup/restore into another isolated profile; Mail draft/project links, M3 record IDs and dismissed-reminder history retained; connections disconnected/ref removed, prepared send cancelled; no replay |
| K | `language-ui/`: real installed local interpreter from Home/Chat: search Sarah, summary, draft, correct recipient to James, cancel; same draft ID/body preserved, no submission |

Approvals are recorded as exercised under explicit user **delegation**, never
mislabelled manually clicked by the user. Native chooser paths are controlled
fixture inputs. No approved state, observation, server response or success label
is injected into the product. Pure mocks, scripted peers and independent sinks
are distinguished in tests and evidence. Owned fixture processes and dummy vault
references are cleaned up; ignored synthetic profiles/evidence remain for audit.

## Visual inspection and performance

Actual Electron compositor captures were opened and inspected internally: fresh
Mail, populated message, composer/attachments, source proposals, Connections,
approval and partial/uncertain results. Normal 1440×920, smaller 1366×768, dark/
light, 125% interface size, reduced motion and keyboard Compose were exercised.
Repairs: field spacing, sticky save actions, earlier two-column adaptation,
readable proposal spacing and native capture after paint to avoid zoom cropping
or obsolete compositor frames. No Welcome/Home redesign was performed.

The final 200-message corpus check (`render-review/`, script
`scripts/m4_mail_review.cjs`) exposed an expanded thread button grid. It was
replaced with a bounded scrolling list and an explicit 30-of-35 count. The final
thread and masked credential-entry images were reopened and inspected. The dummy
value in that additional visual check was cleared without storing credentials.

`local-ui/result.json` records actual navigation/autosave durations including
IPC, lazy loading and the 900 ms autosave debounce; these are not pure renderer
costs. The 200-message check measured populated opening **866 ms**, search to
render **45 ms**, and opening the bounded thread list **25 ms**. A representative
autosave measurement was **1,355 ms including its 900 ms debounce**. These are
single local observations, not hardware-independent budgets.
`language-ui/results.json` records request durations **6,987 / 4,967 / 2,544 /
2,043 / 1,952 ms** for search/summary/draft/correction/cancel, including local
model/backend work, not renderer latency.
No event-driven capture is used to claim FPS. GPU/combined inference overhead,
physical DPI/multi-monitor variants and accessibility certification remain
unmeasured. No new recording is required for M4; screenshots are local evidence,
not a claim of personal user visual approval.

## Dependencies, schema, compatibility and limits

- Personal Core remains schema 4; Mail adds separate transactional SQLite schema
  1 with immutable blob snapshots. No old records, calendar UIDs or profile paths
  are renamed. Existing `.dmdo` profiles/backup identities remain supported.
- DOMPurify **3.4.15** became a direct pinned dependency at its already-locked
  version; no broad upgrade. Production Python uses stdlib and existing pywin32/
  Pillow. Test-only `requirements-mail-test.txt` pins aiosmtpd 1.4.6, atpublic 7.0.0,
  attrs 26.1.0 and cryptography 50.0.1. DOMPurify Apache-2.0/MPL-2.0, aiosmtpd
  Apache-2.0, atpublic Apache-2.0, attrs MIT, cryptography Apache-2.0/BSD licensing
  remains governed by their distributed notices; include applicable notices in
  future packaging.
- SMTP is independently tested locally; IMAP interoperability beyond the scripted
  TLS peer is unverified because an independent local engine was unavailable.
  No Internet account/server or delivery was tested. OAuth-only services, IMAP
  extensions not implemented, Unicode mailbox conversion and non-ASCII server
  TEXT search are not claimed. Local Unicode search works.
- No permanent remote delete, bulk mail, scheduled send, automatic uncertain
  retry, full RSVP/organiser sync or always-running service. Socket cancellation
  may wait for a bounded 10-second command timeout. Mail content/backups are
  readable; vault encryption does not encrypt the whole profile.
- Source production assets build and run locally without Vite/CDN. The existing
  missing self-contained `desktop/backend-artifact` still blocks a distributable
  packaging/clean-machine claim. No installer/shortcut/auto-update was published.

## Opening the features

Use the existing Electron launch instructions in `desktop/README.md`. Open
**All Spaces → Mail**, **Command palette → Compose Mail**, or
**Settings → Connections → Mail**. Start locally with Compose or Import EML;
optional server setup and exact TLS/authentication limits are in
`MAIL_TRANSPORTS.md`. `run_olive.bat` still retains the Qt default/fallback.

No real personal records, mailbox, account, credential, message destination or
OS certificate-store configuration was modified. No next milestone or release
tag is started by this checkpoint.
