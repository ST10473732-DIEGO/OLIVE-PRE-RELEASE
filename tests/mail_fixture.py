"""Independent aiosmtpd loopback sink: never relays or opens outgoing sockets."""
from datetime import datetime,timedelta,timezone
import ipaddress
from pathlib import Path
import ssl
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult,LoginPassword
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def certificate(directory,hostname_mismatch=False):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'OLIVE isolated loopback fixture')])
    instant=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(instant-timedelta(minutes=1)).not_valid_after(instant+timedelta(days=1))
          .add_extension(x509.SubjectAlternativeName([x509.DNSName('wrong.invalid')] if hostname_mismatch else [x509.IPAddress(ipaddress.ip_address('127.0.0.1')),x509.DNSName('localhost')]),critical=False)
          .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).sign(key,hashes.SHA256()))
    pem=cert.public_bytes(serialization.Encoding.PEM);(directory/'certificate.pem').write_bytes(pem)
    (directory/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(directory/'certificate.pem',directory/'key.pem')
    return pem.decode(),context


class EphemeralController(Controller):
    def _trigger_server(self):
        self.port=self.server.sockets[0].getsockname()[1]
        return super()._trigger_server()


class Sink:
    def __init__(self,directory,*,reject=(),lose_final_reply=False,starttls=False,hostname_mismatch=False,on_record=None):
        self.records=[];self.reject=set(reject);self.lose_final_reply=lose_final_reply
        self.on_record=on_record
        self.pem,context=certificate(directory,hostname_mismatch)
        def authenticate(server,session,envelope,mechanism,data):
            valid=isinstance(data,LoginPassword) and data.login==b'fixture' and data.password==b'fixture-secret'
            return AuthResult(success=valid,handled=False,auth_data='fixture' if valid else None)
        security={'tls_context':context,'require_starttls':True} if starttls else {'ssl_context':context}
        self.controller=EphemeralController(self,hostname='127.0.0.1',port=0,authenticator=authenticate,auth_required=True,
                                           # This aiosmtpd flag describes its STARTTLS
                                           # state. Implicit TLS is enforced by the
                                           # listener's SSLContext before SMTP exists.
                                           auth_require_tls=starttls,enable_SMTPUTF8=True,data_size_limit=20_000_000,**security)
        self.mode='starttls' if starttls else 'tls'

    def __enter__(self):self.controller.start();return self
    def __exit__(self,*args):self.controller.stop()

    @property
    def connection(self):return {'id':'fixture','revision':1,'enabled':True,'name':'Loopback sink','username':'fixture','sender':'sender@example.invalid',
        'smtp':{'host':'127.0.0.1','port':self.controller.port,'tls':self.mode},'imap':None,'ca_pem':self.pem}

    async def handle_RCPT(self,server,session,envelope,address,rcpt_options):
        if address in self.reject:return '550 Fixture recipient rejected'
        # .invalid recipients only, and DATA is retained locally without relay.
        if not address.endswith('@example.invalid'):return '550 Fixture permits example.invalid only'
        envelope.rcpt_tos.append(address);return '250 Recipient accepted by local sink'

    async def handle_DATA(self,server,session,envelope):
        self.records.append({'sender':envelope.mail_from,'recipients':list(envelope.rcpt_tos),'bytes':bytes(envelope.original_content)})
        if self.on_record:self.on_record(self.records[-1])
        if self.lose_final_reply:server.transport.close()
        return '250 Accepted by loopback sink; no relay'
