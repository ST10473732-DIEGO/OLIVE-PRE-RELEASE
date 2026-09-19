"""Build the 3.5.1 ledger; preserve all inherited obligations and explicit status."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/releases/3.5.1'
# Semicolon-separated independently verifiable obligations, grouped by source section.
SECTIONS = '''
1|M0|Inspect clean/dirty Git state; Inspect current branch; Verify release tags without moving them; Audit actual services and dependencies; Read current architecture/security/plans; Branch from current checkpoint; Record implemented versus contract-only scope; Run existing Python harness; Run Qt harness; Run language harness
2|M4|Preserve one local-first platform; Migrate every shipped frontend feature; Preserve Python intelligence; Complete native Personal Core; Keep external application capabilities; Exclude trading/wallet execution; Exclude voice/training/Tor expansion; Exclude mandatory cloud accounts; Exclude hosted mail deployment/sync/service
3|M0|Create PLAN; Create STATUS; Create REQUIREMENTS; Create PARITY; Create ACCEPTANCE; Carry unfinished 3.5 obligations individually; Record classification/location/evidence/status/limitations; M1 actual application launch; M1 screenshots; M1 interaction recording where supported; M1 Python streaming; M1 safe save; M1 real tests/output; M1 measured performance; Stop for explicit M1 user approval
4|M0|Retain Qt fallback; Isolate comparison profiles; Prevent simultaneous profile writers; Preserve data locations/formats; Retain Qt modules until parity; No hidden legacy GUI; Extract only required orchestration
5|M0|Electron; React; Strict TypeScript; Maintained bundler; Local Monaco; xterm.js; Motion; Central CSS tokens; One accessible component foundation; One packaged icon family; Pin compatible dependencies; Commit lockfile; Focused modules; No dashboard template
6|M0|Narrow preload; Main-process validation; Private process transport; Python authoritative services; Main owns lifecycle/dialogs/supervision; Renderer cannot access DB/Ollama; No unauthenticated network API
7|M1|Versioned request contract; Request IDs; Task IDs; Validated method arguments; Ordered events; Typed success/error; Cancellation; Timestamp evidence; Explicit method allowlist; Stream model output; Progress events; Approval events; Build output; Snapshots; Recovery without replay; Bounded frames; Backpressure; Timeouts; Unsubscribe; Separate stdout/logs; Partial frame handling; Malformed input rejection; Explicit Python executable/arguments; No shell interpolation; One backend per profile; No orphan workers; Refresh cannot replay tools; Crash cannot repeat uncertain actions; Shutdown rejects new work; Shutdown cancels/pauses safely; Flush persistence; Close connections; Stop desktop input on UI loss
8|M0|nodeIntegration false; contextIsolation true; sandbox true; webSecurity true; No raw ipcRenderer; No arbitrary fs/shell/secret bridge; Validate sender/frame/origin; Validate payload/context; Restrictive production CSP; Local custom protocol; Restrict navigation; Restrict windows; Deny unexpected permissions; Validate external URLs; Untrusted content has no preload; No generated JS execution; Preserve execution isolation; Document same-user limitation
9|M1|Distinct OLIVE design; Ink/navy surfaces; Restrained blue accent; Readable typography; Purposeful spacing; Compact workspace density; Dark tokens; Light tokens; Semantic colours; Licensed/system fonts; No fake metrics/decorative controls
10|M1|Core journey; Universal command surface; Inspect/clear context chips; Activity/approvals; Contextual handoffs; Exact Continue context; Progressive details
11|M1|Reuse actual olive source unchanged; Inspect transparent derived assets; Small-size icon review; Window icon; Taskbar identity verification; Packaging icon; Built shortcut/executable verification conditional; Blue vector Core; Real service states; Text state labels; No fake progress; Reduced/hidden motion
12|M1|Minimal Welcome; Fast first frame before optional readiness; No model load for Welcome; Skippable short Enter transition; Keyboard entry; Skip Welcome preference; Home never reopens Welcome; No fake authentication; Enter offline local features
13|M1|Greeting; Universal composer; Chat/Agent/Studio/Research entrances; Continue; Real contextual activity; All shipped spaces discoverable; Same card system; Responsive grid; Search; Pin/unpin; Favourite ordering; Keyboard navigation; Unavailable states; Empty search state; No invented activity
14|M1|One primary BrowserWindow; No rail on Welcome; Compact workspace rail; Expandable labels; All Spaces access; Native drag/snap/maximise/minimise/restore; DPI/multiple-monitor testing; Short consistent motion; Reduced motion; No hover-only actions; Persist navigation state; Bound hidden editor resources
15|M1|Content-sized messages; Readable width; Markdown/code/tables; Source cards; Attachments; Streaming; Contextual actions; History/search; Sticky composer; Stop; Regenerate; Branches; Model selection; Project association; Draft persistence; Task/event deduplication; Evidence-based result states; Expandable diagnostics
16|M2|Agent idle objective/context/history; Active timeline/validation/files; Pause/stop/resume; Desktop objective/current app/verification; Emergency stop visible; Discoverable developer details; Focus/takeover guards; Main-process stop fallback; Honest vision limits; Supported Discord bot boundaries; No user-token/prohibited automation workaround
17|M1|Locally bundled Monaco editor; Explorer; Multiple tabs; Dirty markers; Syntax; Cursor/selection; Find/replace; Go-to-line; Bracket matching/folding; Diagnostic markers; Diff review; Resizable assistant; Resizable bottom panel; Retain models/view state; Dispose unused models; Local workers; No false LSP/debugger claims; No silent language-server install
18|M1|Same real files for user/agent; Approved roots; Bounded reads; Expected hashes; Checkpoints; Conflict detection; Task rollback; Git review; Unsaved buffers survive agent disk change; Compare/reconcile; Run; Stop; Restart; stdout/stderr; Exit state; Compiler errors; Test results; Artifacts; Authorised previews; xterm output through backend; Distinguish output/structured command/user terminal; No fake PTY; Preserve generated-code isolation
19|M2|Separate untrusted previews; Bind preview to RunSession; Validate local origin/port; Isolated session; No app preload; Block navigation; Sanitise Markdown/HTML; Validate external schemes; Terminal content cannot invoke commands; Native apps separate when authorised
20|M2|Research question/depth/activity/findings; Sources/evidence/history; Website learning/cancel/project links; Projects search/create/open/relationships; Knowledge health/index/relink/reindex/remove/jobs/inspector; Memory CRUD/search/suggestions/source/export; Settings full validated parity; Searchable categories; Safe diagnostics copy/export; Action-level acceptance
21|M3|Audit/reuse native services; Native Identity; Native Contacts; Native Calendar; Native Tasks; Native Reminders; Native Mail; Stable IDs; Revisions/timestamps; Provenance/project relationships; Transactional local storage; No gratuitous old-store migration; Distinct PersonalTask/AgentTask; Domains through UI/Home/Chat/Agent
22|M3|Profile name/avatar/timezone/locale/hours/calendar/preferences; Skippable setup; No invented email identity; Contacts labelled email/phone; Names/organisation/aliases/notes/identifiers/projects; Contact CRUD/search/detail; Duplicate suggestions; Explicit merge preview; CSV import/export; vCard import/export; Evidence-based recipient resolution; Clarify multiple recipients; Bounded relevant contact context; South African English default; Confirmable environment timezone
23|M3|Month; Week; Agenda; Multiple calendars; Event CRUD; Search/Today navigation; Recurrence; Availability; ICS import/export; Aware timed events; Date-only all-day events; Exclusive end dates; Exceptions; Occurrence/series distinction; Bounded expansion; DST tests; Unsupported import reporting; Deterministic arithmetic; Task fields/status/priority/due/project/links/completion; Today/upcoming/completed/project views; Persistent reminders; Snooze/dismiss; Delivery deduplication; Restart catch-up; Running-app-only delivery; No always-on service; Invitations require approved transport
24|M3|Mail folders; Messages/threads; EML import/export; Draft CRUD; Complete From/To/CC/BCC/Subject/Body composer; Outbox; Attachments; Search; Read/unread; Archive/trash; Reply/forward as drafts; Project links; Truthful disconnected state; Offline draft/import/search/export; SMTP interface/implementation; IMAP interface/implementation; Validated TLS; Bounded retries/timeouts/sizes/batches; Incremental mailbox state; Add/edit/test/capabilities/disconnect connection; Remove credentials; Explicit cache management; Test sends no email; Submission state machine; Acceptance not delivery; No retry uncertain sends; No restart/restore outbox replay
25|M3|Windows-protected vault; Opaque references; No invented encryption; Trusted provider secret access only; Masked transient secret entry; No secret logs/prompts/localStorage/backups; Document vault limits; Safe MIME; Header injection rejection; Sanitised HTML; Block tracking; Safe attachment paths; No auto-execution; Approval action/revision/arguments binding; Destination/content/hash binding; Edits invalidate approval; Revalidate execution; Untrusted content cannot authorise; Preserve direct manual edit policy
26|M3|Same NLO/CapabilityRouter; No React parser; File reference follow-ups; Draft recipient/attachment corrections; Event time correction; Research/project composition; Cross-route context; Distinct pending actions; Conservative ambiguity; Contact to Mail; File to Mail; Mail to Calendar proposal; Calendar to Mail draft; Project to Task/Calendar; Home/Chat access; No silent Gmail fallback; Preserve measured model roles; No new models/training
27|M1|Immediate submission feedback; Distinguish interpretation/model loading/working/waiting/verifying/final states; No invented percentages; Human-readable consequential preview; Expandable technical details; Edits invalidate preview; Backend cancellation; Preserve focus/takeover
28|M4|Measure cold/warm startup; Welcome first frame; Cached navigation; Chat streaming; Monaco typing; Output rendering; Idle memory; GPU use; Combined inference resources; Lazy heavy routes; Bounded editor models/lists; Throttle rendering not input; Hidden animations stop; No global GPU-disable workaround; Compare Qt before default switch
29|M4|1366x768; 1920x1080; 100/125/150 percent scaling; Multi-monitor where available; Keyboard-only; Reduced motion; Light/dark; Text scaling; Visible focus; Accessible names; Tab order; Contrast; Non-colour states; Command palette shortcut/UI; Navigation/new chat/workspace/research/project/mail/event/settings/diagnostics commands; Settings search; No certification claim
30|M4|Preserve data paths; Additive migrations; Consistent SQLite backups; Isolated restore; Schema validation; Rollback; IDs/relationships retained; Credentials excluded; No external action replay; Document Qt rollback schema limits; No personal data in Git; Local search privacy
31|M4|Retain Python tests; Equivalent frontend coverage before Qt test retirement; Typecheck; Lint; Components; Contracts; Electron integration; E2E; Screenshots; Bridge/security tests; IPC rejection; Backend crash; Renderer reload; Cancellation; Approval binding; Deduplication; Stream recovery; State retention; Monaco conflicts; Run/output; Persistence; Offline; Secret exclusion; Untrusted rendering; Isolated fixtures; No real sends/private account/desktop/model-loading in ordinary tests; Evidence classification
32|M4|Live launch/Enter/Home; Harmless real Python Home result; Real Chat stream/cancel/retention; Monaco approved workspace/edit/save/tests; Agent/dirty-buffer conflict; Contact/calendar correction/restart; Mail correction/cancel/no-send; EML to approved event; Simulated offline; Interruption safe recovery; Isolated backup/restore; Research integration; Authorised desktop integration without Qt; External mail only approved server
33|M4|Actual Welcome screenshots; Home empty/populated; All Spaces; Chat code/tool result; Agent idle/active; Monaco/output; Research/sources; Desktop; Projects; Knowledge; Memory; Settings; Contacts; Calendar three views; Tasks; Mail states; Approvals; Actual transitions; Fixture labels; Visual hierarchy/spacing/density/focus/scroll/resize/motion review; M1 user approval; Final user approval
34|M4|One packaging path; Bundle frontend/workers/icons/licences; Package Python runtime and dependencies; No developer virtualenv dependency in package; Appropriate writable data/resources; No Vite/CDN/Internet production dependency; Validate assets; No silent runtime downloads; Packaging smoke; Separate clean-machine evidence; No publishing/signing purchase/autoupdate; Default switch only after parity/approval; Tested fallback
35|M4|All applicable inherited scope accounted; Individual acceptance; No v3.5.0 filler tag; Preserve tags; Backend regressions pass; Frontend/contracts/Electron pass; Existing action parity; Native Core complete; Live demos; Security; User approval; Packaging status; Clean tree; Annotated v3.5.1 only after acceptance
36|M1|Accurate checkpoint docs; Meaningful commits; Honest baseline/architecture/security/features report; Evidence/performance/dependency/migration/package report; Exact remaining limits/tag status; Implement real M0/M1; Stop before design propagation for approval
'''


def main():
    path = OUT / 'requirements.json'
    if path.exists():
        rows = json.loads(path.read_text(encoding='utf-8'))
    else:
        rows = []
        for line in SECTIONS.strip().splitlines():
            section, milestone, descriptions = line.split('|')
            for number, description in enumerate(descriptions.split('; '), 1):
                rows.append(dict(id=f'R351-{int(section):02}-{number:02}', description=description,
                    source=f'3.5.1 section {section}', classification='mandatory', milestone=milestone,
                    implementation='Pending', acceptance='Focused test or live/visual check of this obligation',
                    status='not implemented', evidence='Not tested', limitation='No scope reduction agreed',
                    implemented=False, unit_tested=False, integration_tested=False, live_tested=False,
                    visually_reviewed=False, user_approved=False))
        for old in json.loads((ROOT / 'docs/releases/3.5/requirements.json').read_text(encoding='utf-8')):
            row = dict(old)
            row.update(id='C' + old['id'][1:], source=f"3.5 section {old['source']} ({old['id']})",
                milestone='M3' if old['milestone'] in ('M3', 'M4', 'M5') else 'M2' if old['milestone']=='M2' else 'M4',
                status='carry-forward audit pending', evidence=f"Historical status only: {old['status']}; {old['evidence']}",
                limitation='Qt-specific presentation is superseded by 3.5.1; underlying functionality remains required. Applicability must be audited individually.',
                implemented=False, unit_tested=False, integration_tested=False, live_tested=False,
                visually_reviewed=False, user_approved=False)
            rows.append(row)
        path.write_text(json.dumps(rows, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    assert len({r['id'] for r in rows}) == len(rows)
    text = ['# OLIVE 3.5.1 individual requirements', '',
        'M2 is accepted for progression; M3 remains complete. M4 native Mail implementation and classified internal acceptance are recorded in M4_COMPLETION.md, with action-level mapping in M4_PARITY.md. Final release/packaging approval remains separate. No release tag. Historical evidence and all inherited obligations remain in force.', '',
        'Editable source: requirements.json. Render: `python scripts/electron_requirements.py`.',
        'New master obligations and every inherited 3.5 row are retained. Carry-forward audit pending is not acceptance.',
        'Framework-specific conflicts require an explicit supersession reason; no mandatory product scope is silently removed.',
        'I/U/X/L/V/A = implemented / unit / integration / live / visually reviewed / user approved.', '',
        '| ID / source | Requirement | Class / milestone | Implementation / acceptance | I/U/X/L/V/A | Status / evidence / limitation |',
        '| --- | --- | --- | --- | --- | --- |']
    for r in rows:
        cells = [r['id']+' / '+str(r['source']), r['description'], r['classification']+' / '+r['milestone'],
                 r['implementation']+' / '+r['acceptance'], '/'.join('yes' if r[k] else '-' for k in
                 ('implemented','unit_tested','integration_tested','live_tested','visually_reviewed','user_approved')),
                 r['status']+'; '+r['evidence']+'; '+r['limitation']]
        text.append('| '+' | '.join(str(c).replace('|','/').replace('\n',' ') for c in cells)+' |')
    (OUT/'REQUIREMENTS.md').write_text('\n'.join(text)+'\n', encoding='utf-8')
    print(f'{len(rows)} individually tracked rows; no completion inferred.')


if __name__ == '__main__':
    main()
