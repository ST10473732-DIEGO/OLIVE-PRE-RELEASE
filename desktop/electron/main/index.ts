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
  clipboard,
  nativeImage,
} from "electron";
import { z } from "zod";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, realpathSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { identity, normalizeEnvironment, resolveProfile } from "../identity";
import { Preview } from "./preview";
import { OliveBrowser } from "./browser";
import { Backend } from "./backend";
import { backendArguments, backendEnvironment, backendPython, brandingAsset, enforceSandboxPolicy, findExternalWorkspace, iconName, sandboxPolicy, WORKSPACE_ANCHOR } from "../platform";
import { validateCall } from "../contracts";
import { fileAction } from "./file-actions";
import { mediaId, mediaResponse } from "./media-protocol";
import { nativeNotifications } from './notifications';
import { writeClipboardText } from '../clipboard';

const root = app.isPackaged
  ? path.join(process.resourcesPath, "backend")
  : path.resolve(__dirname, "../../..");
normalizeEnvironment(process.env);
// External-only macOS Preview: Finder launches do not inherit terminal environment.
// Verify the SSD anchor BEFORE allowing Electron or Python to create profile files.
if (process.platform === "darwin" && app.isPackaged) {
  // The workspace is found from where this app lives (its anchor names its own root);
  // nothing about a particular drive or person is built into the app.
  const workspace = findExternalWorkspace(process.execPath);
  if (!workspace) {
    throw new Error("OLIVE macOS Preview must run from inside a verified external SSD workspace (" + WORKSPACE_ANCHOR + ").");
  }
  const { root: externalRoot, volume } = workspace;
  const anchorFile = path.join(externalRoot, WORKSPACE_ANCHOR);
  const profileDir = path.join(externalRoot, "data-private/packaged-preview");
  const anchor = JSON.parse(readFileSync(anchorFile, "utf8")) as {volume_uuid: string; root: string};
  const disk = execFileSync("/usr/sbin/diskutil", ["info", volume], {encoding: "utf8", timeout: 12000});
  if (anchor.root !== externalRoot ||
      !/^\s*Device Location:\s*External\s*$/m.test(disk) ||
      !disk.includes("Volume UUID:") ||
      !new RegExp("^\\s*Volume UUID:\\s*" + anchor.volume_uuid + "\\s*$", "m").test(disk)) {
    throw new Error("OLIVE macOS external SSD identity does not match the migration anchor.");
  }
  const parent = realpathSync(path.dirname(profileDir));
  if (parent !== path.join(externalRoot, "data-private")) {
    throw new Error("OLIVE macOS profile parent unexpectedly resolves outside the SSD.");
  }
  if (!existsSync(profileDir)) mkdirSync(profileDir, {recursive: false, mode: 0o700});
  if (realpathSync(profileDir) !== profileDir) {
    throw new Error("OLIVE macOS profile is not an ordinary external directory.");
  }
  if (process.env.OLIVE_DATA_DIR && realpathSync(process.env.OLIVE_DATA_DIR) !== profileDir) {
    throw new Error("Conflicting OLIVE_DATA_DIR: refusing to redirect private data.");
  }
  process.env.OLIVE_DATA_DIR = profileDir;
  // One verified root for the backend, its media helpers and the Keychain HOME split.
  process.env.OLIVE_MACOS_EXTERNAL_ROOT = externalRoot;
  process.env.OLLAMA_MODELS = path.join(externalRoot, "model-store/ollama");
  process.env.OLLAMA_HOST = "127.0.0.1:11434";
  process.env.OLIVE_OLLAMA_HOST = "http://127.0.0.1:11434";
  process.env.OLIVE_OLLAMA_EXECUTABLE = path.join(externalRoot, "envs/ollama-v0.40.17/ollama");
  process.env.OLIVE_START_OLLAMA = "1";
  process.env.OLLAMA_NO_CLOUD = "1";
  // Two prompt-cache slots: request classification and the chat answer each keep
  // their own cached prompt instead of evicting each other on every message
  // (measured on M1 Max: classification 2.3 s -> 0.75 s, first answer word 0.74 s -> 0.17 s).
  process.env.OLLAMA_NUM_PARALLEL = "2";
  process.env.OLLAMA_MAX_LOADED_MODELS = "2";
  process.env.OLLAMA_KEEP_ALIVE = "1800";
  process.env.OLIVE_MACOS_RETAIN_TWO = "1";
  // Mac Studio Preview models (olive/services/presets.py MACOS_PRESET_PROFILE); every other
  // platform, source run and test keeps the release presets of the 1.0 runtime manifest.
  process.env.OLIVE_MACOS_MODEL_PROFILE = "1";
  process.env.OLIVE_MACOS_PREWARM_NORMAL = "1";
  process.env.OLIVE_RECOVER_PYTHON = "1";
  process.env.OLIVE_CONNECT_START_DIAGNOSTICS = "1";
  process.env.OLLAMA_CONTEXT_LENGTH = "8192";
  // Native media remains fail-closed until its pinned image acceptance receipt passes.
  process.env.OLIVE_ENABLE_NATIVE_MFLUX = "1";
  process.env.OLIVE_ENABLE_NATIVE_KOKORO = "1";
  // Short silent Wan2.1 video is available only after on-device MP4 acceptance.
  process.env.OLIVE_ENABLE_NATIVE_WAN = "1";
  process.env.HOME = path.join(externalRoot, "envs/ollama-home");
  process.env.XDG_CONFIG_HOME = path.join(externalRoot, "envs/ollama-home/.config");
  process.env.HF_HOME = path.join(externalRoot, "cache/hf");
  process.env.XDG_CACHE_HOME = path.join(externalRoot, "cache/xdg");
  process.env.TMPDIR = path.join(externalRoot, "cache/tmp") + "/";
  // Only the packaged Python bridge needs macOS login HOME for Keychain lookup.
  // Ollama child is still anchored to the external SSD using its own HOME.
  process.env.OLIVE_MACOS_KEYCHAIN_LOGIN_HOME = "1";
}
const profile = resolveProfile(process.env);
app.setName(identity.name);

