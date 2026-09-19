const { test } = require('node:test');
const assert = require('node:assert/strict');
const { validateApproval } = require('./m2_input_approval.cjs');
test('delegation accepts exact target input and rejects broader or changed requests', () => {
  const window = { hwnd: 10, pid: 20, process_created: 30, title: 'fixture', executable: 'pythonw.exe' };
  const a = { id: 'one', fingerprint: 'bound', expires_at: Date.now()/1000+60, allow_remember: false,
    targets: ['m2_accessible_acceptance_window.py'], tool_name: 'desktop.keyboard_input',
    arguments: { application: 'm2_accessible_acceptance_window.py', window_identity: window, target: 'Acceptance text', text: 'OLIVE local acceptance' } };
  validateApproval(a, 'text', { window });
  for (const change of [{ tool_name: 'desktop.mouse_input' }, { allow_remember: true }, { expires_at: 0 },
    { targets: ['other'] }, { arguments: { ...a.arguments, text: 'different' } },
    { arguments: { ...a.arguments, window_identity: { ...window, pid: 21 } } },
    { arguments: { ...a.arguments, extra: 'broader scope' } }])
    assert.throws(() => validateApproval({ ...a, ...change }, 'text', { window }));
  assert.throws(() => validateApproval(a, 'invoke', { window }));
});
test('launch hashes allow matching Windows case aliases but reject changed files or hashes', () => {
  const args = { application: 'm2_accessible_acceptance_window.py', executable: 'D:\\Fixture\\pythonw.exe',
    arguments: ['D:\\Fixture\\target.py'], file_hashes: { 'D:\\Fixture\\pythonw.exe': 'one', 'D:\\Fixture\\target.py': 'two' } };
  const a = { id: 'launch', fingerprint: 'bound', expires_at: Date.now()/1000+60, allow_remember: false,
    targets: ['m2_accessible_acceptance_window.py'], tool_name: 'terminal.execute', arguments: args };
  const hashes = { ...args.file_hashes, 'd:\\fixture\\pythonw.exe': 'one' };
  validateApproval({ ...a, arguments: { ...args, file_hashes: hashes } }, 'launch', { launchArguments: args });
  for (const change of [{ 'd:\\fixture\\pythonw.exe': 'changed' }, { 'D:\\unrelated.exe': 'one' }])
    assert.throws(() => validateApproval({ ...a, arguments: { ...args, file_hashes: { ...hashes, ...change } } }, 'launch', { launchArguments: args }));
});
