import { test, expect, _electron as electron } from '@playwright/test';
import path from 'node:path';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { spawnSync } from 'node:child_process';
import { createServer } from 'node:http';
import { openSpace } from './shell';

test('Linux L2: launcher, live presets, GPU residency, cancellation, route churn and owned shutdown', async () => {
  test.skip(process.platform !== 'linux' || process.env.OLIVE_LIVE_AI !== '1', 'Real Linux Ollama models required');
  test.setTimeout(600000);
  const root = path.resolve('..');
  const python = path.join(root, '.venv/bin/python');
  const profile = await mkdtemp(path.join(tmpdir(), 'olive-linux-l2-'));
  const seed = spawnSync(python, [path.join(root, 'scripts/seed_electron_fixture.py'), profile], { encoding: 'utf8' });
  expect(seed.status, seed.stderr).toBe(0);
  await writeFile(path.join(profile, 'fixture-workspace/main.py'), 'word = input("Enter a word: ")\nprint(word)\n');
  const server = createServer((_req, res) => res.end('<title>L2 fixture</title><p>Linux L2 Browser fixture</p>'));
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const app = await electron.launch({ executablePath: path.join(root, 'run_olive.sh'), chromiumSandbox: true,
    args: ['--ozone-platform=wayland'], env: { ...process.env, OLIVE_DATA_DIR: profile }, timeout: 60000 });
  const errors: string[] = [];
  let rejected = 0;
  app.process().stderr?.on('data', chunk => { rejected += (String(chunk).match(/Error occurred in handler for 'olive:call'/g) || []).length; });
  let owned = '[]';
  try {
    const page = await app.firstWindow();
    page.on('pageerror', error => errors.push(error.message));
    await page.getByRole('button', { name: 'Enter OLIVE', exact: true }).click();
    await openSpace(page, 'Chat');
    const snapshot = () => page.evaluate(() => window.olive.call('runtime.snapshot', {})) as Promise<{
      chat: { id: string; model: string; messages: { role: string; content: string }[] };
      presets: { id: string; available: boolean }[]; activity: { items: unknown[] };
    }>;
    await expect.poll(async () => (await snapshot()).presets.filter(p => ['fast', 'normal', 'max'].includes(p.id) && p.available).length, { timeout: 30000 }).toBe(3);
    const evidence: unknown[] = [];
    const ask = async (question: string) => {
      const count = (await snapshot()).chat.messages.length;
      await page.getByRole('textbox', { name: 'Message OLIVE', exact: true }).fill(question);
      await page.getByRole('button', { name: 'Send message', exact: true }).click();
      await expect.poll(async () => {
        const s = await snapshot();
        return s.chat.messages.length > count && s.chat.messages.at(-1)?.role === 'assistant' && !s.activity.items.length;
      }, { timeout: 150000 }).toBe(true);
      const answer = (await snapshot()).chat.messages.at(-1)!.content;
      expect(answer).not.toMatch(/unavailable|returned no answer|output limit|stopped before completing/i);
      expect(answer.length).toBeGreaterThan(20);
      return answer;
    };
    for (const preset of ['fast', 'normal', 'max']) {
      await page.getByRole('combobox', { name: 'OLIVE preset', exact: true }).selectOption(preset);
      const answer = await ask('What is recursion? Answer in two sentences.');
      const residency = await (await fetch('http://127.0.0.1:11434/api/ps')).json() as { models: { name: string; size_vram: number }[] };
      expect(residency.models).toHaveLength(1);
      expect(residency.models[0].size_vram).toBeGreaterThan(0);
      evidence.push({ preset, model: (await snapshot()).chat.model, answer, residency });
    }
    await page.getByRole('combobox', { name: 'OLIVE preset', exact: true }).selectOption('fast');
    await page.getByRole('textbox', { name: 'Message OLIVE', exact: true }).fill('Explain recursion in 100 detailed numbered paragraphs.');
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    await page.getByRole('button', { name: 'Stop response', exact: true }).click({ timeout: 30000 });
    await expect(page.getByRole('button', { name: 'Stop response', exact: true })).toBeHidden();
    evidence.push({ recovery: await ask('Define a base case in one sentence.') });
    await openSpace(page, 'OLIVE GO');
    await page.locator('.go-ntp input').fill(`http://127.0.0.1:${(server.address() as { port: number }).port}/`);
    await page.locator('.go-ntp input').press('Enter');
    await expect.poll(() => app.evaluate(async ({ webContents }) => {
      const view = webContents.getAllWebContents().find(w => w.getURL().startsWith('http://127.0.0.1:'));
      return view && !view.isLoading() ? view.executeJavaScript('document.body.innerText') : '';
    })).toContain('Linux L2 Browser fixture');
    await openSpace(page, 'Studio');
    await page.getByRole('button', { name: 'Fixture · local Python project', exact: true }).click();
    await page.getByRole('button', { name: 'Run', exact: true }).click();
    const terminal = page.locator('.terminal-view:not([hidden])');
    await expect(terminal).toContainText('Enter a word:');
    await terminal.locator('textarea').pressSequentially('level');
    await terminal.locator('textarea').press('Enter');
    await expect(page.getByRole('tab', { name: /Run program.*exited/ })).toBeVisible();
    const contents = await app.evaluate(({ webContents }) => webContents.getAllWebContents().length);
    for (let i = 0; i < 3; i++) {
      for (const route of ['Chat', 'OLIVE GO', 'Studio']) await openSpace(page, route);
    }
    expect(await app.evaluate(({ webContents }) => webContents.getAllWebContents().length)).toBe(contents);
    // Leave a real input-waiting program open; application shutdown owns cleanup.
    await page.getByRole('button', { name: 'Run', exact: true }).click();
    await expect(terminal).toContainText('Enter a word:');
    await page.screenshot({ path: test.info().outputPath('linux-l2-studio.png') });
    expect(errors).toEqual([]); expect(rejected).toBe(0);
    const probe = spawnSync(python, ['-c', 'import psutil,json,sys; p=psutil.Process(int(sys.argv[1])); print(json.dumps([(c.pid,c.create_time()) for c in [p,*p.children(recursive=True)]]))', String(app.process().pid)], { encoding: 'utf8' });
    expect(probe.status, probe.stderr).toBe(0); owned = probe.stdout.trim();
    await writeFile(test.info().outputPath('linux-l2.json'), JSON.stringify({ evidence, errors, rejected, contents, owned: JSON.parse(owned) }, null, 2));
  } finally {
    await app.close(); server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve()));
  }
  await expect.poll(() => {
    const probe = spawnSync(python, ['-c', 'import psutil,json,sys\nlive=[]\nfor pid,created in json.loads(sys.argv[1]):\n try:\n  p=psutil.Process(pid)\n  if p.create_time()==created: live.append(pid)\n except psutil.NoSuchProcess: pass\nprint(json.dumps(live))', owned], { encoding: 'utf8' });
    expect(probe.status, probe.stderr).toBe(0); return JSON.parse(probe.stdout);
  }, { timeout: 15000 }).toEqual([]);
});

