const { test } = require('node:test');
const assert = require('node:assert/strict');
const { recordFailure, terminalOutcome, selectedLaunch, inspectionPolicies } = require('./desktop_attach_outcome.cjs');
test('original attach failure wins over page-close and teardown errors', () => {
  const result = { cleanup_errors: [] };
  recordFailure(result, 'attach', 'original');
  recordFailure(result, 'page-closed', 'secondary');
  result.cleanup_errors.push('page closed during cleanup');
  assert.deepEqual(result.primary_error, { stage: 'attach', error: 'original' });
  assert.equal(terminalOutcome({ failure: 'original', closed: true }).detail, 'original');
});
test('visible error terminates an observation wait without a session', () => {
  assert.equal(terminalOutcome({ state: { session: null }, alerts: ['Attach failed'] }).kind, 'failure');
});
test('approval, cancellation, observation, and timeout are distinct terminal outcomes', () => {
  assert.equal(terminalOutcome({ approval: { id: 'approval' } }).kind, 'approval_pending');
  assert.equal(terminalOutcome({ state: { stopped: true } }).kind, 'cancelled');
  assert.equal(terminalOutcome({ state: { observation: { window: { hwnd: 1 } } } }).kind, 'observation');
  assert.equal(terminalOutcome({ expired: true }).kind, 'timeout');
  assert.equal(terminalOutcome({ state: { session: null } }), null);
});
test('historical launches do not override the target selected in Electron', () => {
  const old = { launch_id: 'old', application: 'm2_desktop_acceptance_window.py', state: 'launched_not_inspected' };
  const selected = { ...old, launch_id: 'selected' };
  assert.equal(selectedLaunch([old, selected], 'selected', false), selected);
  for (const id of ['', 'unknown']) assert.throws(() => selectedLaunch([old, selected], id, false));
  assert.throws(() => selectedLaunch([selected, selected], 'selected', false));
  assert.throws(() => selectedLaunch([{ ...selected, application: 'different.py' }], 'selected', false));
  const attached = { ...selected, state: 'attached' };
  assert.throws(() => selectedLaunch([attached], 'selected', false));
  assert.equal(selectedLaunch([attached], 'selected', true), attached);
});
test('accessible fixture requires explicit identity and narrow approved policies', () => {
  const launch = { launch_id: 'qt', application: 'm2_accessible_acceptance_window.py', state: 'launched_not_inspected' };
  assert.throws(() => selectedLaunch([launch], 'qt', false));
  assert.equal(selectedLaunch([launch], 'qt', false, launch.application), launch);
  const policy = { enabled: true, uia: true, screen_observation: false, vision_fallback: false,
    mouse_policy: 'deny', keyboard_policy: 'ask', unknown_app_policy: 'ask' };
  inspectionPolicies(policy, true);
  for (const change of [{ keyboard_policy: 'deny' }, { keyboard_policy: 'allow' }, { mouse_policy: 'ask' },
    { screen_observation: true }, { vision_fallback: true }, { unknown_app_policy: 'allow' }, { enabled: false }]) {
    assert.throws(() => inspectionPolicies({ ...policy, ...change }, true));
  }
  inspectionPolicies({ ...policy, keyboard_policy: 'deny' }, false);
  assert.throws(() => inspectionPolicies(policy, false));
});
