import { WebContentsView, session, type BrowserWindow } from "electron";
import { randomUUID } from "node:crypto";
import { previewSchema } from "../preview";
import type { Backend } from "./backend";
export class Preview {
  private view: WebContentsView | null = null;
  private run = "";
  private generation = 0;
  private isolated = session.fromPartition(`olive-preview-${randomUUID()}`);
  constructor(
    private window: BrowserWindow,
    private backend: Backend,
  ) {
    this.isolated.setPermissionRequestHandler(
      (_contents, _permission, callback) => callback(false),
    );
    this.isolated.setPermissionCheckHandler(() => false);
    this.isolated.on("will-download", (event) => event.preventDefault());
    backend.on("lost", () => this.close());
    backend.on(
      "event",
      (event: { topic: string; data: { id?: string; state?: string } }) => {
        if (
          event.topic === "run" &&
          event.data.id === this.run &&
          event.data.state !== "running"
        )
          this.close();
        if (event.topic === "approval") this.close();
      },
    );
    window.webContents.on("did-start-navigation", () => this.close());
    window.webContents.on("render-process-gone", () => this.close());
    window.on("closed", () => this.close());
    window.on("resize", () => this.close());
    window.on("minimize", () => this.close());
  }
  close() {
    this.generation++;
    const view = this.view;
    this.view = null;
    this.run = "";
    if (view) {
      if (!this.window.isDestroyed())
        this.window.contentView.removeChildView(view);
      if (!view.webContents.isDestroyed()) view.webContents.close();
    }
    if (view && !this.window.isDestroyed())
      this.window.webContents.send("olive:preview-closed");
  }
  private bounds(bounds: Electron.Rectangle) {
    const [width, height] = this.window.getContentSize();
    if (
      bounds.x < 64 ||
      bounds.y < 100 ||
      bounds.x + bounds.width > width ||
      bounds.y + bounds.height > height - 20
    )
      throw new Error("Preview must remain inside the Studio content area");
    return bounds;
  }
  async action(input: unknown) {
    const value = previewSchema.parse(input);
    if (value.action === "close") {
      this.close();
      return;
    }
    const bounds = this.bounds(value.bounds);
    if (value.action === "bounds") {
      this.view?.setBounds(bounds);
      return;
    }
    this.close();
    const generation = this.generation;
    const result = (await this.backend.request("studio.preview_authorize", {
      session_id: value.session_id,
    })) as { url: string; session_id: string };
    if (generation !== this.generation)
      throw new Error("Preview request was interrupted");
    const origin = new URL(result.url);
    if (
      !["http:", "https:"].includes(origin.protocol) ||
      !["127.0.0.1", "localhost", "[::1]"].includes(origin.hostname) ||
      !origin.port ||
      origin.username ||
      origin.password
    )
      throw new Error("Unsupported preview origin");
    const isolated = this.isolated;
    await isolated.clearStorageData();
    await isolated.clearCache();
    await isolated.closeAllConnections();
    if (generation !== this.generation)
      throw new Error("Preview request was interrupted");
    isolated.webRequest.onBeforeRequest((details, callback) => {
      let allowed = false;
      try {
        const url = new URL(details.url);
        allowed = url.origin === origin.origin;
      } catch {
        /* Reject malformed and non-network URLs. */
      }
      callback({ cancel: !allowed });
    });
    const view = new WebContentsView({
      webPreferences: {
        session: isolated,
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: true,
        webSecurity: true,
        allowRunningInsecureContent: false,
      },
    });
    this.view = view;
    this.run = value.session_id;
    view.webContents.on("before-input-event", (event, input) => {
      if (input.key === "Escape") {
        event.preventDefault();
        this.close();
        this.window.webContents.focus();
      }
    });
    view.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    view.webContents.on("will-navigate", (event, url) => {
      if (new URL(url).origin !== origin.origin) event.preventDefault();
    });
    view.webContents.on("will-redirect", (event, url) => {
      if (new URL(url).origin !== origin.origin) event.preventDefault();
    });
    view.webContents.on("will-attach-webview", (event) =>
      event.preventDefault(),
    );
    view.webContents.on("render-process-gone", () => this.close());
    this.window.contentView.addChildView(view);
    view.setBounds(bounds);
    try {
      await view.webContents.loadURL(result.url);
    } catch (error) {
      if (this.view === view) this.close();
      throw error;
    }
  }
}
