import { afterEach, expect, it } from "vitest";
import { Backend } from "../electron/main/backend";

const instances: Backend[] = [];
afterEach(async () => {
  for (const item of instances.splice(0)) await item.close();
});

it.skipIf(process.platform !== "darwin")(
  "recovers a crashed macOS backend without replaying a pending request, then caps retries",
  async () => {
    const script = [
      'process.stdout.write(JSON.stringify({v:1,kind:"event",seq:1,topic:"runtime.ready",data:{ready:true}})+"\\n")',
      "process.stdin.resume()",
      "setTimeout(() => process.exit(39), 130)",
    ].join(";");
    const backend = new Backend(
      process.execPath,
      ["-e", script],
      process.cwd(),
      { ...process.env, OLIVE_RECOVER_PYTHON: "1" },
    );
    instances.push(backend);
    let ready = 0;
    let lost = 0;
    let exhausted = false;
    let rejectedUnconfirmed = false;
    backend.on("ready", () => {
      ready += 1;
      if (ready === 1) {
        void backend.request("desktop.status", {}).catch((e: Error) => {
          rejectedUnconfirmed = e.message.includes("not replayed");
        });
      }
    });
    backend.on("lost", () => { lost += 1; });
    backend.on("recovery_exhausted", () => { exhausted = true; });
    const deadline = Date.now() + 11500;
    while (!exhausted && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    expect(exhausted).toBe(true);
    expect(ready).toBe(4); // Initial launch + three bounded recoveries
    expect(lost).toBe(4);
    expect(rejectedUnconfirmed).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(ready).toBe(4); // no unbounded restart storm
  },
  14000,
);
