import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { openSpace, showPanel } from "./shell";
import { captureMail } from "./m4-capture";
test("Local preview is bound to a real run and has no application bridge", async () => {
  const root = path.resolve("..");
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-preview-"));
  const seed = spawnSync(
    path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
    [path.join(root, "scripts/seed_electron_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  await writeFile(
    path.join(profile, "fixture-workspace/main.py"),
    `import http.server
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(b"""<html><body style="background:#eef2f8;color:#16243a;font:18px system-ui;padding:24px"><h1>Fixture local application</h1><p>Actual Python RunSession. No private data.</p><button onclick="document.querySelector(\'p\').textContent=\'Fixture interaction works.\'">Check interaction</button></body></html>""")
server=http.server.HTTPServer(('127.0.0.1',0),Handler)
print('http://127.0.0.1:'+str(server.server_port),flush=True)
server.serve_forever()
`,
  );
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(15000);
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Studio");
    await page
      .getByRole("button", {
        name: "Fixture · local Python project",
        exact: true,
      })
      .click();
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await expect(page.locator('.terminal-view:not([hidden])')).toContainText("http://127.0.0.1", { timeout: 15000 });
    await showPanel(page, "Output");
    await expect(page.locator(".output-terminal")).toContainText(
      "http://127.0.0.1",
    );
    await page.getByText("Workspace actions", { exact: true }).click();
    await page.getByRole("button", { name: "Local app preview" }).click();
    await expect
      .poll(() =>
        app.evaluate(
          ({ webContents }) =>
            webContents
              .getAllWebContents()
              .filter((view) => view.getURL().startsWith("http://127.0.0.1:"))
              .length,
        ),
      )
      .toBe(1);
    const observed = await app.evaluate(async ({ webContents }) => {
      const view = webContents
        .getAllWebContents()
        .find((view) => view.getURL().startsWith("http://127.0.0.1:"))!;
      return {
        prefs: (
          view as unknown as {
            getLastWebPreferences: () => Record<string, boolean>;
          }
        ).getLastWebPreferences(),
        bridge: await view.executeJavaScript("typeof window.olive"),
        node: await view.executeJavaScript("typeof require"),
        text: await view.executeJavaScript("document.body.innerText"),
        external: await view.executeJavaScript(
          "fetch('http://127.0.0.1:9').then(()=>false).catch(()=>true)",
        ),
      };
    });
    expect(observed.bridge).toBe("undefined");
    expect(observed.node).toBe("undefined");
    expect(observed.prefs.nodeIntegration).toBe(false);
    expect(observed.prefs.sandbox).toBe(true);
    expect(observed.text).toContain("Actual Python RunSession");
    expect(observed.external).toBe(true);
    const evidence = path.join(root, "artifacts/ui-review/M2");
    await mkdir(evidence, { recursive: true });
    await captureMail(page, app, path.join(evidence, "studio-isolated-live-local-preview.png"));
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Close", exact: true })
      .click();
    await expect
      .poll(() =>
        app.evaluate(
          ({ webContents }) =>
            webContents
              .getAllWebContents()
              .filter((view) => view.getURL().startsWith("http://127.0.0.1:"))
              .length,
        ),
      )
      .toBe(0);
    await page.getByRole("button", { name: "Stop program" }).click();
    await expect(page.locator(".output-terminal")).toContainText("stopped");
  } finally {
    await app.close();
  }
});
