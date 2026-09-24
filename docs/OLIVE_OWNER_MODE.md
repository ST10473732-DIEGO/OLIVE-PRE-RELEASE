# OLIVE Owner Mode

Implementation checkpoint: 24 September 2026. This work continues the approved
`feature/olive-unified-agent` repair branch. Repair baseline is
`f7efb5034b3b3c1fe43680570c03fefbcb440822`; the Owner Mode continuation started
from `a02d2f204ffb74228b6ddf05133071eb714354e0`, preserving the pending desktop repairs.

Owner Mode does not make the language model root. It allows OLIVE Core to
invoke owner-authorized capabilities through typed brokers.

## Authority and boundaries

`olive.authority.owner.OwnerPolicy` is an in-process capability-broker policy,
not a new privileged service. The authenticated renderer/private bridge opens a
request context. The installation identity is an opaque persisted UUID bound to
the current OS user (UID on Linux). Same-user malicious processes are not a
sandbox boundary. No model or wire API imports grants or provisions permissions.

A grant records a task ID, local owner and installation identity, original
request digest, capabilities, directional source/destination or selected
workspace, expiry and cancellation epoch. It lasts at most ten minutes, ends
with the request, and reserves a mutation once before dispatch. Read observations
cannot extend its resources. Model fields such as `approved`, `owner_mode`,
`permission`, `ignore_user_policy`, `disable_stop`, `grant_root` and
`extra_recipient` cannot confer authority.

Implemented silent tool authorization covers resolved ordinary file copy/move,
scoped single-file creation/editing and detected Studio run/validation. Other
capabilities retain their existing typed controllers and user-request contracts;
this is not a claim that every listed OS capability is implemented. Unresolved
relative paths still require target resolution. Overwrite on copy/move remains
blocked, and security-credential directories use the separate high-impact path.
Ordinary delete-to-Trash and broader OS settings need their own supported typed
operations; no unrestricted terminal or root tool was introduced.

Explicit permission Deny is evaluated before Owner Mode. A move checks write
restrictions on both source and destination. File targets must remain owned and
must not traverse symbolic links. Studio commands are detected from the approved
workspace and checked again by the existing tool; model command strings do not
become validation commands. Existing trust/isolation requirements still apply.

Native desktop task grants retain their shorter five-minute expiry, exact scope,
fresh observation, effect ledger, Stop and helper watchdog. Owner Mode can resolve
ordinary input Ask within that grant; Deny, persistent disable and portal revocation
still win. Revoking Owner Mode invalidates grants and requests desktop Stop before
settings persistence. A new explicit request can receive a new independent grant.
The KDE compatibility identity remains `local.dmdo.desktop`.

Remote-target Chat never enters an owner context. C1–C8 use their existing exact
remote capability rules. No remote desktop, clipboard or Owner Mode capability
was added. Browser/document/source text and model proposals remain untrusted data.
Credentials, authentication, payments, security changes and unbounded destructive
operations are outside this ordinary-task policy.

## Installation migration and rollback

Version 1 was explicitly provisioned for this installation with
`scripts/provision_owner_mode.py`. It records timestamp, installation identity,
previous values and new value in the private receipt
`~/.local/state/olive/setup/owner-mode-v1.json`. It changed only `owner_mode` and
`owner_installation` in the resolved profile settings. Permission rows, Connect
rules, portal grants and other installations were not changed. Fresh installs
default to disabled. Re-running an existing receipt never silently re-enables a
revoked setting.

The setting is visible in Settings → Privacy & Security → Permissions as
“Owner Mode — ordinary explicit local tasks”. Disable there to revoke. To roll
back the unchanged migration, close OLIVE and run:

```sh
.venv/bin/python scripts/provision_owner_mode.py \
  --receipt "$HOME/.local/state/olive/setup/owner-mode-v1.json" --restore
```

Restoration refuses a mismatched owner/profile or subsequently changed setup;
it preserves unrelated settings. The receipt stays outside Git.

## Acceptance status

Policy fixtures currently pass actual owned-file move/edit with zero prompts,
Deny, reverse/changed target, remote context, quoted/source injection,
self-approval fields, symlink, expiry, Stop/fresh task, detected workspace commands,
and migration idempotency/rollback checks. These are **FIXTURE_ONLY** authority
checks until the production Chat acceptance matrix is completed. Native Copy and
Kate paste live proof belongs to the Chat repair report; it is not itself proof
of all Owner Mode effects.

The existing executor, permission service, desktop gateway and app controllers
form the broker boundary for future separate apps. No root daemon, OLIVE OS,
C9 or C10 implementation is included. No automatic push is authorized.
