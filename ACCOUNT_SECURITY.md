# OLIVE local identity and protected Mail credentials

Welcome is not authentication or a lock screen. A profile is not an online account.
Optional Mail connections do not invent a routable email address.

The existing trusted `olive/services/credential_vault.py` uses current-user Windows
Credential Manager through installed pywin32. Profile-path namespaces and opaque
connection-specific references isolate secrets. Legacy namespace identities stay
stable: branding is not security authority. Persistence across logons does not
enable machine-wide decryption.

A dedicated masked transient control and validated storage endpoint accept a
secret. The renderer receives only opaque references; no generic renderer/model
secret getter exists. Trusted transport code retrieves credentials only for the
configured connection. Replacement writes a new vault record before committing
its reference; failure preserves the prior credential. Vault failure never falls
back to plaintext. Secret-entry exceptions do not retain provider exception chains
in the protocol response or cached task state.

Secrets are excluded from general React state, localStorage, prompts, snapshots,
diagnostics, Knowledge, Memory and portable backups. The field is cleared after
use where practical; managed-language memory is not claimed perfectly erasable.
Tests use isolated dummy credentials, including real save/read/delete and
cross-profile isolation.

The vault does **not** protect against every malicious same-user process.
Ordinary Mail/personal databases and exports are not automatically encrypted.
TLS is not end-to-end mail encryption. Backups/EML may contain readable personal
content. Restored connections need review and new credentials; sends never replay.

UI and natural-language actions use the shared ToolRegistry, PermissionService
and ConfirmationService. Explicit Deny wins over manual form convenience. Send
approval binds connection revision, sender, envelope, body, attachment hashes and
submission fingerprint. Changes require renewed review. Mail content and models
cannot approve actions. Diagnostics expose request/stage/category/connection IDs
and counts, never raw AUTH or full message bodies.

Mail HTML combines DOMPurify with an opaque sandbox and restrictive CSP: no
application bridge, scripts, forms, remote resources or automatic navigation.
CID raster images are validated/re-encoded; dangerous paths and active images
are rejected. Attachments are immutable untrusted blobs, never executable paths.
Reading mail does not execute or index attachments.

Electron sender/origin validation, sandbox/context isolation, profile ownership,
cancellation and existing desktop safeguards remain. M4 evidence is not an
independent security audit or universal provider certification. No real credentials
or accounts were used. See [transport limits](MAIL_TRANSPORTS.md) and
[M4 evidence](docs/releases/3.5.1/M4_COMPLETION.md).


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
