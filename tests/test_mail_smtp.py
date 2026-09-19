"""Production SMTP adapter against an independent aiosmtpd TLS loopback sink."""
import tempfile
import threading
import unittest
from olive.mail.mime import compose,parse
from olive.mail.smtp import SMTPSubmissionTransport
from tests.mail_fixture import Sink


class SMTPTests(unittest.TestCase):
    def submit(self,sink,password='fixture-secret',cancel=None):
        raw,envelope=compose({'to':['alex@example.invalid'],'bcc':['hidden@example.invalid'],'subject':'Unicode café','text':'Synthetic local body'},[],sender='sender@example.invalid')
        boundaries=[]
        result=SMTPSubmissionTransport().submit(sink.connection,password,raw,envelope,cancel or threading.Event(),lambda:None,lambda a,r:boundaries.append((a,r)))
        return result,boundaries

    def test_real_tls_and_starttls_exchange_bcc_and_no_send_during_test(self):
        for starttls in (False,True):
            with self.subTest(starttls=starttls),tempfile.TemporaryDirectory() as root,Sink(root,starttls=starttls) as sink:
                test=SMTPSubmissionTransport().test(sink.connection,'fixture-secret')
                self.assertEqual(test['status'],'completed');self.assertEqual(sink.records,[])
                result,boundaries=self.submit(sink)
                self.assertEqual(result['state'],'accepted');self.assertEqual(len(boundaries),1)
                self.assertEqual(len(sink.records),1);received=sink.records[0]
                self.assertEqual(received['recipients'],['alex@example.invalid','hidden@example.invalid'])
                self.assertNotIn(b'\r\nBcc:',received['bytes']);self.assertEqual(parse(received['bytes'])['subject'],'Unicode café')

    def test_partial_all_rejected_and_unknown_final_response(self):
        cases=[({'reject':['hidden@example.invalid']},'partially_accepted',1),
               ({'reject':['hidden@example.invalid','alex@example.invalid']},'failed',0),
               ({'lose_final_reply':True},'outcome_uncertain',1)]
        for options,state,count in cases:
            with self.subTest(state=state),tempfile.TemporaryDirectory() as root,Sink(root,**options) as sink:
                result,_=self.submit(sink);self.assertEqual(result['state'],state);self.assertEqual(len(sink.records),count)
                if state=='partially_accepted':self.assertEqual(result['accepted'],['alex@example.invalid'])

    def test_authentication_certificate_and_pre_submission_cancellation(self):
        with tempfile.TemporaryDirectory() as root,Sink(root) as sink:
            result,_=self.submit(sink,password='wrong-fixture-secret');self.assertEqual(result['category'],'authentication')
            event=threading.Event();event.set();result,_=self.submit(sink,cancel=event);self.assertEqual(result['state'],'cancelled')
            raw,envelope=compose({'to':['alex@example.invalid'],'text':'Local'},[],sender='sender@example.invalid')
            config={**sink.connection,'ca_pem':''}
            result=SMTPSubmissionTransport().submit(config,'fixture-secret',raw,envelope,threading.Event(),lambda:None,lambda a,r:None)
            self.assertEqual(result['category'],'certificate_validation');self.assertEqual(sink.records,[])
        with tempfile.TemporaryDirectory() as root,Sink(root,hostname_mismatch=True) as sink:
            result,_=self.submit(sink)
            self.assertEqual(result['category'],'certificate_validation');self.assertEqual(sink.records,[])