if (process.platform === "linux") {
  app.setDesktopName("olive.desktop");
}

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
    // Fail closed: never run web content unsandboxed because a launcher fell back to --no-sandbox.
    const sandbox = sandboxPolicy({ platform: process.platform, noSandboxSwitch: app.commandLine.hasSwitch("no-sandbox"), env: process.env });
    const refused = enforceSandboxPolicy(sandbox, {
      showError: (title, message) => dialog.showErrorBox(title, message),
      exit: (code) => app.exit(code),
      error: (text) => console.error(text),
      warn: (text) => console.warn(text),
    });
    if (refused) return;
    app.setAccessibilitySupportEnabled(true);
    // A checkout launched via Electron.app otherwise displays Electron's default Dock icon.
    // Use the same OLIVE branding as the signed/packaged macOS application.
    if (process.platform === "darwin" && app.dock) {
      const dockIcon = nativeImage.createFromPath(brandingAsset(iconName(), app.isPackaged, root, process.resourcesPath));
      if (!dockIcon.isEmpty()) app.dock.setIcon(dockIcon);
      else console.warn("OLIVE Dock icon could not be loaded");
    }
    const assets = app.isPackaged
      ? path.join(app.getAppPath(), "out/renderer")
      : path.join(root, "desktop/out/renderer");
    protocol.handle(identity.renderer_scheme, async (request) => {
      const url = new URL(request.url);
      if (url.host !== "app" || request.method !== "GET")
        return new Response("", { status: 403 });
      const artifact = mediaId(url.pathname);
      if (artifact) return mediaResponse(request, artifact, backend);
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
              "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; font-src 'self'; worker-src 'self'; connect-src 'none'; frame-src 'self'; base-uri 'none'; form-action 'none'",
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
      backendArguments(app.isPackaged),
      root,
      backendEnvironment(process.env, {
        packaged: app.isPackaged,
        profile,
        uiProcessId: process.pid,
        executable: process.execPath,
      }),
    );
    window = new BrowserWindow({
      width: 1440,
      height: 920,
      minWidth: 640,
      minHeight: 480,
      backgroundColor: "#060705",
      title: identity.name,
      icon: brandingAsset(iconName(), app.isPackaged, root, process.resourcesPath),
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
    const notify = nativeNotifications(profile, brandingAsset('olive-256.png', app.isPackaged, root, process.resourcesPath), () => {
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
    ipcMain.handle("olive:copy-text", async (event, input: unknown) => {
      trusted(event);
      await writeClipboardText(input, text => clipboard.writeText(text));
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
    if (process.platform === "linux" || process.platform === "darwin") {
      const trayAsset = brandingAsset(iconName(), app.isPackaged, root, process.resourcesPath);
      const trayImage = process.platform === "darwin"
        ? nativeImage.createFromPath(trayAsset).resize({width: 18, height: 18})
        : trayAsset;
      controlTray = new Tray(trayImage);
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
