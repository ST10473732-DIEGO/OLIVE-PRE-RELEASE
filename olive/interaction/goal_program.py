"""Finite typed branches for goals the router can execute without a planner.

Only literal request content selects steps. A branch runs only when its typed
trigger holds for a verified earlier outcome; otherwise it is reported as
explicitly skipped. No loop, shell or model-selected effect is introduced.
"""
import re

from .task_goal import SKIPPED


def conditional_test_program(request, goal):
    """"Run the tests; if they fail explain, if they pass commit" style goals."""
    if not any(e.effect == 'test' for e in goal.requested_effects):
        return None
    if any(e.effect not in {'test', 'explain', 'commit', 'stage'} for e in goal.requested_effects):
        return None  # Other effects need the normal interpreter; constraints still apply.
    triggers = {c.trigger for c in goal.conditions}
    if not triggers & {'tests_fail', 'tests_pass'} and not goal.constraints:
        return None
    steps = [{'intent': 'code.test', 'entities': {}, 'references': {}}]
    if 'tests_fail' in triggers or any(e.effect == 'explain' for e in goal.requested_effects):
        steps.append({'intent': 'code.explain_failure', 'entities': {}, 'references': {}, 'when': 'tests_fail'})
    commit = next((e for e in goal.requested_effects if e.effect == 'commit'), None)
    if commit:
        message = re.search(r'\bmessage\s+(["\'“])(.{1,200}?)["\'”]', request)
        if not message:
            return {'confidence': 1, 'clarification': 'What commit message should I use if the tests pass?', 'steps': []}
        when = 'tests_pass' if commit.conditional == 'tests_pass' or 'tests_fail' in triggers else ''
        steps.append({'intent': 'code.git', 'entities': {'operation': 'add', 'files': '.'}, 'references': {}, 'when': when or 'tests_pass'})
        steps.append({'intent': 'code.git', 'entities': {'operation': 'commit', 'message': message.group(2)},
                      'references': {}, 'when': when or 'tests_pass'})
    return {'confidence': 1, 'clarification': '', 'steps': steps}


MUTATION_GOALS = {'save_note', 'copy', 'move', 'send', 'draft', 'create_directory', 'commit', 'stage', 'code_edit',
                  'run', 'test', 'trash'}
INTERNAL_SURFACES = {'studio', 'olive', 'chat', 'settings', 'mail', 'calendar', 'tasks', 'files'}
STEP_EFFECTS = {'code.test': 'test', 'code.run': 'run', 'code.explain_failure': 'explain', 'filesystem.copy': 'copy',
                'filesystem.move': 'move', 'filesystem.create_directory': 'create_directory',
                'filesystem.create_file': 'save_note', 'filesystem.edit_file': 'save_note', 'filesystem.trash': 'trash',
                'filesystem.search': 'search', 'communication.send': 'send', 'communication.compose': 'draft',
                'browser.search': 'search', 'application.search': 'search', 'browser.navigate': 'visit',
                'application.launch': 'open', 'application.activate': 'open', 'code.modify': 'code_edit',
                'project.create': 'create_project', 'knowledge.query': 'read'}


def step_effect(step):
    if step['intent'] == 'code.git':
        return {'add': 'stage', 'commit': 'commit', 'create_branch': 'branch', 'checkout': 'switch'}.get(
            step['entities'].get('operation'), 'git_read')
    return STEP_EFFECTS.get(step['intent'], '')


def gate(step, outcome, goal):
    """Return a skip reason when the step's typed branch condition is not met."""
    when = step.get('when')
    if not when:
        return ''
    if not outcome or outcome.get('intent') != 'code.test':
        return 'the test result was not verified'
    passed = outcome.get('passed')
    if when == 'tests_fail' and passed:
        return 'the tests passed'
    if when == 'tests_pass' and not passed:
        return 'the tests did not pass'
    return ''


def skip(goal, step, reason):
    effect = step_effect(step)
    goal.mark(effect, SKIPPED, reason)
