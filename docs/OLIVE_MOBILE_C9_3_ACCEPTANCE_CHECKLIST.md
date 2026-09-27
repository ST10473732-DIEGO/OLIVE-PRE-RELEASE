# C9.3 remaining physical checks — updated 2026-09-27

**Current gate audit:** the owner completed the C5 and C8 policy/deletion/editor
batches and all three final Chat checks. Do not repeat those sections. Remaining
unproven gate observations are exact desktop presence-label timing during a
successful file transfer and independent system expiration during active C7 Chat.
The latter cannot be deterministically forced through a public API; system Stop
is separately passed, and network timeout is not proof of system expiration.
The primary report retains PARTIAL status and all earlier failed runs.

The normal phone app is installed and available. Automated phone tests are
finished for this batch. Use only the owned `C93 Acceptance ...` records and
fixture directory printed by setup. No re-pairing or desktop installation is
needed. Report exact failures; do not silently work around them.

## 1. Today — final desktop deletion check

**Passed by owner:** synthetic Task, Calendar event and linked Reminder deleted
on desktop. Do not repeat the checks below; they describe the completed procedure.

Phone creation, bidirectional edits, four-domain conflicts/resolution, recurring
Calendar exceptions and linked Task completion have passed. The phone has now
explicitly tombstoned the synthetic Task, Event and linked Reminder; repeated
sync and a fresh store load passed.

1. On desktop confirm **C93 Acceptance Task Desktop Conflict** and **C93 Acceptance
   Calendar Desktop Conflict** are removed, and the linked reminder schedule is
   removed. The empty **C93 Acceptance Calendar** may remain.
2. Do not recreate these records or repeat the already-passed edits.

## 2. Selected Chat — final desktop deletion check

**Passed by owner:** Shared Chat deleted; Private remains unselected on desktop.
The deletion checks below are complete. The optional idle availability-probe
observation was not separately reported in this batch.

Selection, unselected isolation, stable ordered IDs, mobile turn exactly once,
conflicts/resolution and FIRST-prompt tombstone across two real app relaunches
passed. The bot's FIRST reply correctly remained when only its user prompt was
deleted. The phone has now deleted the entire synthetic shared conversation.

1. Confirm **C93 Acceptance Chat Desktop Conflict** is removed on desktop.
2. Confirm **C93 Acceptance Private** remains on desktop. Do not select it for
   sync. Open it briefly while the phone is connected; the phone should remain
   connected. This exercises desktop model-availability probes after the fix.

## 3. Files — remaining permissions, collision, revocation and timing

The latest owner attempts were rejected at zero bytes. The read-only desktop
count confirmed six completed files totaling 207 MiB; another 64 MiB exceeds the
256 MiB quota. Completed transfers count even after Save. On desktop, Save if
needed, then Dismiss from Inbox one completed owned 64 MiB test transfer before
the timed repeat. Retain user files. The updated phone explains quota rejection
and missing receipts explicitly.

**Instagram repeat completed:** after the 54.00% expiration, a fresh explicit
owner attempt completed all 64 MiB in 69.228 seconds with a real background grant
and success recorded. Keep both results; no root-cause fix is claimed. The USB
scheduler trace captured admission but hit its byte limit before completion.
Do not repeat the successful transfer solely for that trace. Exact desktop UI
presence timing is still open. Collision and active permission revocation/no replay
now have owner confirmation; the phone journal corroborates an interrupted active
transfer. Save/dismiss only owned completed fixtures if quota blocks later checks.

The 5 MiB/64 MiB round trips, hashes, quarantine/export, background Stop,
network loss and force quit already passed. The real invalid-hash rejection,
durable failed receipt, oversized metadata rejection and disconnected-channel
rejection also passed. Do not repeat those successful transfers unnecessarily.

1. **Passed:** desktop Receive files Off blocked phone sending; Ask completed
   after one approval; Allow completed without approval. Do not repeat this matrix.
   **Passed:** owner confirmed the existing `collision.bin` Save protection check.
   Do not repeat it or authorize replacing that fixture.
2. **Passed:** Send selected files Off blocked desktop sending; Ask completed
   after one approval and phone acceptance; Allow completed without another
   desktop approval, retaining phone acceptance. Change both file permissions
   back to Off and confirm new sends are denied; then restore Allow for steps 3–4.
