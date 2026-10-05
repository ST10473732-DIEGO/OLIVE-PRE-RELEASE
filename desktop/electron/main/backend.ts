import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { randomUUID } from "node:crypto";
import { EventEmitter } from "node:events";
export class Backend extends EventEmitter {
  private child: ChildProcessWithoutNullStreams;
  private buffer = Buffer.alloc(0);
  private pending = new Map<
    string,
    {
      resolve: (v: unknown) => void;
      reject: (e: Error) => void;
      timer: NodeJS.Timeout;
    }
  >();
  private ready: Promise<void>;
  private dead = false;
  constructor(python: string, args: string[], root: string, env: NodeJS.ProcessEnv) {
    super();
    this.child = spawn(python, args, {
      cwd: root,
      windowsHide: true,
      env,
      stdio: ["pipe", "pipe", "pipe"],
      shell: false,
    });
    this.ready = new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("Python startup timed out")),
        30000,
      );
      this.once("ready", () => {
        clearTimeout(timer);
        resolve();
      });
      this.once("lost", () => {
        clearTimeout(timer);
        reject(new Error("Python runtime unavailable"));
      });
    });
    void this.ready.catch(() => undefined);
    this.child.stdout.on("data", (chunk: Buffer) => this.receive(chunk));
    // Deliberately do not forward backend diagnostic text into renderer state or logs.
    this.child.stderr.on("data", () => undefined);
    this.child.on("error", () => this.lost());
    this.child.on("exit", () => this.lost());
  }
  private receive(chunk: Buffer) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    let position: number;
    while ((position = this.buffer.indexOf(10)) >= 0) {
      if (position > 1048576) {
        this.lost();
        return;
      }
      const raw = this.buffer.subarray(0, position);
      this.buffer = this.buffer.subarray(position + 1);
      try {
        const value = JSON.parse(raw.toString("utf8"));
        if (value.v !== 1 || !["event", "response"].includes(value.kind))
          throw new Error("Invalid protocol");
        if (value.kind === "event") {
          if (
            !Number.isSafeInteger(value.seq) ||
            typeof value.topic !== "string"
          )
            throw new Error("Invalid event");
          if (value.topic === "runtime.ready") this.emit("ready");
          this.emit("event", value);
        } else {
          const pending = this.pending.get(value.id);
          if (pending) {
            clearTimeout(pending.timer);
            this.pending.delete(value.id);
            if (value.ok === true) pending.resolve(value.result);
            else {
              console.error("OLIVE request failed", {
                request_id: value.id,
                method: value.error?.method,
                context_ids: value.error?.context_ids,
                feature: value.error?.feature,
                stage: value.error?.stage,
                category: value.error?.category ?? value.error?.code,
              });
              pending.reject(
                new Error(value.error?.message ?? "Backend request failed"),
              );
            }
          }
        }
      } catch {
        this.lost();
        return;
      }
    }
    if (this.buffer.length > 1048576) this.lost();
  }
  private lost() {
    if (this.dead) return;
    this.dead = true;
    this.child.stdin.destroy(); // EOF stops desktop input even if the renderer has vanished.
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(
        new Error("Runtime disconnected. Actions were not replayed."),
      );
    }
    this.pending.clear();
    this.emit("lost");
  }
  async request(
    method: string,
    args: unknown,
    id: string = randomUUID(),
  ): Promise<unknown> {
    await this.ready;
    if (this.dead) throw new Error("Runtime is disconnected");
    if (this.pending.has(id)) throw new Error("Duplicate in-flight request");
    const frame = JSON.stringify({ v: 1, id, method, args }) + "\n";
    if (
      Buffer.byteLength(frame) > 1048576 ||
      this.pending.size >= 32 ||
      this.child.stdin.writableLength > 1048576
    )
      throw new Error("Request capacity exceeded");
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(
          new Error("Request timed out; inspect activity before retrying."),
        );
      }, 360000);
      this.pending.set(id, { resolve, reject, timer });
      this.child.stdin.write(frame, (error) => {
        if (error) this.lost();
      });
    });
  }
  stopControl() {
    void this.request("desktop.stop", {}).catch(() =>
      this.child.stdin.destroy(),
    );
  }
  async close() {
    this.stopControl();
    await Promise.race([
      this.request("runtime.shutdown", {}).catch(() => undefined),
      new Promise((r) => setTimeout(r, 1500)),
    ]);
    this.child.stdin.end();
    // Ending stdin is what makes the backend stop its language servers,
    // debuggers and terminals. Killing it before that finishes orphans them on
    // the machine, so wait longer than their own bounded stop takes.
    await Promise.race([
      new Promise((r) => this.child.once("exit", r)),
      new Promise((r) => setTimeout(r, 8000)),
    ]);
    if (this.child.exitCode === null) this.child.kill();
  }
}
