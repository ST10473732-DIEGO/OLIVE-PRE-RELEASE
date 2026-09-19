# OLIVE Mail and optional transports

OLIVE owns local drafts, imported messages and immutable attachment bytes.
Open **All Spaces → Mail**, or **Command palette → Open Mail**. Compose, autosave,
search, EML import/export, reply/forward, archive/trash and project links work
without an account or model. Autosave is local and revision-checked, never sending.
Received source EML remains unchanged. Local read/starred/folder annotations are
distinct from server state. Threads use account-scoped references, not subject
similarity or an assumed globally unique Message-ID.

## Optional server setup

1. Open **Settings → Connections → Mail → Add connection**, also available from
   Mail's Connections button. Enter a name, actual sender address and username.
2. Enable SMTP, IMAP or both. Use your administrator's host/port/TLS mode:
   commonly SMTP 465 implicit TLS / 587 STARTTLS, IMAP 993 implicit TLS / 143
   STARTTLS. Certificate-validated TLS must succeed before login.
3. Save, then store the password/app-password in the dedicated masked control.
   Generic transports use password/app-password authentication. Gmail uses the
   separate registered desktop OAuth flow described below; no mandatory provider
   or public OLIVE address is invented.
4. **Test connection** shows incoming/outgoing results separately and sends no
   message. **Reconnect** enables subsequent approved access. Disconnect, remove
   credentials and remove cached bodies are separate operations.
5. Select the connection/mailbox in Mail and **Refresh server**. Headers are
   batched; **Fetch body** retrieves one selected message using PEEK without an
   implicit read flag. Server flag/move/folder operations have explicit review.
6. Compose with that sending identity. **Review submission** presents the exact
   server, sender, To/CC/BCC, subject/body, attachments and size. Cancelling review
   preserves the draft. Changed content or connection requires renewed approval.

Additional CA certificates are scoped to that connection's validating TLS
context, preserving hostname checks. No OS trust-store change or accept-all
certificate mode exists. OLIVE runs no public listener, configures no DNS and
never silently downgrades to plaintext. Google authorization temporarily opens a
loopback-only callback listener for at most five minutes; it is not a LAN service.

## Optional Gmail and iCloud accounts

Mail Connections contains the complete Google setup checklist: enable Gmail API,
configure the Google consent audience and `https://mail.google.com/` restricted
scope, register a **Desktop app** OAuth client, import its downloaded JSON, and
authorize each account in the system browser. Public distribution requires Google's
applicable verification; testing-mode grants can expire. OLIVE validates state and
PKCE, uses pinned TLS endpoints, and stores client/refresh credentials only in the
existing OS vault. Access tokens are memory-only. Imported app configuration is
device-local and is not transferred by data backup. No embedded login, cookie
scraping, password capture, or hosted fallback is used.

OAuth-enabled IMAP/SMTP extends the existing M4 transport and submission journal;
it does not introduce a parallel mail store. Only the Gmail profile's actual primary
address is offered for that account. Additional aliases are not claimed supported.
After consent, enable and test the account explicitly. Reauthorize expired/revoked
grants; remove the grant in Google Account security settings for provider-side
revocation. Removing local credentials disconnects OLIVE without deleting mail.
See Google's [desktop OAuth documentation](https://developers.google.com/identity/protocols/oauth2/native-app)
and [Gmail XOAUTH2 protocol](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol).