3. Start the observer on CachyOS, then send the saved 64 MiB file from phone and
   use another app for 60 seconds. Watch desktop Devices. Note the observer's
   elapsed time when Offline first appears and whether bytes were still growing.
   Paste the observer output. It also checks the invalid-hash artifact absence.

   ```sh
   # CachyOS Fish shell, from the OLIVE checkout; use its resolved profile.
   set OLIVE_C93_DB (.venv/bin/python -c 'from olive.identity import resolve_profile; print(resolve_profile() / "connect" / "devices.sqlite3")')
   python3 /tmp/olive-c93-acceptance-fixture.py observe --database "$OLIVE_C93_DB" --seconds 180
   ```

   Use OLIVE's actual configured profile if different; do not copy databases.
4. **Passed:** owner confirmed no restart after Receive files Off → Allow in the
   active-transfer test. The phone journal shows interruption at 11,141,120 bytes
   with unsuccessful system completion. Exact desktop wording/artifact inspection
   was not separately provided; do not equate this with device trust revocation.
5. If the owned 65 MiB fixture is already accessible in the phone's system file
   picker, select it and confirm **File too large** before transfer. Otherwise
   report picker case NOT RUN; do not try to send it through C6 to arrange this.

## 4. Sync / Studio permission matrix and Studio draft safety

**Passed by owner:** all four Sync domains, all five Studio scopes, and native
editor stale-save refusal with draft retention. Do not repeat the procedures below.
Optional fixture text restoration was not separately confirmed.

Keep desktop Remote AI Allow unchanged. No Owner Mode. Scope changes may cancel
active jobs, so wait for each operation to end before the next policy change.

1. **Passed by owner:** Sync Tasks, Calendar, Reminders and Selected chats each
   passed Off → Ask → Allow → Off, explicit phone Sync after each change, approval
   without duplication under Ask, no approval under Allow, and restoration to
   Allow afterward. Do not repeat this matrix.
2. On desktop shared **C93 Acceptance Shared** workspace, cycle each permission
   **view/edit/build/test/run** through the same sequence using phone Refresh /
   Save / Build / Test / Run respectively. Keep other required scopes allowed.
   Ask approval must continue the same save/job once. Cancel the 75-second Run
   explicitly after checking admission. Restore Allow between scopes. After each
   policy change, refresh workspaces and reopen the share before the tested
   operation so its share revision is current; keep other scopes Allow.
3. Phone Studio: open `notes.txt`, edit it to `C93 Acceptance phone draft` without
   saving. On desktop edit that owned file to `C93 Acceptance desktop newer` and
   save. Attempt phone **Save with revision check**: stale refusal, phone draft
   retained, desktop text unchanged. Then reload/discard only the synthetic draft.
   Restore `notes.txt` to `C93 Acceptance original` plus a newline on desktop.

Shared/unshared isolation, tree/read/save/hash, protocol stale refusal, Build,
Test, Run, 65-second background completion, Cancel and 80-second channel-loss /
no-replay observation already passed. No need to repeat them here. Mobile has no
terminal, PTY, debugger, package installation or Owner Mode controls.

## 5. Final Remote AI regression and connection-loss recovery

**Steps 1–3 passed by owner:** reconnect/Allow/code, Stop/new request, and Wi-Fi
loss/recovery. Exact reported failure: “Failed The request timed out Draft restored
nothing was resent.” The journal corroborates interrupted `requestTimeout` and a
later explicit successful request. Step 4 remains unproven for independent C7
expiration; do not relabel the already-passed system Stop as that event.

1. Background the idle phone, then reopen OLIVE: reconnect without re-pairing,
   desktop Remote AI Allow retained. Ask for a short Python function in a fenced
   code block; verify completion and code rendering.
2. Start a longer harmless response, tap Stop while active, then send a new short
   request and verify success.
3. Start another response, switch apps and turn Wi-Fi off while it is streaming.
   Restore Wi-Fi and return: partial/interrupted state, no automatic resend,
   preserved draft behavior, and a new explicit request works. Do not increase
   inference limits for the test.
4. If iOS independently expires active work, record the exact state and recovery.
   System Stop is already tested but is not evidence of independent resource
   expiration. If expiration is not observed, report NOT OBSERVED; it remains open.

Send one combined reply: `1 Today: ...; 2 Chat: ...; 3 Files: ...; 4 Permissions /
Studio draft: ...; 5 Remote AI: ...`, with exact errors and observer output.
Use NOT RUN for untested items. These are the remaining physical checks, not a
request to repeat the passed C9.3 acceptance suite.
