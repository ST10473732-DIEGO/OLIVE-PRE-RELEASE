"""Synthetic linked records in an empty temporary profile; no inference/network/actions."""
import asyncio,json,os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
async def main():
 profile=Path(sys.argv[1]).resolve()
 if not profile.is_relative_to(Path(tempfile.gettempdir()).resolve()) or any(profile.iterdir()):raise ValueError('Use an empty temporary fixture profile')
 os.environ['OLIVE_DATA_DIR']=str(profile)
 from olive.application.service_container import ServiceContainer
 from olive.models import DocumentRef
 from olive.agent.agent_task import AgentTask,AgentStep
 from olive.research.models import ResearchSession
 s=ServiceContainer(lambda *args:None,lambda *args:False,data_dir=profile,migrate=False)
 project=s.data.create_project('Fixture linked project','Synthetic records for cross-feature navigation review.')
 workspace=profile/'fixture-workspace';workspace.mkdir();(workspace/'tests').mkdir()
 (workspace/'main.py').write_text('def add(left, right):\n    return left + right\n\nif __name__ == "__main__":\n    print(add(2, 3))\n',encoding='utf-8')
 (workspace/'tests'/'test_main.py').write_text('import unittest\nfrom main import add\n\nclass FixtureTests(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n',encoding='utf-8')
 s.data.create_workspace('Fixture review workspace',str(workspace),project['id'])
 chat=s.chats[s.current_chat_id];chat.title='Fixture linked conversation';chat.project_id=project['id'];chat.add_message('user','Fixture context, not a private conversation.');chat.add_message('assistant','Illustrative fixture response; no model was run.\n\n```python\nprint("Fixture local work")\n```')
 file=profile/'fixture-notes.txt';file.write_text('Harmless fixture source content.',encoding='utf-8')
 chat.documents.append(DocumentRef(id='fixture-source',name=file.name,stored_path=str(file),original_path=str(file),indexed=False));s.save_chats()
 memory=s.memory.add('Fixture project prefers outcome-based tests.','project')
 p=s.project_repo.load_all()[project['id']];p.memory_ids=[memory.id];s.project_repo.save(p)
 task=AgentTask('Fixture linked task (no execution)',project_id=p.id,state='failed');task.plan=[AgentStep('Illustrative completed read',state='completed'),AgentStep('Illustrative blocked validation',state='failed')];task.completion_summary='Fixture partial history; no tools were executed.';s.agent_task_repo.save(task)
 research=ResearchSession('Fixture linked investigation',status='completed');research.final_report='# Fixture report\n\nIllustrative findings, not live research.';s.research.repository.save(research)
 s.research.reports.write({'schema_version':1,'reports':[{'id':'fixture-report','session_id':research.id,'project_id':p.id,'question':research.question,'report':research.final_report,'created_at':research.updated_at}]})
 print(json.dumps({'project_id':p.id,'chat_id':chat.id,'memory_id':memory.id,'task_id':task.id,'research_id':research.id}))
 await s.shutdown()
if __name__=='__main__':asyncio.run(main())
