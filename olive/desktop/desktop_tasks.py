"""Chat desktop tasks on the shared Agent task card, with effect receipts.

Every Chat-originated desktop task gets one AgentTask (kind='desktop') so the
existing task card shows its factual timeline ("✓ Firefox focused") and Stop.
Input is recorded as receipts: reserved before dispatch with the expected
result, settled from the next observation. Navigation input is class
``desktop_input``; a message send is ``external`` and is never retried when its
outcome is uncertain (also after a restart, see AgentTaskRepository).

Receipts hold identities, revisions and digests only: no page text, message
body, screenshot or typed text.
"""
import hashlib
import re

from ..agent.agent_task import AgentTask
from ..agent.receipts import COMPLETED, DESKTOP_INPUT, EXTERNAL, FAILED, UNCERTAIN, NOT_APPLIED, reserve, settle

# Public error prefix -> task failure category.
CATEGORY_BY_CODE = {
    'APPLICATION_NOT_INSTALLED': 'application not installed', 'APPLICATION_DID_NOT_OPEN': 'application did not open',
    'APPLICATION_NOT_RUNNING': 'application did not open', 'NEEDS_USER_CLARIFICATION': 'multiple windows match',
    'MULTIPLE_WINDOWS': 'multiple windows match', 'WINDOW_DISAPPEARED': 'window disappeared',
    'WINDOW_CHANGED': 'window changed', 'WINDOW_OFF_MONITOR': 'window changed',
    'CONTROL_UNAVAILABLE': 'control unavailable', 'CONTROL_AMBIGUOUS': 'control ambiguous',
    'TARGET_AMBIGUOUS': 'control ambiguous', 'STALE_OBSERVATION': 'stale observation',
    'TARGET_NOT_VISIBLE': 'target not visible', 'DESTINATION_UNVERIFIED': 'destination unverified',
    'DIALOG_REQUIRES_USER': 'dialog requires user', 'AUTHENTICATION_REQUIRED': 'authentication required',
    'CAPTCHA_REQUIRED': 'captcha required', 'DESKTOP_CONTROL_UNAVAILABLE': 'desktop control unavailable',
    'INPUT_REFUSED': 'input refused', 'URL_REFUSED': 'input refused', 'NAVIGATION_TIMED_OUT': 'navigation timed out',
    'LAYOUT_INCOMPATIBLE': 'target not visible',
}


def category_for(message):
    match = re.match(r'\s*([A-Z][A-Z_]{5,})\b', str(message or ''))
    return CATEGORY_BY_CODE.get(match.group(1), '') if match else ''


def digest(value):
    return hashlib.sha256(str(value).encode('utf-8', 'replace')).hexdigest()[:16]


class DesktopTaskRecord:
    """One desktop task; a no-op when there is no chat/task repository (tests, scripts)."""

    def __init__(self, services, chat_id, message_id, request):
        self.s = services
        self.repo = getattr(services, 'agent_task_repo', None)
        self.task = None
        if self.repo is not None and chat_id:
            self.task = AgentTask(request[:4000], kind='desktop', chat_id=chat_id, message_id=message_id)
            self.task.transition('running')
            self.save()

    @property
    def id(self):
        return self.task.id if self.task else ''

    def save(self):
        if self.task is None:
            return
        try:
            self.repo.save(self.task)
        except Exception:
            return  # The desktop task itself never fails because its card could not be written.
        self.s.publish('agent', {'id': self.task.id, 'kind': 'desktop', 'state': self.task.state})

    def status(self, text):
        if self.task is not None and text and self.task.status_text != text:
            self.task.status_text = text[:200]
            self.save()

    def done(self, text, status='done', **evidence):
        if self.task is not None:
            self.task.note(text, status, **evidence)
            self.save()

    def reserve(self, operation, effect, *, application='', window='', revision='', expected=''):
        """Before input: what will be done, where, and what must be observed afterwards."""
        if self.task is None:
            return None
        if effect not in {DESKTOP_INPUT, EXTERNAL}:
            raise ValueError('Desktop receipts are desktop_input or external')
        receipt = reserve(self.task, 'desktop.' + operation,
                          {'application': application, 'window': window, 'revision': revision, 'expected': expected},
                          effect, step=operation, target=f'{application}:{window}')
        receipt['evidence'].update({'application': application, 'window': window, 'revision': revision,
                                    'expected': expected[:200]})
        self.save()
        return receipt

    def settle(self, receipt, state, observed=''):
        if receipt is None or self.task is None:
            return
        if state not in {COMPLETED, FAILED, UNCERTAIN, NOT_APPLIED}:
            raise ValueError('Unknown receipt state')
        settle(receipt, state, observed=observed[:200])
        self.save()

    def open_receipts(self):
        return [r for r in (self.task.receipts if self.task else []) if r['state'] == 'reserved']

    def finish(self, state, summary='', category='', detail=''):
        """completed | failed | cancelled | waiting_user | paused."""
        if self.task is None or self.task.terminal:
            return
        # A reservation still open at the end was dispatched but not confirmed.
        for receipt in self.open_receipts():
            settle(receipt, UNCERTAIN, observed='not confirmed before the task ended')
        if state == 'failed':
            self.task.fail(category or category_for(detail) or 'tool unavailable', detail or summary)
        else:
            self.task.transition(state)
            if state in {'waiting_user', 'paused'}:
                self.task.failure_category = category or category_for(detail)
                self.task.error = (detail or summary)[:2000]
        self.task.completion_summary = summary[:2000] if summary else self.task.completion_summary
        self.task.status_text = ''
        self.save()
