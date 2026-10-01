# Final milestone: phone, laptop and PC

Desktop remains Electron/React/TypeScript with Python services. This milestone
prepares contracts; it does not ship a phone client, start a server, open a
firewall port, synchronize user data, or deploy a cloud service.

Diego selected **iPhone** on 2026-09-14. The initial implementation target is an
installable Safari web client for Chat, selected notes/tasks/calendar and research
history, with offline local changes and an explicitly paired desktop AI host.
An iOS native shell remains a separate adapter if verified background/offline or
device-tool requirements exceed Safari's supported behavior. The first milestone
must test on an actual iPhone, including foreground/background transitions and
host loss; resizing Electron is not mobile acceptance. No Apple developer account,
App Store submission, paid service or network exposure is authorized by choosing
the platform. Reusing React components does not make Electron a mobile host.

This initial choice uses WebKit's supported Home Screen web-app path; see
[Safari 26 web-app support](https://webkit.org/blog/17333/webkit-features-in-safari-26-0/).
Offline storage must handle quota failures, eviction and user-cleared data,
check persistence status, and request persistent storage without promising it
will be granted. Unsynchronized changes need a visible pending state and recovery
export. See [WebKit's storage policy](https://webkit.org/blog/14403/updates-to-storage-policy/).
The implementation gate must validate device-key storage on the actual iPhone;
browser storage is not assumed to provide native Keychain or hardware-backed keys.
If the required key protection cannot be met in Safari, choose the native adapter
before implementing pairing. Loss of local keys requires explicit re-pairing.

## Boundaries

| Boundary | Contract and responsibility |
|---|---|
| UI client | Typed view models and explicit commands; no SQLite/vault/terminal APIs |
| AI execution host | Authenticated streamed inference request, request ID, cancellation, actual model/preset identity, host availability and capability response |
| Data synchronization | Collection-scoped revision envelopes and separately selected immutable blobs; repository adapters apply transactions |
| Device-local tools | Local permission service, target identity, exact payload/revision approval and local outcome ledger |

`olive/sync/contracts.py` contains executable validation for version-1 envelopes,
stable legacy-ID mapping, per-device collection/capability grants, revocation,
duplicate recognition and divergent offline changes. It has no network listener
or persistence side effects. Existing repositories keep their IDs and formats.
A migration will persist one random profile namespace and an ID map; copying an
installation must not generate a second namespace for the same record history.
An import/merge of unrelated profiles needs explicit reconciliation.

Initial collections: chat messages, notes, calendar events, tasks, saved research
sessions/evidence references and document references. Mail bodies, credentials,
pending approvals, external-action queues, terminal sessions and execution state
are excluded from the first sync milestone. Syncing a task record never runs it.
Free-form notes may contain user-written secrets; field-name validation is only
a structural guard, not a claim that arbitrary text has been scrubbed.

Each change carries schema version, collection, stable record ID, origin device,
revision, base revision, tombstone and bounded payload. The receiver applies a
change only when its base revision matches; retries are idempotent, and concurrent
edits/deletes produce a conflict with both versions retained. A production adapter
must use atomic compare-and-swap and durable change cursors. The current reference
decision function is not a production synchronization engine. Attachments use
content hashes, chunked bounded transfers and user-selected collections; missing
offline content stays explicitly unavailable. Never share live SQLite files.

## Pairing and execution protocol

1. The desktop explicitly starts a short-lived pairing window. Generate a device
   keypair in each device's secure store and show a QR invitation with a pinned
   public-key fingerprint and single-use expiring nonce. Both devices show the
   same short verification string; the user chooses permitted collections.
2. An approved deployment uses TLS with pinned peer identity (or an authenticated
   relay chosen separately). No unauthenticated Ollama, filesystem, terminal or
   control endpoints are exposed. LAN listening/firewall/remote access needs a
   separate explicit deployment approval. Cloud and paid services remain off.
3. Each request is authenticated and bound to device, request ID, expiry, nonce,
   allowed collection/capability and protocol version. Rate limits, payload bounds,
   audit records and replay protection apply. Authorization never comes from
   synchronized content or model output.
4. Revoking a device prevents further sessions and invalidates its grants. It
   cannot erase information already read on that device; remote wipe is not
   promised. Re-pairing creates a new grant and does not revive queued actions.
5. A phone can use an authorized desktop model host. The client shows offline,
   unreachable, busy, model unavailable and cancelled states separately. It never
   claims a large desktop model runs locally on every phone. External actions
   require a fresh approval on the executing device; reconnecting or syncing
   never replays email, Discord, shell commands or desktop input.

## Implementation and acceptance sequence

With iPhone selected, after desktop acceptance: extract presentation
interfaces from the private desktop pipe; implement repository change adapters
and transactional conflict storage; implement authenticated pairing and revocation
without opening a default listener; build the chosen phone client; then obtain
approval for a bounded two-device deployment test.

Required acceptance includes phone/desktop offline edits, competing edits and
delete conflicts, duplicate/reordered messages, revoked keys, unselected data,
missing attachments, unavailable AI host, cancelled streams, device-specific tools,
and proof that syncing/restarting cannot submit an external action. Test vault
exclusion and backups independently. Laptop/PC portability uses the same contracts
with installed toolchains and hardware measured per device.

## Later: OLIVE Connect World

Since this milestone, paired devices can also connect from different networks
through **OLIVE Connect World**: an outbound relay that forwards the devices' own
end-to-end TLS 1.3 session without being able to read it. Direct LAN Connect stays
preferred. No public relay is deployed by OLIVE itself; see
[OLIVE_CONNECT_WORLD.md](OLIVE_CONNECT_WORLD.md) and `world-relay/README.md`.
