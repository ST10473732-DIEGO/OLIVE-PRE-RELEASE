"""Update only M4's existing obligations; retain historical and release gates."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/releases/3.5.1'


def main():
    rows=json.loads((OUT/'requirements.json').read_text(encoding='utf-8'))
    extras=set('R351-02-09 R351-21-07 R351-26-10 R351-26-11 R351-26-12 R351-26-13 R351-29-15 R351-32-07 R351-32-08 R351-32-14 R351-33-16 C350-03-05 C350-03-06 C350-16-12 C350-24-06 C350-37-13 C350-39-14 C350-39-27 C350-40-07 C350-40-12 C350-41-16 C350-42-04 C350-43-04 C350-43-13 C350-43-19 C350-44-09 C350-48-09 C350-49-20 C350-51-01 C350-51-02 C350-51-03 C350-51-05'.split())
    groups={
      'R351-24-':('olive/mail/local.py, submission.py, connections.py, smtp.py, imap.py, sync.py; desktop/src/features/mail','test_mail_local/policy/smtp/imap/composition; Electron m4-mail-*'),
      'R351-25-':('olive/services/credential_vault.py; olive/mail/controller.py, mime.py, images.py, submission.py; SafeBody.tsx, MailConnections.tsx','test_mail_vault/security/policy/smtp; Electron content/smtp'),
      'C350-30-':('olive/mail/store.py, local.py, language.py; desktop/src/features/mail','test_mail_local/policy; Electron local/content; opt-in language-live'),
      'C350-31-':('olive/mail/connections.py, smtp.py, imap.py, sync.py, submission.py, background.py','test_mail_smtp/imap/security; Electron smtp/imap'),
      'C350-32-':('olive/mail/mime.py, images.py, local.py, composition.py, language.py; SafeBody.tsx','test_mail_local/security/policy/composition; Electron content/language'),
      'C350-33-':('olive/services/credential_vault.py; olive/mail/controller.py, connections.py; MailConnections.tsx; ACCOUNT_SECURITY.md','test_mail_vault/security; Electron smtp'),
    }
    live=set('R351-24-01 R351-24-03 R351-24-04 R351-24-05 R351-24-06 R351-24-07 R351-24-08 R351-24-11 R351-24-12 R351-24-13 R351-24-14 R351-24-15 R351-24-16 R351-24-17 R351-24-19 R351-24-20 R351-24-21 R351-24-23 R351-24-24 R351-24-25 R351-24-26 R351-24-27 R351-25-01 R351-25-05 R351-25-10 R351-25-11 R351-25-14 R351-25-15 R351-25-19 R351-32-07 R351-32-08 C350-31-33 C350-33-22 C350-40-07 C350-41-16 C350-51-03'.split())
    changed=0
    for row in rows:
        group=next((value for prefix,value in groups.items() if row['id'].startswith(prefix)),None)
        if not group and row['id'] not in extras and not (row['id'].startswith('C350-50-') and 15<=int(row['id'][-2:])<=21):continue
        group=group or ('olive/mail; shared interaction router; existing Personal/Knowledge/Projects; Electron Mail','M4_COMPLETION.md A–K; focused Mail/domain/security tests')
        row.setdefault('pre_m4_status',row['status']);row.setdefault('pre_m4_evidence',row['evidence'])
        row.update(implementation=group[0],acceptance=group[1],implemented=True,
          status='M4 implemented; internal acceptance evidence classified in M4_COMPLETION.md',
          evidence=group[1]+'; artifacts/ui-review/M4; M4_COMPLETION.md',
          limitation='No live external account/server certification; IMAP uses a scripted TLS peer. Final release/packaging approval remains separate.',
          unit_tested=True,integration_tested=True,live_tested=row['id'] in live,
          visually_reviewed=row['id'] in live and not row['id'].startswith('C350-33-'),user_approved=False)
        if row['description'].startswith(('No ','Do not ','Document ','Maintain ','Exclude ')) or row['id'] in {'C350-31-35','C350-42-04','C350-43-19'}:
            row['unit_tested']=False
            row['evidence']='Implementation/configuration audit and documented boundaries; '+row['evidence']
        if row['id']=='C350-33-08':row['limitation']='Qt/QML secret presentation is superseded by Electron masked transient entry; there is no Qt Mail UI or model secret getter.'
        if row['id']=='C350-31-33':row['limitation']='Independent aiosmtpd SMTP TLS sink passed. IMAP uses a scripted TLS peer; independent IMAP engine unavailable.'
        changed+=1
    (OUT/'requirements.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'{changed} M4 obligations updated; {len(rows)} total IDs retained')
    # Separate new action table; never overwrite the 125 original M2 mappings.
    import sys
    sys.path.insert(0,str(ROOT))
    from olive.mail.contracts import SPEC,MAIN_ONLY,permissions
    text=['# M4 native Mail action parity','','All routes reach one Python controller and existing permission/confirmation services.','The original 125 M2 mappings in PARITY.md remain unchanged. Evidence classifications','and actual UI versus protocol demonstrations are in M4_COMPLETION.md.','','| Action | Electron / language access | Permission | State / evidence |','| --- | --- | --- | --- |']
    for method in SPEC|MAIN_ONLY:
        access='Settings Connections; direct application consent only' if 'connection' in method or 'credential' in method else 'Mail contextual UI; shared registered capability'
        if method=='mail.credential_store':access='Dedicated masked control; never registered as a model tool'
        if method in MAIN_ONLY and method!='mail.credential_store':access+='; native main-process file/configuration route'
        text.append('| `'+method+'` | '+access+' | '+', '.join('`'+p+'`' for p in permissions(method))+' | Revision/identity validation, Deny preserved; tests/test_mail_*.py and classified M4 demonstrations |')
    text+=['','Local and remote outcomes are distinct. Send/remote changes retain uncertainty;','there is no automatic send replay. Entry-point existence is not claimed as a','live pass for every action. See MAIL_TRANSPORTS.md for supported protocol limits.']
    (OUT/'M4_PARITY.md').write_text('\n'.join(text)+'\n',encoding='utf-8')


if __name__=='__main__':main()
