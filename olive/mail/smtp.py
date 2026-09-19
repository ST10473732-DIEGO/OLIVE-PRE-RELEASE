"""Certificate-validated SMTP submission with explicit irreversible boundary.

No debug logging, plaintext mode, retries or background outbox worker.
"""
import smtplib
import socket
import ssl
from .connections import tls_context


class Cancelled(Exception):
    pass


def check(cancel,guard):
    if cancel.is_set():raise Cancelled('Cancelled before submission')
    guard()


class SMTPSubmissionTransport:
    def connect(self,connection,password):
        endpoint=connection.get('smtp')
        if not endpoint:raise ValueError('SMTP submission is not configured')
        context=tls_context(connection)
        client=None
        try:
            if endpoint['tls']=='tls':
                client=smtplib.SMTP_SSL(endpoint['host'],endpoint['port'],timeout=10,context=context,local_hostname='olive.local')
            else:
                client=smtplib.SMTP(endpoint['host'],endpoint['port'],timeout=10,local_hostname='olive.local')
                client.ehlo();client.starttls(context=context)
            client.ehlo()
            if connection.get('auth_type')=='google_oauth':
                client.auth('XOAUTH2',lambda challenge=None: f"user={connection['username']}\x01auth=Bearer {password}\x01\x01" if challenge is None else '')
            elif connection['username']:client.login(connection['username'],password)
            return client
        except BaseException:
            if client:client.close()
            raise

    def test(self,connection,password):
        client=self.connect(connection,password)
        try:
            code,_=client.noop()
            return {'status':'completed' if code==250 else 'failed','capabilities':list(client.esmtp_features),'sent_message':False}
        finally:client.close()

    def submit(self,connection,password,raw,envelope,cancel,guard,before_data):
        client=None;possibly_submitted=False;accepted=[];rejected={}
        try:
            check(cancel,guard)
            client=self.connect(connection,password)
            check(cancel,guard)
            options=[]
            if envelope['smtp_utf8']:
                if not client.has_extn('smtputf8'):raise ValueError('Server does not support SMTPUTF8 for these addresses')
                options=['SMTPUTF8','BODY=8BITMIME']
            declared=client.esmtp_features.get('size','').strip()
            if declared.isdigit() and len(raw)>int(declared):raise ValueError('Message exceeds the server SIZE limit')
            if client.has_extn('size'):options.append('SIZE='+str(len(raw)))
            code,_=client.mail(envelope['sender'],options)
            if code!=250:return {'state':'failed','category':'sender_rejected','accepted':[],'rejected':{}}
            for recipient in envelope['recipients']:
                check(cancel,guard)
                code,_=client.rcpt(recipient)
                if code in (250,251):accepted.append(recipient)
                else:rejected[recipient]={'code':code,'reason':'Recipient rejected by submission server'}
            if not accepted:return {'state':'failed','category':'all_recipients_rejected','accepted':[],'rejected':rejected}
            check(cancel,guard)
            # Persist uncertainty BEFORE asking the server to accept message bytes.
            # An abrupt crash after this transaction cannot reactivate the send.
            before_data(accepted,rejected)
            check(cancel,guard)
            possibly_submitted=True
            code,_=client.data(raw)
            if code!=250:
                return {'state':'failed','category':'data_rejected','accepted':[],'rejected':rejected}
            return {'state':'partially_accepted' if rejected else 'accepted','category':'submission_server_acceptance',
                    'accepted':accepted,'rejected':rejected}
        except Cancelled:
            return {'state':'outcome_uncertain' if possibly_submitted else 'cancelled','category':'cancelled',
                    'accepted':[],'rejected':rejected}
        except smtplib.SMTPDataError as error:
            return {'state':'failed','category':'data_rejected','code':error.smtp_code,'accepted':[],'rejected':rejected}
        except Exception as error:
            # Transport errors may contain arbitrary server text or recipient
            # data. Persist a safe category, never AUTH bytes/message bodies.
            category=('certificate_validation' if isinstance(error,ssl.SSLCertVerificationError) else
                      'authentication' if isinstance(error,smtplib.SMTPAuthenticationError) else
                      'timeout' if isinstance(error,(TimeoutError,socket.timeout)) else
                      'unsupported_operation' if isinstance(error,ValueError) else type(error).__name__)
            return {'state':'outcome_uncertain' if possibly_submitted else 'failed','category':category,
                    'accepted':[],'rejected':rejected}
        finally:
            if client:client.close()
