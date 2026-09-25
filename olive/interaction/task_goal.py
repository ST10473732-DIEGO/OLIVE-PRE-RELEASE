"""Typed task goals: requested effects, negative constraints and finite conditions.

Derived deterministically from the literal local request, never from a model or
an observation. The goal can only narrow authority: it rejects plans that omit a
requested effect or violate a constraint, skips branches whose condition is not
met, and reports every requested effect with an explicit final status. Hidden
reasoning is not stored; only these concise records exist for the task lifetime.
"""
from dataclasses import dataclass, field
import hashlib
import re
import time
import uuid

from .deliverable import instruction_text

PENDING, COMPLETED, SKIPPED, CANCELLED, FAILED, CLARIFY = (
    'PENDING', 'COMPLETED', 'EXPLICITLY_SKIPPED_BY_CONDITION', 'CANCELLED', 'FAILED', 'NEEDS_CLARIFICATION')
FINAL = {COMPLETED, SKIPPED, CANCELLED, FAILED, CLARIFY}
# Plan effects that only move/observe toward a requested effect.
PREREQUISITES = {'open', 'visit', 'read', 'scroll', 'tab', 'search', 'click', 'summarize'}
MUTATIONS = {'edit_save', 'paste_save', 'copy', 'move', 'send', 'draft', 'create_directory', 'code_edit',
             'commit', 'stage', 'close'}
NEGATION = r"(?:do not|don['’]t|never|without)"


@dataclass(frozen=True)
class Constraint:
    kind: str            # forbid | no_overwrite | draft_only | no_file_changes | exact_destination
    effect: str = ''     # forbidden effect class, when applicable
    target: str = ''     # literal target named by the user
    text: str = ''       # the literal clause, for the user-facing report

    def violated_by(self, effect, target=''):
        if self.kind == 'draft_only':
            return effect == 'send'
        if self.kind == 'no_file_changes':
            return effect in {'edit_save', 'paste_save', 'copy', 'move', 'create_directory', 'code_edit', 'commit',
                              'stage', 'trash'}
        if self.kind == 'forbid':
            if effect != self.effect:
                return False
            return not self.target or not target or self.target.casefold() in target.casefold() \
                or target.casefold() in self.target.casefold()
        return False


@dataclass(frozen=True)
class Condition:
    trigger: str         # tests_fail | tests_pass | exists | multiple
    action: str          # explain | skip | ask | proceed
    effect: str = ''     # effect governed by this branch
    text: str = ''


@dataclass
class RequiredEffect:
    effect: str
    target: str = ''
    status: str = PENDING
    detail: str = ''
    conditional: str = ''  # trigger that must hold for this effect to run


