"""Bounded UID-based IMAP adapter. No sequence-number identities or EXPUNGE."""
import imaplib
import re
from .connections import tls_context
from .smtp import check
from .mime import MAX_BYTES, text


def mailbox(value):
    text(value,300,header=True)
    if not value or any(ord(c)<32 for c in value):raise ValueError('Invalid mailbox name')
    # Python's IMAP client does not supply modified UTF-7 encoding. Preserve the
    # advertised wire name; do not silently invent an encoding or rename it.
    if not value.isascii():raise ValueError('Use the server-advertised encoded mailbox name')
    return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'


def require(response):
    status,data=response
    if status!='OK':raise RuntimeError('IMAP command was rejected')
    return data


def capabilities(client):
    return {c.decode('ascii','replace').upper() if isinstance(c,bytes) else str(c).upper() for c in getattr(client,'capabilities',())}


class MailboxSyncTransport:
    def connect(self,connection,password):
        endpoint=connection.get('imap')
        if not endpoint:raise ValueError('IMAP is not configured')
        client=None
        try:
            context=tls_context(connection)
            if endpoint['tls']=='tls':client=imaplib.IMAP4_SSL(endpoint['host'],endpoint['port'],ssl_context=context,timeout=10)
            else:
                client=imaplib.IMAP4(endpoint['host'],endpoint['port'],timeout=10)
                require(client.starttls(ssl_context=context))
            original_read=client.read
            def bounded_read(size):
                if size>MAX_BYTES:raise ValueError('IMAP literal exceeds 20 MB')
                return original_read(size)
            client.read=bounded_read
            if connection.get('auth_type')=='google_oauth':
                require(client.authenticate('XOAUTH2',lambda _:f"user={connection['username']}\x01auth=Bearer {password}\x01\x01".encode()))
            elif connection['username']:require(client.login(connection['username'],password))
            # Authentication can reveal additional capabilities (including Gmail IDs).
            advertised=require(client.capability())
            if not advertised or not isinstance(advertised[-1],bytes) or len(advertised[-1])>10000:raise ValueError('Invalid authenticated IMAP capabilities')
            client.capabilities=tuple(advertised[-1].decode('ascii').upper().split())
            return client
        except BaseException:
            if client:self.close(client)
            raise

    @staticmethod
    def close(client):
        # LOGOUT closes the selected mailbox without CLOSE's expunge side effect.
        try:client.logout()
        except (OSError,imaplib.IMAP4.error):
            try:client.shutdown()
            except OSError:pass

    def test(self,connection,password):
        client=self.connect(connection,password)
        try:
            require(client.noop())
            return {'status':'completed','capabilities':sorted(capabilities(client)),'sent_message':False}
        finally:self.close(client)

    def folders(self,client):
        data=require(client.list('""','"*"'))
        result=[]
        for line in data:
            if line is None:continue
            if not isinstance(line,bytes) or len(line)>4096:raise ValueError('Unsupported oversized mailbox listing')
            match=re.fullmatch(rb'\(([^)]*)\) (NIL|"(?:[^"\\]|\\.)*") (.+)',line)
            if not match:raise ValueError('Unsupported mailbox LIST response; no names guessed')
            flags=match[1].decode('ascii','replace').split();name=match[3].decode('ascii')
            if name.startswith('"') and name.endswith('"'):name=re.sub(r'\\(.)',r'\1',name[1:-1])
            if '\\Noselect' not in flags:result.append({'name':name,'flags':flags})
            if len(result)>200:raise ValueError('Mailbox listing exceeds 200 folders')
        return result

    def select(self,client,name,readonly=True):
        require(client.select(mailbox(name),readonly=readonly))
        _,data=client.response('UIDVALIDITY')
        if not data or not data[0] or not data[0].isdigit():raise ValueError('Server did not return a valid UIDVALIDITY')
        return int(data[0])

    def uids(self,client,after=0,query=''):
        if type(after) is not int or after<0:raise ValueError('Invalid UID cursor')
        if query:
            text(query,300,header=True)
            if not query.isascii():raise ValueError('This server search supports ASCII terms; use local Unicode search for cached content')
            data=require(client.uid('SEARCH',None,'TEXT',mailbox(query)))
        else:data=require(client.uid('SEARCH',None,'UID',str(max(1,after+1))+':*'))
        if not data or not isinstance(data[0],bytes) or len(data[0])>1_000_000:raise ValueError('UID search response exceeds its bound')
        values=data[0].split()
        if any(not v.isdigit() for v in values):raise ValueError('Malformed UID search response')
        return sorted({int(v) for v in values if int(v)>after})

    def fetch(self,client,uid,body=False):
        if type(uid) is not int or uid<1:raise ValueError('Invalid message UID')
        # First obtain size; literal reads are separately capped before allocation.
        gmail='X-GM-EXT-1' in capabilities(client)
        metadata=require(client.uid('FETCH',str(uid),'(UID FLAGS RFC822.SIZE'+(' X-GM-MSGID' if gmail else '')+')'))
        headers=b' '.join(part for part in metadata if isinstance(part,bytes))
        actual_metadata=re.search(rb'UID (\d+)',headers)
        if not actual_metadata or int(actual_metadata[1])!=uid:raise ValueError('Server returned metadata for a different UID')
        match=re.search(rb'RFC822.SIZE (\d+)',headers)
        if not match:raise LookupError('Message disappeared or size metadata is missing')
        size=int(match[1])
        if size>MAX_BYTES:raise ValueError('Remote message exceeds 20 MB; body not fetched')
        field='BODY.PEEK[]' if body else 'BODY.PEEK[HEADER]'
        data=require(client.uid('FETCH',str(uid),'(UID FLAGS '+field+')'))
        literals=[part for part in data if isinstance(part,tuple)]
        if len(literals)!=1:raise ValueError('Expected one exact UID body response')
        description,raw=literals[0]
        actual=re.search(rb'UID (\d+)',description)
        if not actual or int(actual[1])!=uid:raise ValueError('Server returned a different message UID')
        if len(raw)>MAX_BYTES:raise ValueError('Remote body exceeds the supported size')
        flags=imaplib.ParseFlags(headers)
        result={'raw':raw,'size':size,'read':b'\\Seen' in flags,'starred':b'\\Flagged' in flags}
        if gmail:
            identity=re.search(rb'X-GM-MSGID (\d{1,20})(?:\s|\))',headers)
            if not identity:raise ValueError('Gmail message identity is missing; no label duplicate was created')
            result['provider_message_id']=identity[1].decode()
        return result

    def metadata(self,client,uid):
        if type(uid) is not int or uid<1:raise ValueError('Invalid UID')
        data=require(client.uid('FETCH',str(uid),'(UID FLAGS RFC822.SIZE)'))
        headers=b' '.join(p for p in data if isinstance(p,bytes))
        actual=re.search(rb'UID (\d+)',headers)
        if not actual or int(actual[1])!=uid:raise LookupError('Exact UID metadata is unavailable')
        flags=imaplib.ParseFlags(headers)
        return {'read':b'\\Seen' in flags,'starred':b'\\Flagged' in flags}

    def flags(self,client,uid,*,read=None,starred=None):
        if type(uid) is not int or uid<1:raise ValueError('Invalid UID')
        for value,flag in [(read,'\\Seen'),(starred,'\\Flagged')]:
            if value is not None:
                if type(value) is not bool:raise ValueError('Invalid flag value')
                require(client.uid('STORE',str(uid),'+FLAGS.SILENT' if value else '-FLAGS.SILENT','('+flag+')'))

    def move(self,client,uid,destination):
        if type(uid) is not int or uid<1:raise ValueError('Invalid UID')
        if 'MOVE' not in capabilities(client):raise ValueError('Server does not support safe UID MOVE; local folders remain available')
        require(client.uid('MOVE',str(uid),mailbox(destination)))
        _,data=client.response('COPYUID')
        if data and isinstance(data[0],bytes):
            match=re.fullmatch(rb'(\d+) (\d+) (\d+)',data[0])
            if match and int(match[2])==uid:return {'mailbox':destination,'uidvalidity':int(match[1]),'uid':int(match[3])}
        return None

    def folder_action(self,client,action,name,new_name=''):
        if action=='create':return require(client.create(mailbox(name)))
        if action=='rename':return require(client.rename(mailbox(name),mailbox(new_name)))
        # DELETE/EXPUNGE deliberately absent; cannot prove it affects only one
        # explicitly approved message on all advertised server implementations.
        raise ValueError('Unsupported mailbox operation')

    def append_sent(self,client,name,raw):
        if len(raw)>MAX_BYTES:raise ValueError('Sent copy exceeds limit')
        require(client.append(mailbox(name),'(\\Seen)',None,raw))
