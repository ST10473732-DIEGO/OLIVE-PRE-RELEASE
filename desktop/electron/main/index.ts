import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  protocol,
  session,
  shell,
  globalShortcut,
  Tray,
  Menu,
} from "electron";
import { z } from "zod";
import path from "node:path";
import { readFile } from "node:fs/promises";
import { identity, normalizeEnvironment, resolveProfile } from "../identity";
import { Preview } from "./preview";
import { OliveBrowser } from "./browser";
import { Backend } from "./backend";
import { backendPython, iconName } from "../platform";
import { validateCall } from "../contracts";
import { fileAction } from "./file-actions";
import { nativeNotifications } from './notifications';

const root = app.isPackaged
  ? path.join(process.resourcesPath, "backend")
  : path.resolve(__dirname, "../../..");
normalizeEnvironment(process.env);
const profile = resolveProfile(process.env);
app.setName(identity.name);
app.setPath("userData", path.join(profile, identity.shell_directory));
app.setPath("sessionData", path.join(profile, identity.shell_directory));
app.setAppUserModelId(identity.app_id);
protocol.registerSchemesAsPrivileged([
  {
    scheme: identity.renderer_scheme,
    privileges: { standard: true, secure: true, supportFetchAPI: true },
  },
]);
let window: BrowserWindow;
let backend: Backend;
let controlTray: Tray | undefined;
let quitting = false;
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", () => {
    window?.restore();
    window?.focus();
  });
  void app.whenReady().then(async () => {
    const assets = app.isPackaged
      ? path.join(app.getAppPath(), "out/renderer")
      : path.join(root, "desktop/out/renderer");
    protocol.handle(identity.renderer_scheme, async (request) => {
      const url = new URL(request.url);
      if (url.host !== "app" || request.method !== "GET")
        return new Response("", { status: 403 });
      let relative: string;
      try {
        relative =
          decodeURIComponent(url.pathname).replace(/^\//, "") || "index.html";
      } catch {
        return new Response("", { status: 400 });
      }
      const file = path.resolve(assets, relative);
      const within = path.relative(assets, file);
      if (
        within.startsWith("..") ||
        path.isAbsolute(within) ||
        relative.includes("\\")
      )
        return new Response("", { status: 403 });
      const types: Record<string, string> = {
        ".html": "text/html",
        ".js": "text/javascript",
        ".css": "text/css",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ttf": "font/ttf",
        ".woff2": "font/woff2",
      };
      try {
        return new Response(await readFile(file), {
          headers: {
            "Content-Type":
              types[path.extname(file)] || "application/octet-stream",
            "Content-Security-Policy":
              "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; worker-src 'self'; connect-src 'none'; frame-src 'self'; base-uri 'none'; form-action 'none'",
          },
        });
      } catch {
        return new Response("", { status: 404 });
      }
    });
    session.defaultSession.setPermissionRequestHandler(
      (_contents, _permission, callback) => callback(false),
    );
    session.defaultSession.setPermissionCheckHandler(() => false);
    backend = new Backend(
      backendPython(root, app.isPackaged, process.env),
      root,
      profile,
    );
    window = new BrowserWindow({
      width: 1440,
      height: 920,
      minWidth: 640,
      minHeight: 480,
      backgroundColor: "#090d14",
      title: identity.name,
      icon: app.isPackaged
        ? path.join(process.resourcesPath, iconName())
        : path.join(root, "assets/branding", iconName()),
      autoHideMenuBar: true,
      webPreferences: {
        preload: path.join(__dirname, "preload.cjs"),
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: true,
        webSecurity: true,
      },
    });
    // Presentation-only native visibility also covers automation/occlusion modes
    // where Chromium's document visibility can remain visible when minimized.
    const publishVisibility = () => {
      if (!window.isDestroyed())
        window.webContents.send(
          "olive:visibility",
          window.isVisible() && !window.isMinimized(),
        );
    };
    window.on("show", publishVisibility);
    window.on("hide", publishVisibility);
    window.on("minimize", publishVisibility);
    window.on("restore", publishVisibility);
    window.webContents.on("did-finish-load", publishVisibility);
    const preview = new Preview(window, backend);
    // One approval surface for every outward link, whether from Chat or OLIVE GO.
    const openExternalLink = async (target: unknown) => {
      if (typeof target !== "string" || target.length > 4096)
        throw new Error("Invalid link");
      const url = new URL(target);
      if (
        !["https:", "http:"].includes(url.protocol) ||
        url.username ||
        url.password
      )
        throw new Error("Unsupported link");
      const answer = await dialog.showMessageBox(window, {
        message: "Open this link in your browser?",
        detail: url.href,
        buttons: ["Cancel", "Open"],
        defaultId: 0,
        cancelId: 0,
      });
      if (answer.response === 1) await shell.openExternal(url.href);
    };
    const notify = nativeNotifications(profile, path.join(root, 'assets/branding/olive-256.png'), () => {
      if (!window.isDestroyed()) window.webContents.send('olive:event', {v: 1, kind: 'event', seq: 0,
        topic: 'native.notification_failure', data: {}});
    });
    const browser = new OliveBrowser(window, backend, openExternalLink, notify);
    function trusted(event: Electron.IpcMainInvokeEvent) {
      if (
        event.sender !== window.webContents ||
        event.senderFrame !== window.webContents.mainFrame ||
        event.senderFrame.url !== "dmdo://app/index.html"
      )
        throw new Error("Untrusted IPC sender");
    }
    ipcMain.handle("olive:preview", (event, input: unknown) => {
      trusted(event);
      return preview.action(input);
    });
    ipcMain.handle('olive:browser', (event, input: unknown) => {
      trusted(event);
      return browser.action(input);
    });
    ipcMain.handle("olive:interface-scale", (event, input: unknown) => {
      trusted(event);
      const factor = z
        .union([z.literal(1), z.literal(1.1), z.literal(1.25), z.literal(1.5)])
        .parse(input);
      window.webContents.setZoomFactor(factor);
      return factor;
    });
    ipcMain.handle("olive:call", async (event, input: unknown) => {
      trusted(event);
      const r = validateCall(input);
      if (r.method === "mail.google_begin") {
        const result = await backend.request(r.method, r.args, r.id) as {url: string; state: string};
        const target = new URL(result.url);
        if (target.protocol !== "https:" || target.host !== "accounts.google.com" || target.pathname !== "/o/oauth2/v2/auth" || target.username || target.password) {
          await backend.request("mail.google_cancel", {});
          throw new Error("Invalid Google authorization destination");
        }
        try { await shell.openExternal(target.href); }
        catch { await backend.request("mail.google_cancel", {}); throw new Error("Could not open the system browser for Google authorization"); }
        return {state: result.state};
      }
      return backend.request(r.method, r.args, r.id);
    });
    ipcMain.handle("olive:dropped-files", (event, input: unknown) => {
      trusted(event);
      const value = z
        .object({
          chat_id: z.string().min(1).max(4096),
          paths: z
            .array(
              z
                .string()
                .min(1)
                .max(4096)
                .refine(
                  (value) => path.isAbsolute(value) && !value.includes("\0"),
                ),
            )
            .min(1)
            .max(32),
        })
        .strict()
        .parse(input);
      return backend.request("knowledge.attach", {
        ...value,
        permanent: false,
      });
    });
    ipcMain.handle("olive:workspace", async (event) => {
      trusted(event);
      const selected = await dialog.showOpenDialog(window, {
        title: "Open an approved workspace",
        properties: ["openDirectory"],
      });
      if (selected.canceled || selected.filePaths.length !== 1) return null;
      return backend.request("workspace.open", { path: selected.filePaths[0] });
    });
    // Returns a chosen directory only. It creates nothing and approves nothing;
    // Python still validates the path before any project is written there.
    ipcMain.handle("olive:choose-directory", async (event) => {
      trusted(event);
      const selected = await dialog.showOpenDialog(window, {
        title: "Choose where to create the project",
        properties: ["openDirectory", "createDirectory"],
      });
      if (selected.canceled || selected.filePaths.length !== 1) return null;
      return selected.filePaths[0];
    });
    ipcMain.handle("olive:file-action", (event, input: unknown) => {
      trusted(event);
      return fileAction(window, backend, input);
    });
    ipcMain.handle("olive:stop-control", (event) => {
      trusted(event);
      backend.stopControl();
    });
    ipcMain.handle("olive:external", async (event, target: unknown) => {
      trusted(event);
      await openExternalLink(target);
    });
    backend.on("event", (value) => {
      notify(value.topic, value.data || {});
      if (!window.isDestroyed()) window.webContents.send("olive:event", value);
    });
    backend.on("lost", () => {
      if (!window.isDestroyed())
        window.webContents.send("olive:event", {
          v: 1,
          kind: "event",
          seq: 0,
          topic: "runtime.lost",
          data: { message: "Python disconnected. No actions were replayed." },
        });
    });
    window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    window.webContents.on("will-navigate", (event) => event.preventDefault());
    window.webContents.on("will-attach-webview", (event) =>
      event.preventDefault(),
    );
    window.webContents.on("render-process-gone", () => backend.stopControl());
    window.on("unresponsive", () => backend.stopControl());
    let closeApproved = false;
    window.on("close", (event) => {
      if (closeApproved || quitting) return;
      event.preventDefault();
      backend.stopControl();
      void backend
        .request("runtime.snapshot", {})
        .then(async (value) => {
          const snapshot = value as { buffers: unknown[] };
          if (snapshot.buffers.length) {
            const answer = await dialog.showMessageBox(window, {
              message: "Studio has unsaved changes.",
              detail:
                "Return to Studio to save or compare your edits. Closing discards unsaved editor buffers.",
              buttons: ["Keep working", "Discard unsaved changes and close"],
              defaultId: 0,
              cancelId: 0,
            });
            if (answer.response !== 1) return;
          }
          closeApproved = true;
          window.close();
        })
        .catch(async () => {
          const answer = await dialog.showMessageBox(window, {
            message: "The Python runtime is unavailable.",
            detail:
              "Unsaved changes may still be visible in Studio. Copy them before closing.",
            buttons: ["Keep open", "Close"],
            defaultId: 0,
            cancelId: 0,
          });
          if (answer.response === 1) {
            closeApproved = true;
            window.close();
          }
        });
    });
    globalShortcut.register("CommandOrControl+Alt+Escape", () =>
      backend.stopControl(),
    );
    if (process.platform === "linux") {
      controlTray = new Tray(app.isPackaged
        ? path.join(process.resourcesPath, iconName())
        : path.join(root, "assets/branding", iconName()));
      controlTray.setToolTip("OLIVE");
      controlTray.setContextMenu(Menu.buildFromTemplate([
        {label: "Open OLIVE", click: () => {window.show(); window.focus();}},
        {label: "Stop desktop task", click: () => backend.stopControl()},
      ]));
    }
    await window.loadURL("dmdo://app/index.html");
  });
  app.on("window-all-closed", () => app.quit());
  if (process.platform !== "win32") {
    process.on("SIGTERM", () => app.quit());
    process.on("SIGINT", () => app.quit());
  }
  app.on("before-quit", (event) => {
    if (quitting || !backend) return;
    event.preventDefault();
    quitting = true;
    globalShortcut.unregisterAll();
    controlTray?.destroy();
    void backend.close().finally(() => app.quit());
  });
}