@dataclass
class TaskGoal:
    original_user_request: str
    constraints: tuple = ()
    conditions: tuple = ()
    requested_effects: list = field(default_factory=list)
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    owner_context: str = 'local'
    result_bindings: dict = field(default_factory=dict)
    current_location: dict = field(default_factory=dict)
    completed_steps: list = field(default_factory=list)
    pending_steps: list = field(default_factory=list)
    unresolved_requirements: list = field(default_factory=list)
    effect_reservations: dict = field(default_factory=dict)
    cancellation_epoch: int = 0
    deadline: float = field(default_factory=lambda: time.monotonic() + 600)
    max_steps: int = 24
    replans: list = field(default_factory=list)
    repair_budget: int = 3

    @property
    def provenance(self):
        return hashlib.sha256(self.original_user_request.encode()).hexdigest()

    @property
    def prohibited_effects(self):
        return tuple(c for c in self.constraints if c.kind in {'forbid', 'draft_only', 'no_file_changes'})

    # ------------------------------------------------------------------ checks
    def check_effect(self, effect, target=''):
        """Re-evaluated before every effect; raises instead of silently skipping."""
        if time.monotonic() >= self.deadline:
            raise TimeoutError('The task deadline passed; remaining effects were not attempted')
        for constraint in self.constraints:
            if constraint.violated_by(effect, target):
                raise PermissionError('PLAN_SCOPE_EXPANSION: this step would violate your constraint “'
                                      + (constraint.text or constraint.kind) + '”; nothing was changed')

    def completeness(self, plan_effects):
        """Return requested effects a proposed plan omits (typed, no prose)."""
        missing = []
        planned = [(e, (t or '').casefold()) for e, t in plan_effects]
        for required in self.requested_effects:
            if required.conditional:
                continue  # Conditional branches are executed by the goal program, not the planner.
            aliases = EFFECT_ALIASES.get(required.effect, {required.effect})
            matches = [t for e, t in planned if e in aliases]
            if not matches or required.target and not any(
                    not t or required.target.casefold() in t or t in required.target.casefold() for t in matches):
                missing.append(required)
        return missing

    def expansion(self, plan_effects):
        requested = {a for r in self.requested_effects for a in EFFECT_ALIASES.get(r.effect, {r.effect})}
        return [e for e, _ in plan_effects if e in MUTATIONS and e not in requested]

    def mark(self, effect, status, detail='', target=''):
        for required in self.requested_effects:
            if required.status == PENDING and effect in EFFECT_ALIASES.get(required.effect, {required.effect}) and (
                    not target or not required.target or required.target.casefold() in target.casefold()
                    or target.casefold() in required.target.casefold()):
                required.status, required.detail = status, detail[:300]
                return required
        return None

    def finish(self, cancelled=False, failed_detail=''):
        """Every requested effect ends in an explicit state; nothing is silently missing."""
        for required in self.requested_effects:
            if required.status == PENDING:
                required.status = CANCELLED if cancelled else FAILED if failed_detail else CLARIFY
                required.detail = required.detail or ('Stopped before this effect' if cancelled else
                                                      failed_detail[:300] or 'Not reached by the plan')
        return self.report()

    def report(self):
        if not self.requested_effects:
            return ''
        labels = {COMPLETED: 'done', SKIPPED: 'skipped by your condition', CANCELLED: 'cancelled',
                  FAILED: 'failed', CLARIFY: 'needs clarification', PENDING: 'pending'}
        lines = [f"- {EFFECT_LABELS.get(r.effect, r.effect)}{(' ' + r.target) if r.target else ''}: "
                 f"{labels[r.status]}{(' — ' + r.detail) if r.detail and r.status != COMPLETED else ''}"
                 for r in self.requested_effects]
        kept = [c.text for c in self.constraints if c.text]
        if kept:
            lines.append('- Constraints kept: ' + '; '.join(kept))
        return 'Task status:\n' + '\n'.join(lines)

    def all_completed(self):
        return all(r.status in {COMPLETED, SKIPPED} for r in self.requested_effects)

    def repair(self, reason):
        """Consume one bounded repair attempt; the reason is recorded, never hidden."""
        self.replans.append(reason[:200])
        self.repair_budget -= 1
        return self.repair_budget >= 0


EFFECT_ALIASES = {
    'open': {'open', 'visit', 'search', 'read', 'click', 'edit_save', 'paste_save', 'send', 'draft', 'copy', 'move'},
    'visit': {'visit', 'click'}, 'search': {'search'}, 'read': {'read', 'visit'}, 'summarize': {'summarize'},
    'save_note': {'edit_save', 'paste_save'}, 'copy': {'copy'}, 'move': {'move'}, 'send': {'send'},
    'draft': {'draft'}, 'create_directory': {'create_directory'}, 'test': {'test'}, 'run': {'run'},
    'commit': {'commit'}, 'stage': {'stage', 'commit'}, 'explain': {'explain'}, 'click': {'click'},
    'code_edit': {'code_edit'},
}
EFFECT_LABELS = {'open': 'Open', 'visit': 'Open page', 'search': 'Search', 'read': 'Read', 'summarize': 'Summarize',
                 'save_note': 'Save note', 'copy': 'Copy', 'move': 'Move', 'send': 'Send message', 'draft': 'Draft message',
                 'create_directory': 'Create folder', 'test': 'Run tests', 'run': 'Run project', 'commit': 'Commit',
                 'stage': 'Stage changes', 'explain': 'Explain failure', 'click': 'Click', 'code_edit': 'Edit code'}


