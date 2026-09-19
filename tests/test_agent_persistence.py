import tempfile, unittest
from pathlib import Path
from olive.agent.agent_task import AgentTask
from olive.projects import Project
from olive.storage.agent_task_repository import AgentTaskRepository
from olive.storage.project_repository import ProjectRepository

class PersistenceTests(unittest.TestCase):
    def test_project_round_trip_and_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=ProjectRepository(Path(tmp)/"projects.json"); project=Project("OLIVE",root_folders=[tmp]); repo.save(project)
            self.assertEqual(repo.resolve("continue my OLIVE project").id,project.id)
    def test_risky_task_is_paused_not_resumed_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=AgentTaskRepository(Path(tmp)/"tasks.json"); task=AgentTask("work"); task.transition("running"); repo.save(task)
            recovered=repo.recover_interrupted(); self.assertEqual(recovered[0].state,"paused")
    def test_v32_completion_state_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=AgentTaskRepository(Path(tmp)/"tasks.json")
            task=AgentTask("Fix bug",implementation_status="complete",validation_status="passed",completion_conditions=["Tests pass"],completion_evidence=["151 tests passed"],reasoning_summary="Targeted parser fix")
            repo.save(task);loaded=repo.load_all()[task.id]
            self.assertEqual(loaded.implementation_status,"complete")
            self.assertEqual(loaded.completion_conditions,["Tests pass"])
            self.assertEqual(loaded.reasoning_summary,"Targeted parser fix")
