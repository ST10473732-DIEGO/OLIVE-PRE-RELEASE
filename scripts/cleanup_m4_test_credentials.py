"""Remove only this M4 harness's dummy connection credentials after failed runs."""
import argparse,json,sqlite3,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from olive.services.credential_vault import CredentialVault

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--profile',action='append',required=True);args=parser.parse_args()
results=[]
for value in args.profile:
    profile=Path(value).resolve()
    if profile.parent!=Path(tempfile.gettempdir()).resolve() or not profile.name.startswith('olive-m4-smtp-ui-'):raise ValueError('Not an owned M4 SMTP fixture profile')
    db=sqlite3.connect((profile/'mail.sqlite3').as_uri()+'?mode=ro',uri=True)
    try:rows=db.execute("SELECT body FROM records WHERE kind='connection'").fetchall()
    finally:db.close()
    removed=0
    for row in rows:
        connection=json.loads(row[0])
        if connection['name']!='M4 isolated loopback sink' or connection['sender']!='sender@example.invalid' or connection['username']!='fixture' or connection['smtp']['host']!='127.0.0.1' or connection['imap'] is not None:raise ValueError('Fixture identity does not match')
        reference=connection.get('credential_ref')
        if reference:CredentialVault(profile).remove(reference);removed+=1
    results.append({'profile':str(profile),'dummy_credential_references_removed':removed,'secret_retrieval':False})
print(json.dumps(results,indent=2))
