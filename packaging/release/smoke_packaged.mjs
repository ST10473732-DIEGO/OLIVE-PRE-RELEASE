// Launch smoke test for an installed OLIVE package on a clean CI runner (no Playwright).
//
//   node packaging/release/smoke_packaged.mjs <path to the installed OLIVE executable>
//
// Starts the app with a DevTools port, waits for the renderer, and passes only when the first-run
// setup wizard is shown with the release manifest. The wizard renders after the packaged backend
// answered runtime.setup_status, so this proves the bundled backend starts and responds. It never
// installs anything, and the runner's profile is thrown away with the runner.
import { spawn, execFileSync } from "node:child_process";

const executable = process.argv[2];
if (!executable) {
  console.error("usage: smoke_packaged.mjs <executable>");
  process.exit(2);
}
const PORT = 9333;
const DEADLINE = Date.now() + 180_000;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const child = spawn(executable, [`--remote-debugging-port=${PORT}`], {
  stdio: ["ignore", "inherit", "inherit"],
  detached: process.platform !== "win32",
});
let exited = null;
child.on("exit", (code, signal) => { exited = { code, signal }; });

function stop() {
  try {
    if (process.platform === "win32") execFileSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    else process.kill(-child.pid, "SIGTERM");
  } catch { /* already gone */ }
}

async function page() {
  while (Date.now() < DEADLINE && !exited) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const found = targets.find((t) => t.type === "page" && t.webSocketDebuggerUrl && !t.url.startsWith("devtools:"));
      if (found) return found;
    } catch { /* not listening yet */ }
    await sleep(1000);
  }
  return null;
}

function evaluate(socket, expression) {
  return new Promise((resolve, reject) => {
    const id = Math.floor(Math.random() * 1e9);
    const onMessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id !== id) return;
      socket.removeEventListener("message", onMessage);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result.result.value);
    };
    socket.addEventListener("message", onMessage);
    socket.send(JSON.stringify({ id, method: "Runtime.evaluate", params: { expression, returnByValue: true } }));
  });
}

const PROBE = `JSON.stringify({
  url: location.href,
  title: document.title,
  setup: !!document.querySelector('main.setup[aria-label="OLIVE setup"]'),
  testManifest: !!document.querySelector('.setup-banner'),
  step: document.querySelector('.setup-step-name')?.textContent ?? null,
  alert: document.querySelector('[role="alert"]')?.textContent ?? null,
})`;

let result = null;
try {
  const target = await page();
  if (!target) throw new Error(exited ? `OLIVE exited early: ${JSON.stringify(exited)}` : "no renderer page appeared");
  console.log("renderer:", target.url);
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = () => reject(new Error("DevTools connection failed")); });
  while (Date.now() < DEADLINE && !exited) {
    result = JSON.parse(await evaluate(socket, PROBE));
    if (result.setup) break;
    await sleep(1000);
  }
  socket.close();
  console.log("probe:", JSON.stringify(result));
  if (!result?.setup) throw new Error("the first-run setup wizard never appeared");
  if (result.testManifest) throw new Error("the package uses a test runtime manifest");
  console.log("PASS: packaged OLIVE started its backend and showed release first-run setup");
} catch (error) {
  console.error("FAIL:", error.message);
  process.exitCode = 1;
} finally {
  stop();
}
