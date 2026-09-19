// Read-only live capture. Run only after user initiation, with an isolated
// Electron profile and the intended launch selected through the actual UI.
// Does not approve requests, launch targets, invoke target controls, or close windows.
const { chromium } = require('../desktop/node_modules/@playwright/test');
const fs = require('node:fs/promises');
const path = require('node:path');
const { recordFailure, terminalOutcome, selectedLaunch, inspectionPolicies } = require('./desktop_attach_outcome.cjs');
async function bounded(promise, ms = 10000) {
  let timer;
  try { return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(Error('Capture read timed out')), ms); })]); }
  finally { clearTimeout(timer); }
}

(async () => {
  const [profile, output, consent, ...flags] = process.argv.slice(2);
  if (flags.some(flag => !['--observe-pending', '--accessible-target'].includes(flag))) throw Error('Unknown capture option');
  const resume = flags.includes('--observe-pending');
  const accessible = flags.includes('--accessible-target');
  const target = accessible ? 'm2_accessible_acceptance_window.py' : 'm2_desktop_acceptance_window.py';
  const title = accessible ? 'OLIVE M2 accessible acceptance target' : 'OLIVE M2 local acceptance target';
  if (!profile || !output || consent !== '--user-initiated')
    throw Error('Usage: node scripts/capture_desktop_attach.cjs ISOLATED_PROFILE NEW_OUTPUT --user-initiated [--observe-pending] [--accessible-target]');
  const out = path.resolve(output);
  await fs.mkdir(out); // Never overwrite earlier acceptance evidence.
  const result = { scope: 'Target-only inspection; no input, invocation, screen capture or auto-approval', cleanup_errors: [], events: [] };
  const save = () => fs.writeFile(path.join(out, 'result.json'), JSON.stringify(result, null, 2));
  let browser, page;
  try {
    const [port, endpoint] = (await fs.readFile(path.join(profile, 'electron-shell/DevToolsActivePort'), 'utf8')).split(/\r?\n/);
    if (!/^\d+$/.test(port) || !/^\/devtools\/browser\/[a-f0-9-]+$/.test(endpoint)) throw Error('Invalid owned Electron debugging endpoint');
    // Include this launch's browser UUID: a reused port must not attach to a
    // different Electron instance after the intended one closes.
    browser = await chromium.connectOverCDP(`ws://127.0.0.1:${port}${endpoint}`);
    const pages = browser.contexts().flatMap(context => context.pages());
    if (pages.length !== 1 || !pages[0].url().startsWith('dmdo://')) throw Error('Expected one OLIVE application page');
    page = pages[0];
    let failure;
    await page.exposeFunction('captureAttachFailure', data => {
      failure = data;
      recordFailure(result, data.stage, JSON.stringify(data));
    });
    await page.evaluate(() => {
      window.attachCaptureUnsubscribe = window.olive.subscribe(event => {
        if (event.topic === 'request.failure') void window.captureAttachFailure(event.data);
      });
    });
    const before = await page.evaluate(() => window.olive.call('desktop.status', {}));
    result.before = before;
    if (!before.settings.enabled || before.stopped || (!resume && (before.active || before.session)))
      throw Error('Expected an enabled, idle isolated session with no attached target');
    inspectionPolicies(before.settings, accessible);
    const launches = await page.evaluate(() => window.olive.call('desktop.launches', {}));
    const selected = await page.getByRole('combobox', { name: 'Owned launch' }).inputValue({ timeout: 5000 });
    const launch = selectedLaunch(launches, selected, resume, target);
    if (await page.getByRole('alert').count()) throw Error('Resolve existing alert before a new operation');
    result.launch = launch;
    result.stage = resume ? 'observe_existing_request' : 'attach_requested';
    await save();
    if (!resume) {
      await page.getByRole('button', { name: 'Attach launched target', exact: true }).click();
    }
    const deadline = Date.now() + 90000;
    while (true) {
      const closed = page.isClosed();
      const alerts = closed ? [] : await page.getByRole('alert').allTextContents();
      if (alerts.length) recordFailure(result, failure?.stage || 'attach', alerts.join('\n'));
      const failed = closed || failure || alerts.length;
      const state = failed ? null : await bounded(page.evaluate(() => window.olive.call('desktop.status', {})));
      const snapshot = failed ? null : await bounded(page.evaluate(() => window.olive.call('runtime.snapshot', {})));
      const approval = snapshot?.approvals?.find(a => a.tool_name === 'desktop.inspect_application');
      const terminal = terminalOutcome({ failure, alerts, state, approval, closed, expired: Date.now() >= deadline });
      if (terminal) {
        result.outcome = terminal;
        result.state = state;
        if (terminal.kind === 'observation' && state.observation.window.title !== title) {
          result.outcome = { kind: 'failure', detail: 'Unexpected observed target; stopped' };
          recordFailure(result, 'observation_identity', result.outcome.detail);
        }
        if (['failure', 'timeout'].includes(terminal.kind)) recordFailure(result, failure?.stage || 'attach', JSON.stringify(terminal.detail));
        if (!closed) {
          try { await page.screenshot({ path: path.join(out, 'attach-state.png'), timeout: 10000 }); }
          catch (error) { result.cleanup_errors.push('Capture: ' + String(error)); }
        }
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 250));
    }
  } catch (error) {
    recordFailure(result, result.stage || 'preflight', error);
  } finally {
    // Approval remains for the user. Every other terminal outcome requests Stop.
    // This is evidence of a latch request, not proof of interrupting active input.
    if (page && result.outcome?.kind !== 'approval_pending') {
      try {
        await bounded(page.evaluate(() => window.olive.stopControl()));
        result.stopped = await bounded(page.evaluate(() => window.olive.call('desktop.status', {})));
      } catch (error) { result.cleanup_errors.push(String(error)); }
    }
    try { if (page && !page.isClosed()) await page.evaluate(() => window.attachCaptureUnsubscribe?.()); }
    catch (error) { result.cleanup_errors.push(String(error)); }
    try { if (browser) await browser.close(); } // Disconnect CDP, not the owned Electron process.
    catch (error) { result.cleanup_errors.push(String(error)); }
    result.cleanup = 'Electron/target retained for user review; owned-process closure must be recorded separately';
    await save();
    console.log(JSON.stringify({ outcome: result.outcome?.kind, primary_error: result.primary_error, output: out }));
    if (result.primary_error) process.exitCode = 1;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