test('Linux backend interruption is visible and restart recovers without replay', async () => {
  test.skip(process.platform !== 'linux', 'Linux owned-process probe');
  const root = path.resolve('..'), python = path.join(root, '.venv/bin/python');
  const profile = await mkdtemp(path.join(tmpdir(), 'olive-linux-l2-recovery-'));
  const launch = () => electron.launch({ chromiumSandbox: true, args: [path.resolve('.'), '--ozone-platform=wayland'],
    env: { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: process.env.OLIVE_LIVE_AI === '1' ? 'http://127.0.0.1:11434' : 'http://127.0.0.1:1' } });
  let app = await launch();
  try {
    let page = await app.firstWindow();
    await page.getByRole('button', { name: 'Enter OLIVE', exact: true }).click();
    const before = await page.evaluate(() => window.olive.call('runtime.snapshot', {})) as { workspaces: unknown[]; chat: { id: string } };
    await page.evaluate(id => window.olive.call('chat.draft', { chat_id: id, text: 'Synthetic recovery draft' }), before.chat.id);
    const probe = spawnSync(python, ['-c', 'import psutil,sys\np=psutil.Process(int(sys.argv[1]))\nowned=[c for c in p.children() if c.cmdline()[-2:]==["-m","olive.bridge"]]\nassert len(owned)==1\nimport json; print(json.dumps([(c.pid,c.create_time()) for c in [owned[0],*owned[0].children(recursive=True)]]))\nowned[0].terminate()', String(app.process().pid)], { encoding: 'utf8' });
    expect(probe.status, probe.stderr).toBe(0);
    await expect(page.getByText('Python disconnected. No actions were replayed. Restart OLIVE after reviewing any uncertain work.', { exact: true })).toBeVisible();
    await expect.poll(() => {
      const remaining = spawnSync(python, ['-c', 'import psutil,json,sys\nlive=[]\nfor pid,created in json.loads(sys.argv[1]):\n try:\n  p=psutil.Process(pid)\n  if p.create_time()==created: live.append(pid)\n except psutil.NoSuchProcess: pass\nprint(json.dumps(live))', probe.stdout.trim()], { encoding: 'utf8' });
      expect(remaining.status, remaining.stderr).toBe(0); return JSON.parse(remaining.stdout);
    }, { timeout: 15000 }).toEqual([]);
    await app.close();
    app = await launch(); page = await app.firstWindow();
    await page.getByRole('button', { name: 'Enter OLIVE', exact: true }).click();
    const after = await page.evaluate(() => window.olive.call('runtime.snapshot', {})) as { workspaces: unknown[]; chat: { id: string } };
    expect(after.workspaces).toEqual(before.workspaces); expect(after.chat.id).toBe(before.chat.id);
    await openSpace(page, 'Chat');
    await expect(page.getByRole('textbox', { name: 'Message OLIVE', exact: true })).toBeVisible();
  } finally { await app.close(); }
});
