# Native Personal Core

M3 implements OLIVE-owned Profile, Contacts, Calendar, Personal Tasks and in-app
Reminders through the Electron frontend and the existing supervised Python runtime.
Implementation and internal acceptance are complete; see
[M3_COMPLETION.md](docs/releases/3.5.1/M3_COMPLETION.md) for classified evidence and limits.
Mail and optional SMTP/IMAP are implemented by M4 in a separate native store.
Mail proposals reuse these Calendar/Task services and stable source links; they
never imply invitations or messages were sent. See [Mail](MAIL_TRANSPORTS.md).

## Use

Open All Spaces or Ctrl+Shift+P, then Profile, Contacts, Calendar, Tasks or
Reminders. New Calendar Event and New Personal Task commands open their forms.
Profile setup is optional. No online registration or Google/Microsoft account is
required. Manual local operations do not require Ollama or networking.

Profile stores a local name/avatar, IANA timezone, locale, date/time preferences,
working hours and default calendar. South African English and Africa/Johannesburg
are offered by default and can be changed. Avatars are selected locally, resized
and re-encoded; imported contact URLs never fetch images automatically.

Contacts support labelled email/phone/external identifiers, aliases, organisation,
notes and project links. Duplicate suggestions do not merge records. Review the
merge fields and relationships, then approve the specific operation. Search and
conversational identity resolution return bounded candidates, not an address-book
dump. Contact metadata never grants permission to communicate.

Calendar offers Month, Week, Agenda and a focused Day view, calendar visibility/categories, search,
event editing, recurring occurrence/series scope and deterministic free-time
calculation. Tasks have Today, Upcoming, All, Completed and Project views. They can
link to a calendar block, contacts, a project and an existing Agent execution
attempt. Completing/reopening a personal task does not run or complete an Agent
attempt. Scheduling creates a block only when explicitly saved.

## Calendar semantics

Timed events are timezone-aware; all-day events use dates with exclusive end
dates. Common daily/weekly/monthly/yearly RRULE patterns, intervals, selected
weekdays and count/until endings are supported. Query ranges and expansion work
are bounded. Invalid DST starts are skipped without consuming recurrence count;
ambiguous local input requires a first/second-clock-occurrence choice. Exceptions
retain the original occurrence identity. Editing/deleting one occurrence is
distinct from changing the series. Advanced “this and following” series splitting
and drag/resize are not offered. Local attendee references send no invitations.

Free-time calculation merges overlapping/adjacent blocking intervals and applies
selected visible calendars, recurrence, all-day blocks, working hours and duration
in trusted date arithmetic. A single conversational date selects that local day;
a multi-day request supplies an exclusive end date. Returned slots are proposals,
not bookings. Save a proposed new record before linking a dependent reminder by
its persisted identity; OLIVE does not substitute an older selected record.

## Reminders

One runtime scheduler persists reminder definitions and delivery identities.
Snooze, dismiss and history are in the same in-app activity experience. Navigation
and renderer reload do not schedule duplicate workers. Linked edits update future
pending deliveries; completion/deletion cancels relevant pending reminders.

Reminders work only while OLIVE's runtime runs. There is no Windows service or
promise of alerts while the PC/app is off. Restart catch-up produces a bounded
summary and retains history. Delivery is persisted before the UI event; a crash
between those steps can leave a history entry without a popup. This is not a
claim of perfect exactly-once notification delivery. Restoring an old backup
suppresses overdue restored work rather than replaying a flood of alerts.

## Imports, exports and privacy

Use native file selection to preview CSV/vCard contacts or ICS events. Review
record details, validation errors, source fingerprint and create/update/skip
choices before committing. Unchanged source/UID content is skipped; deleted
sources are not silently reactivated. A partial import requires an explicit
choice and reports saved/skipped/error counts. Export is local only.
Exports replace the selected destination atomically; cancellation before replacement
keeps the previous file. Native file selection cancellation is reported separately.

Sources are bounded to 2 MB / 2,000 records, and a preview to 500 KB; split larger
inputs into reviewed batches. CSV exports escape spreadsheet formula prefixes.
Unknown CSV column values are not retained, and the preview says so. Unsupported
vCard fields retain bounded excerpts (up to 1,000 characters each) but are not
re-exported. ICS retains supported events plus original unsupported material where
it fits record limits; unsupported schedules are reported instead of silently
substituted. These are not lossless round-trip guarantees for arbitrary extensions.
No import executes HTML, follows remote URLs, sends invitations or changes policy.

## Storage, permissions and backup

`olive/personal/` owns `personal.sqlite3` under the configured OLIVE data profile
(normally `~/.olive`). React has no direct database access. Schema 4 adds the verified default-calendar relationship; schema 3 adds provenance
to schema 1/2 records without changing IDs or rewriting older OLIVE stores. Records
carry timestamps/revisions; writes reject stale revisions. Import provenance
retains source format, UID and fingerprint; old records without such evidence
are not assigned invented historical provenance.

The narrow bridge calls the same ToolRegistry, permission service, executor and
confirmation service used by native language capabilities. Explicit Deny remains
effective. Ordinary direct form edits use scoped direct-action consent. Destructive
operations, merges/import commits and conversational saves retain their required
action-bound approvals. A changed proposal cannot reuse an obsolete approval.

Settings → Backup & Data includes native records and relationships using SQLite's
backup API, including committed WAL content. Restore validates/stages components,
makes a safety backup, quiesces affected work, replaces safely and requires restart.
Credentials are not portable backup components; external actions are not replayed.
Restore rejects missing Project/Agent references before replacement. Include those
components when native records link to them. Older native schema snapshots are
validated before additive migration; no original user source is deleted.
Actual isolated native-confirmation restore evidence is retained under
`artifacts/ui-review/M3/final-regression-04/screens/backup-result.json`. Earlier failure evidence remains separate.

Qt remains the tested fallback for its existing features; no new Qt Personal Core
screens are created. Old Qt views do not display these new domains, and compatibility
with future schemas must not be inferred. Credential-vault protection is distinct
from ordinary local data storage: this implementation does not claim all personal
data is encrypted or that Welcome authenticates the user.

## Dependencies and release packaging

`requirements-personal.txt` pins icalendar 7.3.0 (BSD-2-Clause), python-dateutil
2.9.0.post0 (Apache-2.0/BSD dual licence), tzdata 2026.3 (Apache-2.0 package;
IANA data notices), vobject 0.9.9 (Apache), pytz 2026.3.post1 and six 1.17.0 (MIT).
These are project-local Python dependencies, not online account services.
See [RFC 5545](https://www.rfc-editor.org/rfc/rfc5545) for interchange semantics,
[icalendar documentation](https://icalendar.readthedocs.io/) and
[dateutil recurrence documentation](https://dateutil.readthedocs.io/en/stable/rrule.html).
The existing Pillow installation handles local avatars; imported images are
decoded, resized and re-encoded without remote fetching.

The later clean-machine backend artifact must include `tzdata/zoneinfo`, library
metadata/licence notices and the pinned parser modules. Source/virtual-environment
testing verifies Windows timezone availability; it does not establish a portable
clean-machine build. No runtime/model download or auto-update was introduced.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
