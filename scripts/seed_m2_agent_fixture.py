"""Explicit illustrative task records in a caller-selected isolated review profile."""
from pathlib import Path
import os
import sys

if __name__ == '__main__':
    profile = Path(sys.argv[1]).resolve()
    if profile == (Path.home() / '.olive').resolve():
        raise SystemExit('Use an isolated fixture profile')
    os.environ['OLIVE_DATA_DIR'] = str(profile)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from olive.agent.agent_task import AgentTask, AgentStep
    from olive.storage.agent_task_repository import AgentTaskRepository
    task = AgentTask('Fixture: partial task record (no execution)', state='failed')
    task.plan = [AgentStep('Illustrative source read', state='completed'),
                 AgentStep('Illustrative validation', state='failed'),
                 AgentStep('Later action', state='pending')]
    task.completion_summary = 'Illustrative review fixture. No tool or external action was executed to create this record.'
    task.validation_status = 'failed'
    task.completion_evidence = ['Fixture record only; not live execution evidence.']
    task.files_changed = []
    AgentTaskRepository(profile / 'agent_tasks.json').save(task)