# ---------------------------------------------------------------------- parse
CONSTRAINT_PATTERNS = (
    (rf"\b{NEGATION}\s+(close|quit|exit)\s+(?:the\s+)?([\w .+-]{{1,60}}?)(?=[.,;]|\s+(?:and|but|then)\b|$)",
     lambda m: Constraint('forbid', 'close', m.group(2).strip(), m.group(0).strip())),
    (rf"\b{NEGATION}\s+(?:overwrit\w*|replac\w*)\b[^.;,]*",
     lambda m: Constraint('no_overwrite', text=m.group(0).strip())),
    (r"\bif\s+(?:it|the file|that file|a file)\s+(?:already\s+)?exists,?\s+(?:do not|don['’]t)\s+overwrite(?:\s+it)?",
     lambda m: Constraint('no_overwrite', text=m.group(0).strip())),
    (rf"\b{NEGATION}\s+send\b[^.;,]*|\bjust\s+draft\s+it\b|\bdraft\s+only\b",
     lambda m: Constraint('draft_only', 'send', text=m.group(0).strip())),
    (rf"\b{NEGATION}\s+(?:edit|change|modify|touch)\s+(?:any(?:thing)?|any files?|the files?|files?|the code|my code)\b[^.;,]*"
     r"|\b(?:do not|don['’]t)\s+change\s+any\s+files\b|\bwithout\s+(?:editing|changing|modifying)\s+anything\b",
     lambda m: Constraint('no_file_changes', text=m.group(0).strip())),
    (rf"\b{NEGATION}\s+commit\b[^.;,]*",
     lambda m: Constraint('forbid', 'commit', text=m.group(0).strip())),
    (rf"\b{NEGATION}\s+delete\b[^.;,]*", lambda m: Constraint('forbid', 'trash', text=m.group(0).strip())),
    (r"\bonly\s+send\s+it\s+if\s+the\s+destination\s+is\s+exactly\s+([^.;]{1,120})",
     lambda m: Constraint('exact_destination', 'send', m.group(1).strip(), m.group(0).strip())),
)
CONDITION_PATTERNS = (
    (r"\bif\s+(?:they|the tests?|tests?|it)\s+fails?,?\s+(?:then\s+)?(?:explain|show|tell)\b[^.;]*",
     lambda m: Condition('tests_fail', 'explain', 'explain', m.group(0).strip())),
    (r"\bif\s+(?:they|the tests?|tests?|it)\s+pass(?:es)?,?\s+(?:then\s+)?commit\b[^.;]*",
     lambda m: Condition('tests_pass', 'proceed', 'commit', m.group(0).strip())),
    (r"\bif\s+there\s+(?:are|is)\s+(?:two|more than one|several|multiple)\b[^.;]*\bask\s+me\b[^.;]*",
     lambda m: Condition('multiple', 'ask', '', m.group(0).strip())),
    (r"\bif\s+(?:it|the file|that file)\s+(?:already\s+)?exists,?\s+(?:do not|don['’]t)\s+overwrite(?:\s+it)?",
     lambda m: Condition('exists', 'skip', 'save_note', m.group(0).strip())),
)


def derive_goal(request, max_steps=24):
    """Parse typed constraints/conditions/effects from the literal request."""
    text = instruction_text(request)
    constraints, conditions = [], []
    for pattern, build in CONSTRAINT_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            value = build(match)
            if value not in constraints:
                constraints.append(value)
    for pattern, build in CONDITION_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            conditions.append(build(match))
    effects = requested_effects(request, constraints, conditions)
    return TaskGoal(request, tuple(constraints), tuple(conditions), effects, max_steps=max_steps)


def residual_negation(request, goal=None):
    """Negations not understood as typed constraints/conditions remain unresolved."""
    text = instruction_text(request)
    goal = goal or derive_goal(request)
    for item in (*goal.constraints, *goal.conditions):
        if item.text:
            text = text.replace(item.text.casefold(), ' ')
    return bool(re.search(r"\b(?:without|unless|except|not|never)\b|don['’]t", text))


