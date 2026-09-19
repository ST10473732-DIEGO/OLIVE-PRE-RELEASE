// Bounded live-local identity check. Synthetic profile, unchanged model assignments.
const { _electron: electron, expect } = require('../desktop/node_modules/@playwright/test');
const fs = require('node:fs/promises');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
(async () => {
  const evidence = path.join(root, 'artifacts/rebrand/local-identity');
  await fs.mkdir(evidence, {recursive:true});
  const profile = await fs.mkdtemp(path.join(evidence, 'profile-'));
  const result = {classification:'live local Electron/Python/Ollama; synthetic conversation',profile,passed:false};
  let app;
  try {
    app = await electron.launch({args:[path.join(root,'desktop')],env:{...process.env,OLIVE_DATA_DIR:profile,OLIVE_OLLAMA_HOST:'http://127.0.0.1:11434'}});
    const page = await app.firstWindow();
    await page.getByRole('button',{name:'Enter OLIVE',exact:true}).click();
    await expect.poll(async () => (await page.evaluate(() => window.olive.call('runtime.snapshot',{}))).initializing,{timeout:60000}).toBe(false);
    const snapshot = await page.evaluate(() => window.olive.call('runtime.snapshot',{}));
    result.model = snapshot.chat.model;
    if (!snapshot.models.length) throw Error('No installed local model available in the runtime');
    const request = 'What is your current application name? Answer briefly.';
    result.request = request;
    const started = performance.now();
    await page.getByRole('textbox',{name:'Ask OLIVE anything',exact:true}).fill(request);
    await page.getByRole('button',{name:'Submit request',exact:true}).click();
    await expect.poll(async () => {
      const chat = await page.evaluate(id => window.olive.call('chat.get',{chat_id:id}),snapshot.chat.id);
      const answer = chat.messages.filter(m => m.role === 'assistant').at(-1);
      if (answer && !chat.generating) {result.answer = answer.content; return true;}
      return false;
    },{timeout:180000}).toBe(true);
    result.elapsedMs = Math.round(performance.now()-started);
    result.interpretation = await page.evaluate(id => window.olive.call('interaction.inspect',{chat_id:id}),snapshot.chat.id);
    await page.screenshot({path:path.join(evidence,'identity.png')});
    expect(result.answer).toMatch(/\bOLIVE\b/);
    result.passed = true;
  } catch (error) {result.primaryError=String(error);process.exitCode=1;}
  finally {
    if (app) try {await app.close();result.cleanup='owned Electron runtime closed';} catch(error){result.cleanupError=String(error);process.exitCode=1;}
    await fs.writeFile(path.join(evidence,'result.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify(result,null,2));
  }
})();