**Add iCloud Mail** fills `imap.mail.me.com:993` (TLS) and
`smtp.mail.me.com:587` (required STARTTLS). Use the full iCloud address and an
Apple app-specific password created after enabling two-factor authentication.
Never enter the main Apple Account password. See [Apple's official settings](https://support.apple.com/en-us/102525).
Connection testing uses authentication and NOOP; it never sends a message.

Unified Inbox and per-account standard folders resolve advertised SPECIAL-USE
roles while retaining exact wire mailbox names and UIDVALIDITY/UID identity.
Gmail X-GM-MSGID deduplicates labels **within one account only**; each label's
remote location remains recorded. UID MOVE is required for remote moves and never
falls back to EXPUNGE. COPYUID updates a moved record's destination identity when
available; otherwise it stays visibly moved until a refresh can reconcile it.
Trash means cached/server deleted-folder content, not recovery of permanently
removed messages. Old data and contact relationships remain intact. Composer
suggestions use bounded recent participant headers, never BCC or a compulsory
Contacts feature; the user selects an exact address.

Current evidence distinguishes real local TLS socket/protocol tests and Electron
Mail workflows from provider interoperability. No personal Gmail or iCloud account
has been signed in or live-verified by this implementation run.

## Submission, cancellation and recovery

`olive/mail/submission.py` persists immutable MIME/envelope snapshots before
approval. Attachment bytes are snapshotted when added: later edits to the source
file do not change approved bytes. BCC is in the envelope/preview, not the
transmitted header. SMTPUTF8 and declared SIZE are checked.

States distinguish draft, awaiting review/prepared, submitting, accepted by the
submission server, partially accepted, failed, cancelled before submission and
outcome uncertain. Acceptance is **not delivery or reading**. Per-recipient
results are retained. An explicit retry action creates an unsent draft only for
definitively rejected recipients, requiring fresh review. Uncertain sends never
retry automatically; Message-ID cannot guarantee exactly-once delivery.

Cancellation can prevent DATA. After bytes may have reached the server it cannot
recall them; loss of the final response is uncertain. Socket commands have a
10-second timeout. Cancellation feedback is immediate, but a blocked command may
take that bounded interval to unwind. Persistent single-flight transitions
prevent double-click/reload replay. Interrupted submissions recover as uncertain;
prepared entries recover cancelled. Restart and restore never submit outbox work.

Remote Sent copies are separate and off by default. Opt in only if the server
does not create its own copy. A reviewed APPEND copies already accepted bytes.
Failure/uncertainty never repeats SMTP. Interrupted remote flag/move/folder
operations retain a durable uncertain record and do not replay. Refresh and
reconcile before another change; there is no automatic remote-mutation retry queue.

## IMAP and content limits

The real adapter uses Python `imaplib`: TLS/STARTTLS, capabilities, LIST/SELECT,
UID SEARCH/FETCH, BODY.PEEK, Seen/Flagged, CREATE/RENAME, advertised MOVE and Sent
APPEND. There is no broad EXPUNGE or permanent remote deletion. Unsupported MOVE
fails explicitly rather than using unsafe delete/expunge. Mailbox wire names
preserve server modified-UTF7 spelling; Unicode name conversion is unclaimed.
Server TEXT search currently accepts ASCII queries; local Unicode search works.

Connection/mailbox + UIDVALIDITY + UID identify cached records, never sequence
numbers. UIDVALIDITY resets preserve and label prior evidence. Missing messages
are labelled rather than erased. Successful batches survive partial failures.
Rotating bounded metadata refresh exposes conflicts with local flags. A moved
source remains labelled; a refreshed destination may have a distinct cache ID.

Batches are 1–100 headers (default 50), UID discovery at most 100,000, server
search results at most 50 headers. Bodies/attachments are fetched on demand.
Optional runtime-only INBOX sync runs at most every five minutes per enabled
connection and only when existing read/connect policies are Allow. Ask/Deny is
not overridden. Welcome does not connect; no always-running service is installed.

MIME input: 20 MB, 150 parts, 12 nesting levels. Readable text is bounded with
warnings and raw EML retained. Outgoing attachments: 10 MB each, 15 MB total.
HTML uses DOMPurify plus an opaque sandbox with no bridge/scripts/forms/network.
Only bounded validated raster CID images render. Plain text always remains
available. Lossless recovery of every malformed MIME variant is not promised.

## Native composition, storage and backups

Shared Home/Chat/Agent language supports search/read/thread summary, unsent
drafts/replies, explicit addresses and recipient suggestions, corrections, attachments, submission and
cancellation. Summaries use at most ten cached thread messages / 12,000 characters
with the installed local model. Ambiguous identities/dates require clarification.
Named recipients require an address selection; legacy Contacts are not a required
Mail feature. Natural-language searches keep the sender address separate from
plain subject/body terms; sender matching uses the parsed exact address.
Imported content is untrusted and cannot grant permission or become user intent.

Mail prepares reviewed source-linked Calendar/Task records. Repeated accepted
proposals retain IDs. Calendar/Project context creates unsent drafts. Selected
messages/attachments can be explicitly added to existing local Knowledge; there
is no automatic mailbox indexing or Memory creation. Basic ICS attachments do not
claim full meeting-organiser/RSVP synchronisation or invitation delivery.

Mail uses additive **mail.sqlite3 schema 1**, including immutable blobs. Personal
Core schema **4**, profile resolution, locks and IDs remain unchanged. SQLite
backup includes committed WAL data. Default backups include native/cached Mail
and attachments but not vault secrets. They contain readable personal content.
Explicit cache removal retains native drafts/imports and stable source records.

Restore validates schema/hashes/relationships, stages replacement and creates a
safety backup, rejecting active work. Connections restore disconnected and
review-required without credential references. Native IDs/reminder history remain;
sends never replay. Explicit Mail Knowledge snapshots rebind to the restored
profile without fetching or automatically reindexing.

SMTP evidence uses independent **aiosmtpd 1.4.6** no-relay loopback TLS sinks,
including partial rejection and lost final reply. IMAP evidence uses real TLS
sockets against a **scripted protocol fixture**, not an independent server.
Docker's local engine was unavailable; no privileged installation was attempted.
No live external server/account has been tested. See
[M4 classified evidence](docs/releases/3.5.1/M4_COMPLETION.md).

Primary references: [Python SMTP](https://docs.python.org/3/library/smtplib.html),
[IMAP](https://docs.python.org/3/library/imaplib.html),
[email](https://docs.python.org/3/library/email.html),
[RFC 9051](https://www.rfc-editor.org/rfc/rfc9051.html),
[DOMPurify](https://github.com/cure53/DOMPurify),
[aiosmtpd](https://aiosmtpd.aio-libs.org/).


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
