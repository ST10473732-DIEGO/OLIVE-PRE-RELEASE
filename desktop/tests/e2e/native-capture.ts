import { expect, type ElectronApplication, type Page } from '@playwright/test';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { captureMail } from './m4-capture';

// Linux captures only Electron's owned window compositor. Windows retains HWND capture.
export async function captureOwnedWindow(page: Page, app: ElectronApplication, output: string) {
  if (process.platform !== 'win32') return captureMail(page, app, output);
  const child = spawn(path.resolve('../.venv/Scripts/python.exe'), [path.resolve('../scripts/capture_fixture_window.py'), '--pid', String(await app.evaluate(() => process.pid)), '--output', output], { windowsHide: true });
  await expect.poll(() => child.exitCode, { timeout: 15000 }).toBe(0);
}
