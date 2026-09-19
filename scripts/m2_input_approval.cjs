// Test-session approval validation only; not a production permission provider.
const assert = require('node:assert/strict');
const path = require('node:path');
function hashesByWindowsPath(hashes) {
  const values = {};
  for (const [file, hash] of Object.entries(hashes)) {
    assert.ok(path.win32.isAbsolute(file));
    const key = path.win32.normalize(file).toLowerCase();
    if (key in values) assert.equal(values[key], hash, 'Conflicting hashes for the same Windows path');
    values[key] = hash;
  }
  return values;
}
function validateApproval(a, phase, expected) {
  const app = 'm2_accessible_acceptance_window.py';
  assert.equal(a.allow_remember, false);
  assert.deepEqual(a.targets, [app]);
  assert.equal(a.arguments.application, app);
  assert.ok(a.id && a.fingerprint && a.expires_at * 1000 > Date.now());
  const args = a.arguments;
  const permitted = { launch: ['terminal.execute', 'system.open_application'],
    attach: ['desktop.inspect_application'], text: ['desktop.keyboard_input', 'desktop.control_application'],
    invoke: ['desktop.control_application'] };
  assert.ok(permitted[phase]?.includes(a.tool_name), 'Unexpected permission');
  if (phase === 'launch') {
    assert.deepEqual({ ...args, file_hashes: hashesByWindowsPath(args.file_hashes) },
      { ...expected.launchArguments, file_hashes: hashesByWindowsPath(expected.launchArguments.file_hashes) });
  } else {
    assert.deepEqual(args.window_identity, expected.window);
    const wanted = { application: app, window_identity: expected.window };
    if (phase === 'text' && a.tool_name === 'desktop.keyboard_input')
      Object.assign(wanted, { target: 'Acceptance text', text: 'OLIVE local acceptance' });
    else if (phase !== 'attach')
      Object.assign(wanted, { target: phase === 'text' ? 'Acceptance text' : 'Check text', action: phase === 'text' ? 'set_text' : 'invoke' });
    assert.deepEqual(args, wanted);
  }
}
module.exports = { validateApproval };
