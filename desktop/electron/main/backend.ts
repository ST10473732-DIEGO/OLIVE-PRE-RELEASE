import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { randomUUID } from "node:crypto";
import { EventEmitter } from "node:events";
export class Backend extends EventEmitter {
  private child!: ChildProcessWithoutNullStreams;
  private buffer = Buffer.alloc(0);
  private pending = new Map<string, {
    resolve: (v: unknown) => void;
    reject: (e: Error) => void;
    timer: NodeJS.Timeout;
  }>();
  private ready!: Promise<void>;
  private dead = false;
  private closing = false;
  private recoveryTimer?: NodeJS.Timeout;
  private failures: number[] = [];
  private readonly recover: boolean;
  constructor(
    private readonly python: string,
    private readonly args: string[],
    private readonly root: string,
    private readonly env: NodeJS.ProcessEnv,
  ) {
    super();
    this.recover = env.OLIVE_RECOVER_PYTHON === "1" && process.platform === "darwin";
    this.launch();
  }
  private launch() {
    if (this.closing) return;
    this.dead = false;
    this.buffer = Buffer.alloc(0);
    const child = spawn(this.python, this.args, {
      cwd: this.root, windowsHide: true, env: this.env,
      stdio: ["pipe", "pipe", "pipe"], shell: false,
    });
    this.child = child;
    this.ready = new Promise<void>((resolve, reject) => {
      const started = () => {
        clearTimeout(timer);
        this.off("lost", disconnected);
        resolve();
      };
      const disconnected = () => {
        clearTimeout(timer);
        this.off("ready", started);
        reject(new Error("Python runtime unavailable"));
      };
      const timer = setTimeout(() => {
        if (this.child === child) this.lost();
      }, 30000);
      this.once("ready", started);
      this.once("lost", disconnected);
    });
    void this.ready.catch(() => undefined);
    child.stdout.on("data", (chunk: Buffer) => {
      if (this.child === child) this.receive(chunk);
    });
    // Never forward diagnostic text to the renderer or console.
    child.stderr.on("data", () => undefined);
    child.on("error", () => {
      if (this.child === child) this.lost(true);
    });
    child.on("exit", () => {
      if (this.child === child) this.lost(true);
    });
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
  private lost(recoverable = false) {
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
    // Only a confirmed process exit/error can restart. A malformed backend
    // protocol, oversized frame, or uncertain running child stays fail-closed.
    if (recoverable && this.recover && !this.closing) {
      const now = Date.now();
      this.failures = this.failures.filter((time) => now - time < 300000);
      if (this.failures.length < 3) {
        this.failures.push(now);
        this.recoveryTimer = setTimeout(() => {
          this.recoveryTimer = undefined;
          if (!this.closing) this.launch();
        }, 2000);
      } else {
        this.emit("recovery_exhausted");
      }
    }
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
    this.closing = true;
    if (this.recoveryTimer) clearTimeout(this.recoveryTimer);
    if (this.dead) {
      this.child.stdin.destroy();
      return;
    }
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
