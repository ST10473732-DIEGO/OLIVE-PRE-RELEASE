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
single-file Trash, scoped creation/editing, detected Studio run/validation and
explicit named console starter creation in Python, C#, Java and JavaScript. Other
capabilities retain their existing typed controllers and user-request contracts;
this is not a claim that every listed OS capability is implemented. Unresolved
relative paths still require target resolution. Overwrite on copy/move remains
blocked, and security-credential directories use the separate high-impact path.
Ordinary single-file deletion uses the typed `filesystem.trash` operation and
Send2Trash; it never falls back to permanent deletion. Direct literal file
contents are bound by a digest, so a model cannot change them. Broader OS settings
remain limited to existing supported capabilities; no unrestricted terminal or
root tool was introduced.

| Capability | This milestone |
|---|---|
| App launch/focus, scoped observation/input, browser navigation/search | Existing unified task broker, explicit local task, no new per-click approval |
| Copy/move/create/edit and single-file Trash | Owner task policy binds exact resources; no redundant Ask; collisions and Deny preserved |
| Named Studio console starter, run and detected validation | Scoped existing controllers; no extra approval for the covered task; validation is not a claim that a starter contains a unit-test suite |
| Explicit messaging | Existing finite send grant; owned visible client tested; native/web Discord account/composer integration incomplete |
| Clipboard write / explicit paste | Trusted Copy IPC and existing task-scoped paste; no background clipboard read or remote exposure |
| Git, package installation, Bluetooth and every other listed ordinary OS/app capability | No blanket Owner Mode coverage claimed. Existing supported workflows remain; a complete capability-by-capability automatic-Ask migration is NOT_IMPLEMENTED |

Thus the setting is a first-class policy with live coverage for the rows above,
not a declaration that all ordinary operations across all apps now auto-authorize.

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

**IMPLEMENTED_AND_LIVE_TESTED:** normal installed-entry Chat created a Python
file, edited its exact contents, moved it and sent it to the actual system Trash
with **zero approval prompts**. The known Trash payload hash matched the original
owned fixture. No private Trash contents were inspected. Production Chat also
created Python and Java Studio starters, validated them and ran the Python
starter without redundant approval. The final restart check also selected a
workspace through Studio, opened a new Chat and ran that project with exit 0
and expected stdout, using a typed scoped workspace reference. Answer-only,
new-code/preview and remote requests cannot inherit that reference as authority.
See `docs/evidence/chat-closing-live.json`. Native Firefox search, Dolphin transfer,
owned GTK messenger sends and a generic KCalc control completed through the
existing desktop task executor. See `docs/evidence/chat-owner-live.json` and
`chat-combined-live.json`; fixture delivery is not external message delivery.

The production Chat Stop handler was tested while Firefox retained focus:
stopped state was observed in 29.90 ms, then cleanup completed. Suspending the
owned backend's heartbeat made the independent helper exit in 1,728.79 ms.
New explicit tasks recovered after both tests without old-task replay. These
measurements do not claim physical shortcut testing or hardware release latency.
See `docs/evidence/chat-stop-live.json`.

**FIXTURE_ONLY** authority/adversarial checks cover explicit Deny, source-write
Deny on move, reverse/changed target, remote context, quoted/source injection,
all seven self-approval fields, symlinks, expiry, Stop/fresh grants, detected
workspace commands and migration idempotency/rollback. These checks preserve
Connect's independent Ask/Off/Allow behavior. User-requested delete grants Trash,
never the critical permanent-delete operation. A file or workspace already
selected in the UI does not grant an answer-only request modification rights.

Send2Trash 2.1.0 (BSD-3-Clause) is a normal Python dependency. Its wheel and Linux
implementation were inspected before installation into the existing venv;
SHA-256 `0da2f112e6d6bb22de6aa6daa7e144831a4febf2a87261451c4ad849fe9a873c`.
Rollback of the feature uses Git revert and the migration receipt. No system
package manager, root privilege or shell interpolation handles file contents.

The existing executor, permission service, desktop gateway and app controllers
form the broker boundary for future separate apps. No root daemon, OLIVE OS,
C9 or C10 implementation is included. No automatic push is authorized.
