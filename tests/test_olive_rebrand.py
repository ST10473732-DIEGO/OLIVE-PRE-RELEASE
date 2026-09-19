"""Rebrand compatibility using synthetic profiles; no real data or credentials."""
import json,os,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from datetime import datetime,timezone
from olive.identity import resolve_profile,normalize_environment,APP_NAME

class RebrandTests(unittest.TestCase):
 def test_profile_defaults_legacy_reuse_and_conflicts(self):
  with tempfile.TemporaryDirectory() as d:
   home=Path(d);legacy=home/'.dmdo';current=home/'.olive'
   self.assertEqual(resolve_profile({},home,platform='win32'),current)
   self.assertEqual(resolve_profile({},home,platform='linux'),home/'.local/share/olive')
   legacy.mkdir();(legacy/'settings.json').write_text('{}')
   self.assertEqual(resolve_profile({},home),legacy)
   current.mkdir();self.assertEqual(resolve_profile({},home),legacy)
   (current/'chats.json').write_text('{}')
   with self.assertRaisesRegex(ValueError,'Both OLIVE'):resolve_profile({},home)
   self.assertEqual(resolve_profile({'OLIVE_DATA_DIR':str(legacy)},home),legacy)
   self.assertEqual(resolve_profile({'DMDO_DATA_DIR':str(legacy)},home),legacy)
   self.assertEqual((legacy/'settings.json').read_text(),'{}')
 def test_environment_aliases_and_conflicts_fail_closed(self):
  for key in ('DATA_DIR','PYTHON','ATTACH_DIAGNOSTICS','OLLAMA_HOST','PRESENTATION'):
   self.assertEqual(normalize_environment({'DMDO_'+key:'legacy'})['OLIVE_'+key],'legacy')
   with self.assertRaisesRegex(ValueError,'Conflicting'):normalize_environment({'DMDO_'+key:'legacy','OLIVE_'+key:'other'})
   self.assertEqual(normalize_environment({'DMDO_'+key:'same','OLIVE_'+key:'same'})['OLIVE_'+key],'same')
 def test_fresh_process_alias_class_identity_and_entrypoints(self):
  with tempfile.TemporaryDirectory() as d:
   env={k:v for k,v in os.environ.items() if not k.startswith(('DMDO_','OLIVE_'))};env['OLIVE_DATA_DIR']=d
   code="import olive,dmdo; from olive.personal.service import PersonalService as A; from dmdo.personal.service import PersonalService as B; from dmdo.runtime.profile_lock import ProfileLock as L; from olive.runtime.profile_lock import ProfileLock as C; assert A is B and L is C and olive is dmdo; print(olive.APP_NAME)"
   result=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=20)
   self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'OLIVE')
   for name,key in [('olive.bridge','OLIVE_DATA_DIR'),('dmdo.bridge','DMDO_DATA_DIR')]:
    local={k:v for k,v in env.items() if not k.startswith('OLIVE_')};local[key]=d
    result=subprocess.run([sys.executable,'-m',name],input='',env=local,capture_output=True,text=True,timeout=20)
    self.assertEqual(result.returncode,0,result.stderr)
 def test_legacy_and_current_imports_share_writer_lock(self):
  from dmdo.runtime.profile_lock import ProfileLock as Old
  from olive.runtime.profile_lock import ProfileLock as New
  with tempfile.TemporaryDirectory() as d:
   with Old(d):
    with self.assertRaises(RuntimeError):New(d).acquire()
 def test_legacy_backup_ids_permissions_content_and_reminders(self):
  from olive.personal.service import PersonalService
  from olive.personal.reminders import ReminderScheduler
  from olive.services.backup_service import BackupService
  from olive.storage.chat_repository import ChatRepository
  from olive.storage.project_repository import ProjectRepository
  from olive.models import Chat,Message
  from olive.projects import Project
  from olive.agent.permission_service import PermissionService,PermissionDecision
  with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
   src=Path(a);dst=Path(b);project=Project('User title mentioning DMDO');ProjectRepository(src/'projects.json').save(project)
   chat=Chat(title='Historical DMDO chat',messages=[Message('user','DMDO is the former name')]);ChatRepository(src/'chats.json').save_all([chat])
   permissions=PermissionService(src/'permissions.json');permissions.save({'contacts.write':'deny'})
   s=PersonalService(src/'personal.sqlite3',lambda:{project.id:project})
   c=s.save('contact',{'display_name':'DMDO fixture name','project_ids':[project.id]})
   event=s.save('event',{'title':'Old event','calendar_id':s.profile()['default_calendar'],'start':'2026-09-14T09:00:00+02:00','end':'2026-09-14T10:00:00+02:00','contact_ids':[c['id']],'project_id':project.id})
   task=s.save('task',{'title':'Old task','event_id':event['id'],'project_id':project.id})
   reminder=s.save('reminder',{'target_kind':'task','target_id':task['id'],'at':'2026-01-01T09:00:00Z','timezone':'UTC'})
   scheduler=ReminderScheduler(s,lambda *_:None,clock=lambda:datetime(2026,9,12,tzinfo=timezone.utc));scheduler.tick();delivery=scheduler.history()[0];scheduler.act(delivery['id'],'dismiss')
   archive=BackupService(src).create();legacy=src/'legacy.zip'
   with zipfile.ZipFile(archive) as old,zipfile.ZipFile(legacy,'w') as new:
    for name in old.namelist():
     value=old.read(name)
     if name=='manifest.json':
      manifest=json.loads(value);self.assertEqual(manifest['product'],'OLIVE');manifest['product']='DMDO';manifest['dmdo_version']=manifest.pop('olive_version');value=json.dumps(manifest).encode()
     new.writestr(name,value)
   BackupService(dst).restore(legacy,confirmed=True)
   restored=PersonalService(dst/'personal.sqlite3',ProjectRepository(dst/'projects.json').load_all)
   for kind,record in [('contact',c),('event',event),('task',task),('reminder',reminder)]:
    self.assertEqual(restored.get(kind,record['id'])['uid'],record['uid'])
   self.assertEqual(restored.get('contact',c['id'])['display_name'],'DMDO fixture name')
   self.assertEqual(ChatRepository(dst/'chats.json').load_all()[chat.id].messages[0].content,'DMDO is the former name')
   self.assertIn(project.id,ProjectRepository(dst/'projects.json').load_all())
   self.assertEqual(PermissionService(dst/'permissions.json').evaluate('contacts.write').decision,PermissionDecision.DENY)
   self.assertEqual(ReminderScheduler(restored,lambda *_:None).history()[0]['state'],'dismissed')
 def test_current_prompt_keeps_historical_content(self):
  from olive.services.prompt_service import PromptBuilder
  from olive.config import DEFAULT_SYSTEM_PROMPT
  self.assertTrue(DEFAULT_SYSTEM_PROMPT.startswith('You are OLIVE'))
  result=PromptBuilder().build(system_prompt='You are DMDO',notes='Historical DMDO note',summary='',memories=[],rag_results=[],history=[],user_text='Who are you?')
  self.assertIn('current application and assistant name is OLIVE',result[0]['content'])
  self.assertIn('Historical DMDO note',result[0]['content'])

 def test_current_identity_templates_and_ui_do_not_reintroduce_old_brand(self):
  root=Path(__file__).resolve().parents[1]
  for base in [root/'desktop/src',root/'olive/ui_qt/experience/qml']:
   for path in base.rglob('*'):
    if path.suffix in {'.tsx','.ts','.qml','.css'}:
     self.assertNotIn('dmdo',path.read_text(encoding='utf-8').lower(),str(path.relative_to(root)))
  from olive.identity import display_alias
  self.assertEqual(display_alias('DMDO-CHAT'),'OLIVE-CHAT')
  self.assertEqual(display_alias('custom-dmdo-model:latest'),'custom-dmdo-model:latest')
  from olive.ui_qt.application import OliveApplication
  import dmdo.ui_qt.application as legacy
  self.assertIs(legacy.DMDOApplication,OliveApplication)
