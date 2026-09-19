"""Maintain M3 evidence in the existing individual release ledger; retain all IDs."""
import argparse,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'docs/releases/3.5.1/requirements.json'
rows=json.loads(PATH.read_text(encoding='utf-8'))
parser=argparse.ArgumentParser()
parser.add_argument('--complete',action='store_true')
args=parser.parse_args()
if args.complete:
 for label,checks in {'final-regression-04':['compile','python','frontend','harness','electron'],'final-live-05':['language'],'final-ordinary-05':['electron']}.items():
  result=json.loads((ROOT/'artifacts/ui-review/M3'/label/'results.json').read_text(encoding='utf-8'))
  if any(result.get(check)!=0 for check in checks):raise SystemExit('Final evidence is missing or failing: '+label)
 qt=json.loads((ROOT/'artifacts/ui-review/M3/final-qt-02/results.json').read_text(encoding='utf-8'))
 if qt.get('errors') or not qt.get('checks') or not all(qt['checks'].values()):raise SystemExit('Qt fallback evidence is missing or failing')
groups={
 'data':('olive/personal/store.py; service.py; validation.py; controller.py','tests/test_personal_core.py; tests/test_personal_recovery.py'),
 'profile':('olive/personal/validation.py:profile; service.py:profile; desktop/src/features/personal/Profile.tsx','tests/test_personal_recovery.py; desktop/tests/e2e/m3-personal.spec.ts'),
 'contacts':('olive/personal/service.py:resolve_contact/duplicates/merge_preview/merge; interchange.py; desktop/src/features/personal/Contacts.tsx','tests/test_personal_core.py; test_personal_interchange.py; test_personal_policy_language.py; desktop/tests/e2e/m3-workflows.spec.ts'),
 'calendar':('olive/personal/calendar.py; service.py; interchange.py; desktop/src/features/personal/Calendar.tsx; EventEditor.tsx','tests/test_personal_core.py; test_personal_interchange.py; test_personal_boundaries.py; desktop/tests/e2e/m3-workflows.spec.ts'),
 'tasks':('olive/personal/service.py:schedule_task/search; reminders.py; desktop/src/features/personal/Tasks.tsx; Reminders.tsx','tests/test_personal_core.py; test_personal_recovery.py; test_personal_boundaries.py; desktop/tests/e2e/m3-workflows.spec.ts'),
 'language':('olive/personal/language.py; olive/interaction/interpreter.py; native_pending.py; router.py; context.py; desktop/src/features/personal/Proposals.tsx','tests/test_personal_policy_language.py; tests/test_native_pending.py; desktop/tests/e2e/m3-language-live.spec.ts'),
 'policy':('olive/personal/controller.py; contracts.py; olive/agent/permission_service.py; existing ToolExecutor/ConfirmationService; desktop/electron/m3-contracts.ts','tests/test_personal_policy_language.py; test_personal_boundaries.py; test_native_pending.py; desktop/tests/m3-native.test.ts'),
 'backup':('olive/services/backup_service.py; olive/application/data_controller.py; olive/bridge/host.py; olive/personal/store.py','tests/test_personal_recovery.py; test_personal_boundaries.py; desktop/tests/e2e/m3-backup.spec.ts'),
 'offline':('olive/application/service_container.py; olive/personal; desktop/src/features/personal; existing Settings','desktop/tests/e2e/m3-personal.spec.ts; m3-workflows.spec.ts; tests/test_personal_policy_language.py'),
 'navigation':('desktop/src/app/App.tsx; navigation/spaces.ts; features/Home.tsx; features/Projects.tsx; features/personal/Today.tsx','desktop/tests/e2e/m3-personal.spec.ts; m3-workflows.spec.ts; m3-language-live.spec.ts'),
}
section_groups={'R351-21':'data','R351-22':'contacts','R351-23':'calendar','R351-25':'policy','R351-26':'language',
 'C350-24':'data','C350-25':'profile','C350-26':'contacts','C350-27':'calendar','C350-28':'calendar','C350-29':'tasks',
 'C350-34':'language','C350-35':'policy','C350-36':'backup','C350-37':'offline','C350-48':'navigation','C350-50':'language','C350-51':'language'}
