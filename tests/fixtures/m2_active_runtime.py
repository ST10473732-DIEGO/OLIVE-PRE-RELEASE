"""Test-only controlled work for real Electron/Python UI tests.

Loaded by a temporary sitecustomize, never by product code. No model, network,
desktop provider, input or external tool is executed. Cancellation/pause controls
still use the original controllers. All visible records explicitly say Fixture.
"""
import asyncio
import os
import tempfile
from pathlib import Path

from olive.application.service_container import ServiceContainer
from olive.agent.agent_task import AgentTask, AgentStep
from olive.desktop.models import DesktopControlSession
from olive.services.memory_suggestion_service import MemorySuggestion

profile = Path(os.environ.get('OLIVE_DATA_DIR', '')).resolve()
if not profile.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not profile.name.startswith('olive-m2-active-'):
    raise RuntimeError('Active fixtures require their own temporary test profile')

original = ServiceContainer.initialize


async def initialize(self):
    await original(self)
    task = AgentTask('Fixture: controlled pending work; no tools executed', state='running')
    task.plan = [AgentStep('Illustrative source read', state='completed'),
                 AgentStep('Controlled wait for cancellation', state='running')]
    task.completion_evidence = ['Mocked work fixture. Controller pause and cancellation are real.']
    self.agent.current = task
    self.agent.publish(task)

    async def agent_work():
        try:
            while not self.agent.cancel_event.is_set():
                if not self.agent.gate.is_set():
                    # Simulate a bounded operation finishing before a safe pause boundary.
                    await asyncio.sleep(1)
                    task.plan[1].state = 'paused'
                await self.agent.wait_for_resume(task)
                if not self.agent.cancel_event.is_set() and task.plan[1].state != 'running':
                    task.plan[1].state = 'running'
                    self.agent.publish(task)
                await asyncio.sleep(.02)
            task.transition('cancelled')
            task.plan[1].state = 'cancelled'
            task.completion_summary = 'Fixture wait cancelled. No tools or external actions executed.'
        finally:
            self.agent.active = None
            self.agent.publish(task)

    self.agent.active = asyncio.create_task(agent_work())
    record = DesktopControlSession('Fixture: controlled application wait, no desktop input',
        application='Fixture application', status='running',
        current_action='Waiting in an inert test coroutine',
        verification='Fixture only; no real application state was observed',
        history=[{'action':'Illustrative observation', 'status':'fixture', 'application':'Fixture application'}])
    self.desktop.record = record

    async def desktop_work():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            record.status = 'cancelled'
            record.verification = 'Fixture wait cancelled. No input was generated.'
        finally:
            self.desktop.operation = None
            self.desktop.publish()

    self.desktop.operation = asyncio.create_task(desktop_work())
    self.desktop.publish()
    for content in ('Fixture suggested preference to correct', 'Fixture suggestion to reject'):
        suggestion = MemorySuggestion(content, 'preference', self.current_chat_id, 0)
        self.chat.suggestions[suggestion.id] = suggestion
    self.publish('memory_suggestion', {})


ServiceContainer.initialize = initialize
