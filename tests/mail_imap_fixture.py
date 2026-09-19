"""Scripted loopback IMAP protocol fixture, NOT independent-server proof."""
import re
import base64
import socketserver
import threading
from .mail_fixture import certificate


class IMAPFixture:
    def __init__(self,directory):
        self.pem,context=certificate(directory);self.validity=101;self.messages={1:b'From: fixture@example.invalid\r\nTo: sender@example.invalid\r\nSubject: Cached fixture\r\nMessage-ID: <one@example.invalid>\r\n\r\nBody fetched only on demand.\r\n'}
        self.flags={};self.body_fetches=0;self.header_fetches=0;self.fail_uid=None;self.commands=[];self.mailboxes=['INBOX'];self.appended=[];self.fail_append=False
        self.mailbox_messages={};self.folder_flags={};self.gmail_ids={};self.auth_methods=[]
        owner=self
        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address=False;daemon_threads=True
            def get_request(inner):
                sock,address=super().get_request()
                try:return context.wrap_socket(sock,server_side=True),address
                except BaseException:sock.close();raise
        class Handler(socketserver.StreamRequestHandler):
            def handle(inner):
                inner.connection.settimeout(10)
                selected='INBOX'
                def line(value):inner.wfile.write(value+b'\r\n');inner.wfile.flush()
                line(b'* OK OLIVE scripted fixture')
                for _ in range(1000):
                    request=inner.rfile.readline(4096)
                    if not request:return
                    values=request.rstrip(b'\r\n').split(b' ',2)
                    if len(values)<2:return
                    tag,command=values[:2];args=values[2] if len(values)>2 else b''
                    # Commands retain operation names only, never AUTH arguments.
                    owner.commands.append(command.decode())
                    if command==b'CAPABILITY':line(b'* CAPABILITY IMAP4rev1 AUTH=PLAIN AUTH=XOAUTH2 UIDPLUS MOVE'+(b' X-GM-EXT-1' if owner.gmail_ids else b''))
                    elif command==b'AUTHENTICATE':
                        if args!=b'XOAUTH2':line(tag+b' NO unsupported auth');continue
                        line(b'+ ');payload=base64.b64decode(inner.rfile.readline(32000).strip())
                        if payload!=b'user=fixture\x01auth=Bearer synthetic-access\x01\x01':line(tag+b' NO rejected auth');continue
                        owner.auth_methods.append('XOAUTH2')
                    elif command==b'LOGIN':
                        if b'fixture' not in args:line(tag+b' NO authentication failed');continue
                    elif command in {b'SELECT',b'EXAMINE'}:
                        selected=args.strip(b'"').decode()
                        line(b'* '+str(len(owner.mailbox_messages.get(selected,owner.messages))).encode()+b' EXISTS');line(b'* FLAGS (\\Seen \\Flagged)')
                        line(b'* OK [UIDVALIDITY '+str(owner.validity).encode()+b'] valid')
                    elif command==b'LIST':
                        for folder in owner.mailboxes:line(b'* LIST ('+b' '.join([b'\\HasNoChildren',*[f.encode() for f in owner.folder_flags.get(folder,[])]] )+b') "/" "'+folder.encode()+b'"')
                    elif command==b'CREATE':owner.mailboxes.append(args.strip(b'"').decode())
                    elif command==b'RENAME':
                        names=re.findall(rb'"([^"]*)"',args)
                        if len(names)!=2:line(tag+b' BAD malformed rename');continue
                        old,new=[n.decode() for n in names];owner.mailboxes=[new if f==old else f for f in owner.mailboxes]
                    elif command==b'APPEND':
                        match=re.search(rb'\{(\d+)\}$',args)
                        if not match or int(match[1])>20_000_000:line(tag+b' BAD oversized append');continue
                        line(b'+ ready for literal');raw=inner.rfile.read(int(match[1]));inner.rfile.readline(2)
                        owner.appended.append(raw)
                        if owner.fail_append:inner.connection.close();return
                    elif command==b'UID':
                        parts=args.split(b' ',2);operation=parts[0]
                        messages=owner.mailbox_messages.get(selected,owner.messages)
                        if operation==b'SEARCH':line(b'* SEARCH '+b' '.join(str(k).encode() for k in sorted(messages)))
                        elif operation==b'FETCH':
                            uid=int(parts[1]);record=messages.get(uid)
                            if uid==owner.fail_uid:line(tag+b' NO fixture batch failure');continue
                            if record is not None:
                                flags=b' '.join(owner.flags.get(uid,[]));prefix=b'* 1 FETCH (UID '+str(uid).encode()+b' FLAGS ('+flags+b') '
                                if b'BODY.PEEK' in parts[2]:
                                    header=b'HEADER' in parts[2];raw=record.split(b'\r\n\r\n')[0]+b'\r\n\r\n' if header else record
                                    if header:owner.header_fetches+=1
                                    else:owner.body_fetches+=1
                                    line(prefix+b'BODY['+(b'HEADER' if header else b'')+b'] {'+str(len(raw)).encode()+b'}')
                                    inner.wfile.write(raw);line(b')')
                                else:line(prefix+b'RFC822.SIZE '+str(len(record)).encode()+(b' X-GM-MSGID '+str(owner.gmail_ids[(selected,uid)]).encode() if b'X-GM-MSGID' in parts[2] else b'')+b')')
                        elif operation==b'STORE':
                            uid=int(parts[1]);flag=re.search(rb'\\(?:Seen|Flagged)',parts[2]).group();flags=set(owner.flags.get(uid,[]))
                            if b'+FLAGS' in parts[2]:flags.add(flag)
                            else:flags.discard(flag)
                            owner.flags[uid]=list(flags)
                        elif operation==b'MOVE':
                            uid=int(parts[1]);destination=parts[2].strip(b'"').decode();target=owner.mailbox_messages.setdefault(destination,{})
                            new_uid=max(target,default=0)+1;target[new_uid]=messages.pop(uid)
                            if (selected,uid) in owner.gmail_ids:owner.gmail_ids[(destination,new_uid)]=owner.gmail_ids[(selected,uid)]
                            line(b'* OK [COPYUID '+str(owner.validity).encode()+b' '+str(uid).encode()+b' '+str(new_uid).encode()+b'] moved')
                        else:line(tag+b' BAD unsupported UID fixture operation');continue
                    elif command==b'LOGOUT':line(b'* BYE fixture closed');line(tag+b' OK logout');return
                    elif command not in {b'NOOP',b'CREATE',b'RENAME'}:line(tag+b' BAD unsupported fixture operation');continue
                    line(tag+b' OK completed')
        self.server=Server(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)

    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):self.server.shutdown();self.server.server_close();self.thread.join(5)
    @property
    def config(self):return {'name':'Scripted IMAP fixture','sender':'sender@example.invalid','username':'fixture','imap':{'host':'127.0.0.1','port':self.server.server_address[1],'tls':'tls'},'ca_pem':self.pem}