def requested_effects(request, constraints=(), conditions=()):
    text = instruction_text(request)
    for item in (*constraints, *conditions):
        if item.text:
            text = text.replace(item.text.casefold(), ' ')
    effects = []
    def add(effect, target='', conditional=''):
        if not any(e.effect == effect and e.target.casefold() == target.casefold() for e in effects):
            effects.append(RequiredEffect(effect, target, conditional=conditional))
    clauses = re.split(r'[.;,]\s*|\s+(?:and|then|but|also)\s+', text)
    clause_verbs = []
    for clause in clauses:
        clause = re.sub(r'^(?:please|then|and|also|finally|next|first)\s+', '', clause.strip())
        match = re.match(r'(open|launch|start|visit|go to|search(?: for)?|find|look up|read|summari[sz]e|save|copy|move|'
                         r'send|draft|create|make|run|test|commit|stage|explain|click|press|fix|edit|modify|refactor|'
                         r'implement)\b\s*(.{0,80})', clause)
        if match:
            clause_verbs.append(match.groups())
    for verb, rest in clause_verbs:
        rest = rest.strip()
        first = rest.split(' ')[0] if rest else ''
        if verb in {'open', 'launch', 'start'}:
            if re.match(r'https?://', rest):
                add('visit', rest.split()[0])
            elif re.match(r'(?:the\s+)?(?:page|result|official)', rest):
                add('visit')
            elif first and not re.match(r'(?:a|an|the|it|this|that)$', first):
                app = re.match(r'([\w.+-]+(?:\s+[A-Z][\w.+-]*)?)', rest).group(1)
                add('open', app)
        elif verb in {'visit', 'go to'}:
            add('visit')
        elif verb.startswith('search') or verb in {'find', 'look up'}:
            add('search')
        elif verb == 'read':
            add('read')
        elif verb.startswith('summari'):
            add('summarize')
        elif verb == 'save':
            add('save_note')
        elif verb in {'copy', 'move'}:
            add(verb)
        elif verb == 'send' and not rest.startswith('me '):
            add('send')
        elif verb == 'draft':
            add('draft')
        elif verb in {'create', 'make'} and re.match(r'(?:a\s+|an\s+|the\s+)?(?:new\s+)?(?:folder|directory)', rest):
            add('create_directory')
        elif verb in {'create', 'make'} and re.match(r'(?:a\s+|an\s+)?(?:new\s+)?(?:note|file|document)', rest):
            add('save_note')
        elif verb == 'run' and re.match(r'(?:the\s+|my\s+|all\s+)?(?:unit\s+)?tests?', rest):
            add('test')
        elif verb == 'test':
            add('test')
        elif verb == 'run':
            add('run')
        elif verb == 'commit':
            add('commit')
        elif verb in {'click', 'press'}:
            add('click')
        elif verb in {'fix', 'edit', 'modify', 'refactor', 'implement'}:
            add('code_edit')
    for condition in conditions:
        if condition.trigger == 'tests_fail' and condition.action == 'explain':
            add('explain', conditional='tests_fail')
        if condition.trigger == 'tests_pass' and condition.effect == 'commit':
            for effect in effects:
                if effect.effect == 'commit':
                    effect.conditional = 'tests_pass'
            add('commit', conditional='tests_pass')
    # A forbidden effect is never a requested effect.
    effects = [e for e in effects if not any(c.violated_by(next(iter(EFFECT_ALIASES.get(e.effect, {e.effect}))), e.target)
                                             for c in constraints if c.kind in {'forbid', 'draft_only'})]
    return effects


RECOVERABLE = ('did not expose one active window', 'did not become active', 'focus or geometry changed',
               'focus the intended application', 'choose the intended accessible application window',
               'lost focus', 'observe again', 'stale observation', 'did not expose its new window',
               'geometry changed during', 'ui remained unstable')


def recoverable(message):
    """Transient launch/observation failures that a fresh observation may resolve."""
    value = str(message).casefold()
    if any(word in value for word in ('ambiguous', 'clarif', 'permission', 'denied', 'overwrite', 'outcome',
                                      'crashed', 'account', 'destination', 'stopped')):
        return False
    return any(marker in value for marker in RECOVERABLE)


def running_applications(goal):
    """Snapshot of apps the user said not to close: name -> running (bool)."""
    import psutil
    names = {c.target.casefold() for c in goal.constraints if c.kind == 'forbid' and c.effect == 'close' and c.target}
    if not names:
        return {}
    found = {name: False for name in names}
    for process in psutil.process_iter(['name', 'cmdline']):
        try:
            label = ' '.join([process.info['name'] or '', *(process.info['cmdline'] or [])[:1]]).casefold()
        except (psutil.Error, TypeError):
            continue
        for name in names:
            if name in label:
                found[name] = True
    return found
