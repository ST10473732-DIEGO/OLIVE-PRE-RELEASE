import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";

test("Welcome refreshes real Connect Off, On, paired online, and Off without entering Home", async () => {
  const root = path.resolve("..");
  const profile = await mkdtemp(path.join(tmpdir(), "olive-welcome-connect-"));
  const shim = path.join(profile, "shim");
  await mkdir(shim);
  // Isolated real C2 pairing and C3 sockets, no synthetic Connect snapshot.
  await writeFile(path.join(shim, "sitecustomize.py"), `import sys,json\nfrom pathlib import Path\nsys.path.insert(0,${JSON.stringify(root)})
from olive.bridge.host import Host
from olive.connect.identity import DeviceKeyStore
from olive.connect.service import DesktopDeviceService
from tests.test_connect_pairing import MemoryVault
from tests.test_connect_network import pair
original = Host.start
async def start(self, directory):
    await original(self, directory)
    service = self.services.connect
    service.identities.key_store = DeviceKeyStore(MemoryVault())
    peer = DesktopDeviceService(Path(directory)/'peer', key_store=DeviceKeyStore(MemoryVault()))
    peer.rename(peer.local_id, 'Acceptance phone')
    pair(service, peer)
    service.rename(peer.local_id, 'Acceptance phone')
    listener = peer.enable_network('127.0.0.1', discovery=False)
    Path(directory, 'test-peer.json').write_text(json.dumps(dict(device_id=peer.local_id, port=listener.port)))
    close = service.close
    def cleanup():
        peer.close()
        close()
    service.close = cleanup
Host.start = start
`);
  const app = await electron.launch({ args: [path.resolve(".")], env: { ...process.env, OLIVE_DATA_DIR: profile, PYTHONPATH: shim, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" } });
  try {
    const page = await app.firstWindow();
    const welcome = page.locator("main.welcome");
    await expect(welcome.getByText("Acceptance phone paired · Connect is off", { exact: true })).toBeVisible({ timeout: 20000 });
    await page.evaluate(() => window.olive.call("connect.enable", { address: "127.0.0.1", discovery: false }));
    await expect(welcome.getByText("Acceptance phone paired · Connect is on", { exact: true })).toBeVisible({ timeout: 10000 });
    const peer = JSON.parse(await readFile(path.join(profile, "test-peer.json"), "utf8"));
    await page.evaluate((peer) => window.olive.call("connect.open", { ...peer, address: "127.0.0.1" }), peer);
    await expect(welcome.getByText("Acceptance phone connected", { exact: true })).toBeVisible({ timeout: 10000 });
    await page.evaluate(() => window.olive.call("connect.disable", {}));
    await expect(welcome.getByText("Acceptance phone paired · Connect is off", { exact: true })).toBeVisible({ timeout: 10000 });
    await expect(welcome.getByRole("button", { name: "Enter OLIVE", exact: true })).toBeVisible();
  } finally { await app.close(); }
});
