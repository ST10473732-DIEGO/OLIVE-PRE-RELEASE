"""Bounded standard-library MIME interchange. HTML remains untrusted content."""
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, make_msgid, format_datetime, parsedate_to_datetime
from datetime import datetime, timezone
import hashlib
import re
import unicodedata
import inspect

_STRICT_ADDRESSES = 'strict' in inspect.signature(getaddresses).parameters

MAX_BYTES = 20_000_000
MAX_TEXT = 160_000


def text(value, limit=1000, *, header=False):
    if not isinstance(value,str) or len(value)>limit or '\0' in value:
        raise ValueError('Invalid or oversized Mail text')
    if header and any(c in value for c in '\r\n'):
        raise ValueError('Mail header contains a newline')
    return value


def addresses(value, *, required=False):
    if not isinstance(value,list) or len(value)>100:
        raise ValueError('Use a bounded recipient list')
    result=[]
    for item in value:
        text(item,320,header=True)
        parsed=getaddresses([item],**({'strict':True} if _STRICT_ADDRESSES else {}))
        if len(parsed)!=1 or not parsed[0][1] or '@' not in parsed[0][1]:
            raise ValueError('Use a complete email address, not only a display name')
        address=parsed[0][1]
        if re.search(r'[\s<>\x00-\x1f\x7f]',address) or address.count('@')!=1:
            raise ValueError('Invalid email address')
        local,domain=address.rsplit('@',1)
        if not local or not domain:raise ValueError('Use both local and domain parts of the email address')
        # Preserve local-part case and international content; do not conflate identities.
        if address not in result:result.append(address)
    if required and not result:raise ValueError('Specify at least one recipient')
    return result


def filename(value):
    value=unicodedata.normalize('NFC',str(value or 'attachment'))
    value=re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]','_',value).strip(' .')[:160] or 'attachment'
    if value.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        value='_'+value
    return value


def parse(raw):
    if not isinstance(raw,bytes) or not raw or len(raw)>MAX_BYTES:
        raise ValueError('EML must contain between 1 byte and 20 MB')
    message=BytesParser(policy=policy.default).parsebytes(raw)
    warnings=[]; attachments=[]; plain=[]; html=[]; parts=0; extracted=0
    def walk(part,depth):
        nonlocal parts,extracted
        parts+=1
        if depth>12 or parts>150:raise ValueError('MIME nesting/part limit exceeded')
        warnings.extend(type(d).__name__ for d in part.defects)
        if part.is_multipart():
            for child in part.iter_parts():walk(child,depth+1)
            return
        data=part.get_payload(decode=True) or b''
        extracted+=len(data)
        if extracted>MAX_BYTES:raise ValueError('Decoded MIME content exceeds 20 MB')
        content_type=part.get_content_type()
        is_file=part.get_content_disposition()=='attachment' or part.get_filename() is not None or content_type not in {'text/plain','text/html'}
        if is_file:
            attachments.append({'name':filename(part.get_filename()),'type':content_type,'size':len(data),
                                'hash':hashlib.sha256(data).hexdigest(),'bytes':data,
                                'cid':str(part.get('Content-ID','')).strip('<>')[:300],'untrusted':True})
        else:
            charset=part.get_content_charset() or 'utf-8'
            try:decoded=data.decode(charset,errors='replace')
            except LookupError:
                decoded=data.decode('utf-8',errors='replace');warnings.append('Unknown character encoding; UTF-8 fallback')
            (html if content_type=='text/html' else plain).append(decoded)
    walk(message,0)
    body='\n'.join(plain); markup='\n'.join(html)
    if not body and markup:
        from html.parser import HTMLParser
        class PlainHTML(HTMLParser):
            def __init__(self):super().__init__(convert_charrefs=True);self.output=[];self.hidden=0
            def handle_starttag(self,tag,attrs):
                if tag in {'script','style','template','head'}:self.hidden+=1
                if tag in {'p','div','br','li','tr'} and not self.hidden:self.output.append('\n')
            def handle_endtag(self,tag):
                if tag in {'script','style','template','head'}:self.hidden=max(0,self.hidden-1)
            def handle_data(self,data):
                if not self.hidden:self.output.append(data)
        parser=PlainHTML();parser.feed(markup[:MAX_TEXT]);body=''.join(parser.output).strip()
        warnings.append('Plain-text display derived from HTML; original source retained')
    if len(body)>MAX_TEXT or len(markup)>MAX_TEXT:
        warnings.append('Display text truncated; original EML retained')
    def header(name):return str(message.get(name,''))[:4000]
    def recipients(name):
        try:return [address for _,address in getaddresses(message.get_all(name,[]),**({'strict':True} if _STRICT_ADDRESSES else {})) if address][:100]
        except ValueError:
            warnings.append('Malformed '+name);return []
    sent_at=None
    try:
        instant=parsedate_to_datetime(header('Date'))
        if instant.tzinfo:sent_at=instant.astimezone(timezone.utc).isoformat()
    except (TypeError,ValueError,OverflowError):pass
    return {'subject':header('Subject'),'from':header('From'),'to':recipients('To'),'cc':recipients('Cc'),
            # Received BCC is retained only in raw evidence, never expanded into Reply All.
            'bcc':[],'reply_to':recipients('Reply-To'),'message_id':header('Message-ID'),
            'references':header('References'),'in_reply_to':header('In-Reply-To'),'date':header('Date'),'sent_at':sent_at,
            'text':body[:MAX_TEXT],'html':markup[:MAX_TEXT], 'attachments':attachments,
            'warnings':list(dict.fromkeys(warnings))[:30]}


def compose(draft, attachments, *, sender, message_id=None):
    sender=addresses([sender],required=True)[0]
    recipients={key:addresses(draft.get(key,[])) for key in ('to','cc','bcc')}
    envelope=list(dict.fromkeys(recipients['to']+recipients['cc']+recipients['bcc']))
    if not envelope:raise ValueError('Specify at least one recipient')
    international=any(not a.isascii() for a in [sender,*envelope])
    message=EmailMessage(policy=policy.SMTPUTF8 if international else policy.SMTP)
    message['From']=sender
    for key,header in [('to','To'),('cc','Cc')]:
        if recipients[key]:message[header]=', '.join(recipients[key])
    message['Subject']=text(draft.get('subject',''),1000,header=True)
    message['Message-ID']=message_id or make_msgid(domain='olive.local')
    message['Date']=format_datetime(datetime.now(timezone.utc))
    for key,header in [('references','References'),('in_reply_to','In-Reply-To')]:
        if draft.get(key):message[header]=text(draft[key],4000,header=True)
    message.set_content(text(draft.get('text',''),MAX_TEXT))
    for attachment,data in attachments:
        if hashlib.sha256(data).hexdigest()!=attachment['hash']:raise ValueError('Attachment snapshot changed')
        mime=attachment['type'].split('/',1)
        if len(mime)!=2 or not all(re.fullmatch('[A-Za-z0-9.+-]+',p) for p in mime):mime=['application','octet-stream']
        message.add_attachment(data,maintype=mime[0],subtype=mime[1],filename=filename(attachment['name']))
    raw=message.as_bytes()
    if len(raw)>MAX_BYTES:raise ValueError('Prepared message exceeds 20 MB')
    return raw, {'sender':sender,'recipients':envelope,'smtp_utf8':international,'message_id':str(message['Message-ID'])}
