"""Record explicit M1 implementation/evidence without accepting untested scope."""
import json
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'docs/releases/3.5.1'


def main():
    path=DIRECTORY/'requirements.json'
    rows=json.loads(path.read_text(encoding='utf-8'))
    if any(row.get('user_approved') for row in rows):
        raise RuntimeError('This M1 recorder must not overwrite later user approval evidence')
    # Each listed description is an audited obligation, not a whole-section pass.
    implemented={
        'Inspect clean/dirty Git state','Inspect current branch','Verify release tags without moving them',
        'Audit actual services and dependencies','Read current architecture/security/plans','Branch from current checkpoint',
        'Record implemented versus contract-only scope','Run existing Python harness','Run Qt harness','Run language harness',
        'Create PLAN','Create STATUS','Create REQUIREMENTS','Create PARITY','Create ACCEPTANCE',
        'Carry unfinished 3.5 obligations individually','Record classification/location/evidence/status/limitations',
        'Retain Qt fallback','Isolate comparison profiles','Prevent simultaneous profile writers','Preserve data locations/formats',
        'Retain Qt modules until parity','No hidden legacy GUI','Extract only required orchestration',
        'Electron','React','Strict TypeScript','Maintained bundler','Local Monaco','xterm.js','Motion','Central CSS tokens',
        'One accessible component foundation','One packaged icon family','Pin compatible dependencies','Commit lockfile',
        'Focused modules','No dashboard template','Narrow preload','Main-process validation','Private process transport',
        'Python authoritative services','Main owns lifecycle/dialogs/supervision','Renderer cannot access DB/Ollama','No unauthenticated network API',
        'Versioned request contract','Request IDs','Validated method arguments','Ordered events','Typed success/error',
        'Explicit method allowlist','Stream model output','Progress events','Approval events','Build output','Snapshots',
        'Bounded frames','Backpressure','Timeouts','Unsubscribe','Separate stdout/logs','Partial frame handling',
        'Malformed input rejection','Explicit Python executable/arguments','No shell interpolation','One backend per profile',
        'Refresh cannot replay tools','Crash cannot repeat uncertain actions','Shutdown rejects new work',
        'nodeIntegration false','contextIsolation true','sandbox true','webSecurity true','No raw ipcRenderer',
        'No arbitrary fs/shell/secret bridge','Validate sender/frame/origin','Validate payload/context','Restrictive production CSP',
        'Local custom protocol','Restrict navigation','Restrict windows','Deny unexpected permissions','Validate external URLs',
        'No generated JS execution','Document same-user limitation','Ink/navy surfaces','Restrained blue accent',
        'Dark tokens','Light tokens','Semantic colours','Licensed/system fonts','No fake metrics/decorative controls',
        'Universal command surface','Inspect/clear context chips','Reuse actual olive source unchanged',
        'Window icon','Blue vector Core','Text state labels','No fake progress','Reduced/hidden motion',
        'Minimal Welcome','Fast first frame before optional readiness','No model load for Welcome','Skippable short Enter transition',
        'Keyboard entry','Skip Welcome preference','Home never reopens Welcome','No fake authentication',
        'Greeting','Universal composer','Chat/Agent/Studio/Research entrances','Continue','All shipped spaces discoverable',
        'Same card system','Responsive grid','Search','Pin/unpin','Unavailable states','Empty search state','No invented activity',
        'One primary BrowserWindow','No rail on Welcome','Compact workspace rail','Expandable labels','All Spaces access',
        'Reduced motion','No hover-only actions','Content-sized messages','Readable width','Markdown/code/tables','Streaming',
        'Sticky composer','Stop','Regenerate','Model selection','Draft persistence','Expandable diagnostics',
        'Locally bundled Monaco editor','Explorer','Multiple tabs','Dirty markers','Syntax','Cursor/selection','Find/replace',
        'Go-to-line','Bracket matching/folding','Diff review','Resizable assistant','Resizable bottom panel',
        'Retain models/view state','Dispose unused models','Local workers','No false LSP/debugger claims','No silent language-server install',
        'Same real files for user/agent','Approved roots','Bounded reads','Expected hashes','Checkpoints','Conflict detection',
        'Unsaved buffers survive agent disk change','Compare/reconcile','Run','Restart','stdout/stderr','Exit state','Test results',
        'xterm output through backend','No fake PTY','Same NLO/CapabilityRouter','No React parser','Immediate submission feedback',
        'No invented percentages','Backend cancellation','Lazy heavy routes','Hidden animations stop','No global GPU-disable workaround',
        'Retain Python tests','Typecheck','Lint','Components','Contracts','Electron integration','E2E','Screenshots','Bridge/security tests',
        'IPC rejection','Renderer reload','Cancellation','Approval binding','Deduplication','State retention','Monaco conflicts',
        'Run/output','Untrusted rendering','Isolated fixtures','Evidence classification','Actual Welcome screenshots',
        'Home empty/populated','All Spaces','Chat code/tool result','Monaco/output','Actual transitions','Fixture labels',
        'One packaging path','No Vite/CDN/Internet production dependency','Validate assets','No publishing/signing purchase/autoupdate',
        'Default switch only after parity/approval','No v3.5.0 filler tag','Preserve tags','Accurate checkpoint docs',
        'M1 actual application launch','M1 screenshots','M1 interaction recording where supported','M1 Python streaming',
        'M1 safe save','M1 real tests/output','M1 measured performance',
    }
    live={
        'M1 actual application launch','M1 screenshots','M1 interaction recording where supported','M1 Python streaming',
        'M1 safe save','M1 real tests/output','M1 measured performance','Keyboard entry','Home never reopens Welcome',
        'One primary BrowserWindow','Responsive grid','Renderer reload','Draft persistence','Streaming','Monaco conflicts',
        'Conflict detection','Unsaved buffers survive agent disk change','Diff review','Expected hashes','Run/output',
        'State retention','Retain models/view state','Typecheck','Lint','E2E','Electron integration','IPC rejection',
        'Actual Welcome screenshots','Home empty/populated','Monaco/output','Actual transitions','Light tokens','Reduced motion',
    }
    for row in rows:
        if row['id'].startswith('C'):
            row['status']='retained scope; Electron implementation pending'
            row['evidence']='Original obligation retained from 3.5; current domain/action status in PARITY.md'
            row['limitation']='Not accepted by a page opening. Native scope remains M3; final parity/security/import/backup scope remains M4.'
            section=int(row['source'].split('section ')[1].split()[0])
            if section in {24,25,26,27,28,29,30,31,32,33,34,35,36,37,49,50,51,52}:
                row['milestone']='M3'
                row['implementation']='Existing Python services where compatible; native domain implementation pending'
            else:
                row['milestone']='M2' if section in {19,20,21,22,23,48,53} else 'M4'
            if any(term in row['description'] for term in ('QQuickWidget','QML','QApplication','QMainWindow','PySide6')):
                row['status']='Qt fallback obligation; final presentation superseded'
                row['limitation']='3.5.1 sections 4-6 explicitly replace the final Qt presentation. Retain current Qt fallback until equivalent Electron action parity.'
                row['implementation']='olive/ui_qt (temporary fallback); desktop (replacement)'
            if 'v3.5.0' in row['description']:
                row['status']='version instruction explicitly superseded'
                row['limitation']='3.5.1 section 35 explicitly forbids creating v3.5.0 as a filler release; preserve prior tags.'
            continue
        description=row['description']
        row.update(implemented=False,unit_tested=False,integration_tested=False,live_tested=False,
                   visually_reviewed=False,user_approved=False,status='not implemented',evidence='Not tested')
        if description in implemented:
            row['implemented']=True
            row['status']='implemented/audited at M1; user approval pending'
            row['implementation']='desktop/src; desktop/electron; olive/bridge; olive/runtime; existing policy-bearing services (see ARCHITECTURE.md)'
            row['evidence']='M1_REVIEW.md and ACCEPTANCE.md; source audit. Individual live flags only where demonstrated.'
            row['limitation']='M1 prototype evidence does not establish full feature parity or final release acceptance.'
        if description in live:
            row['integration_tested']=True;row['live_tested']=True
            row['evidence']='desktop/tests/e2e; .experience-351/electron actual local screenshots/recording/results'
        if description in {'Typecheck','Lint'}:
            row['live_tested']=False;row['integration_tested']=False
            row['evidence']='npm run typecheck / npm run lint; static validation, not live acceptance'
        if description in {'Approval binding','Deduplication','Bounded frames','Malformed input rejection','Explicit method allowlist','Prevent simultaneous profile writers'}:
            row['unit_tested']=True;row['evidence']='tests/test_electron_bridge.py; desktop/tests/contracts.test.ts'
        if description in {'No cold startup claim','Final user approval','M1 user approval','Stop for explicit M1 user approval'}:
            row['status']='awaiting explicit user approval'
        if 'where supported' in description or 'where available' in description or 'conditional' in description:
            row['classification']='conditional'
            row['limitation']='Conditional only as stated in the master brief; report actual environment evidence.'
        row['user_approved']=False
    path.write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    counts=Counter(r['status'] for r in rows)
    (DIRECTORY/'COUNTS.json').write_text(json.dumps(dict(counts),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(counts)))


if __name__=='__main__':main()