mail_sections={'R351-24','C350-30','C350-31','C350-32','C350-33','C350-49','C350-52'}
mail_ids={'R351-21-07','C350-24-06','C350-26-30','C350-28-15','C350-37-13','C350-48-09',
 *[f'R351-25-{n:02}' for n in range(1,14)],*[f'R351-26-{n:02}' for n in (4,10,11,12,13)],
 *[f'C350-50-{n:02}' for n in range(15,22)],*[f'C350-51-{n:02}' for n in (1,2,3,5,6,7)],
 *[f'C350-35-{n:02}' for n in (3,4,5,11)]}
for row in rows:
 identity=row['id'];section=identity.rsplit('-',1)[0]
 if section in mail_sections or identity in mail_ids:
  row.setdefault('pre_m3_milestone',row['milestone']);row['milestone']='M4'
  row['limitation']='Explicit current M3 scope reserves native Mail, transport and mail credential-vault expansion for M4. Requirement retained; no native Mail completion claimed.'
  continue
 if row['milestone']!='M3' or section not in section_groups:continue
 group=section_groups[section]
 if identity=='R351-22-01':group='profile'
 if section=='R351-23' and int(identity[-2:])>=19:group='tasks'
 implementation,evidence=groups[group]
 row.setdefault('pre_m3_status',row['status']);row.setdefault('pre_m3_evidence',row['evidence'])
 row.update(implementation=implementation,status='M3 implementation present; final integrated acceptance in progress',implemented=True,
            acceptance='Verify this action/constraint through the listed domain tests and actual Electron entry; see M3_STATUS.md.',
            evidence=evidence+'; artifacts/ui-review/M3 (classifications and exact runs in M3_STATUS.md)',
            limitation='Unit/controller cases are not live model evidence. Individual live demonstrations and self-review are separately recorded; no universal reliability or user visual approval claimed.',
            user_approved=False)
 if identity in {'C350-28-10','C350-28-11'}:
  row.update(classification='conditional',implemented=False,status='Not implemented: optional drag/resize deferred',
             limitation='Current M3 brief makes dragging/resizing conditional. All essential event operations use keyboard-accessible forms and validated services. No drag control is advertised.')
 if identity=='C350-24-17':row['limitation']='Existing indexing scheduler is domain-specific. Native reminders use one service in the existing supervised runtime, without repurposing indexing jobs or creating another runtime/service.'
 if identity=='C350-25-08':row.update(implementation='Existing Settings application/execution/location preferences; profile preferences in olive/personal/validation.py',limitation='Existing trusted Settings remain authoritative for application/location policy; Profile does not duplicate that repository.')
 if identity in {'C350-34-12','C350-35-02','C350-35-14','C350-37-15'}:row['limitation']='M3 native portion implemented; existing M2 capabilities retained. Mail-specific continuation remains M4 and is not declared complete here.'
 if args.complete and row['implemented']:
  row['status']='M3 native implementation and internal acceptance complete; see classified action evidence'
  row['acceptance']='M3_COMPLETION.md A-L maps UI/API actions, deterministic tests, actual Electron and installed-model evidence. No user screenshot approval inferred.'
  row['evidence']=evidence+'; M3_COMPLETION.md; artifacts/ui-review/M3/final-regression-04; final-ordinary-05; final-live-05; final-qt-02'
  if section=='C350-28' and int(identity[-2:])<=9:row['visually_reviewed']=True
  if identity in {'C350-51-04','C350-51-08','C350-51-10','C350-51-11'}:row.update(integration_tested=True,live_tested=True)
PATH.write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(f'{len(rows)} original individual IDs retained; M3 implementation and M4 residual scope recorded.')
