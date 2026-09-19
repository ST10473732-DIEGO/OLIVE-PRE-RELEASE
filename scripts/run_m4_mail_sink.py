"""Disposable independent SMTP sink for delegated Electron fixture acceptance.

Only loopback sockets; only example.invalid recipients; no relay, accounts or
credential discovery. The trusted harness owns its temporary directory/process.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.mail_fixture import Sink


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True)
    parser.add_argument('--imap',action='store_true',help='Use a scripted IMAP TLS peer instead of the independent SMTP sink')
    parser.add_argument('--reject-address',action='append',default=[])
    parser.add_argument('--lose-final-reply',action='store_true')
    args=parser.parse_args();directory=Path(args.directory).resolve()
    if any(not a.endswith('@example.invalid') for a in args.reject_address):raise ValueError('Only synthetic example.invalid recipients are permitted')
    if not directory.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not directory.name.startswith('olive-m4-sink-'):
        raise ValueError('Use a newly created olive-m4-sink-* directory under the system temporary directory')
    directory.mkdir(parents=True,exist_ok=True)
    if any(directory.iterdir()):raise ValueError('Fixture directory must be empty')
    count=0
    def record(value):
        nonlocal count
        count+=1
        (directory/f'message-{count}.eml').write_bytes(value['bytes'])
        (directory/f'envelope-{count}.json').write_text(json.dumps({'sender':value['sender'],'recipients':value['recipients'],'bytes':len(value['bytes'])}),encoding='utf-8')
    from tests.mail_imap_fixture import IMAPFixture
    fixture=IMAPFixture(directory/'tls') if args.imap else Sink(directory/'tls',starttls=True,on_record=record,reject=args.reject_address,lose_final_reply=args.lose_final_reply)
    with fixture as sink:
        configuration=sink.config if args.imap else sink.connection
        classification='scripted loopback IMAP TLS peer; not independent-server interoperability' if args.imap else 'independent aiosmtpd loopback STARTTLS sink; no relay'
        (directory/'ready.json').write_text(json.dumps({'pid':os.getpid(),'parent_pid':os.getppid(),'script':str(Path(__file__).resolve()),'connection':configuration,'classification':classification}),encoding='utf-8')
        deadline=time.monotonic()+600
        while time.monotonic()<deadline and not (directory/'stop').exists():time.sleep(.1)
        if args.imap:
            (directory/'imap-observations.json').write_text(json.dumps({'commands':sink.commands,'body_fetches':sink.body_fetches,'header_fetches':sink.header_fetches,'flags':{str(k):[f.decode() for f in v] for k,v in sink.flags.items()}}),encoding='utf-8')
    (directory/'stopped.json').write_text(json.dumps({'pid':os.getpid(),'stopped':True,'received_count':count}),encoding='utf-8')


if __name__=='__main__':main()
