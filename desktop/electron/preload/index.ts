import { contextBridge, ipcRenderer, webUtils } from "electron";
import type { Method, Arguments } from "../contracts";
import type { FileAction } from "../file-actions";
import type { PreviewAction } from "../preview";
import type { BrowserAction, BrowserState } from '../browser';
// No raw IPC, filesystem, process, database, or secret access is exposed.
contextBridge.exposeInMainWorld("olive", {
  copyText: (text: string): Promise<void> => ipcRenderer.invoke("olive:copy-text", text),
  browser: (input: BrowserAction) => ipcRenderer.invoke('olive:browser', input),
  onBrowserState: (listener: (state: BrowserState) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, state: BrowserState) => listener(state);
    ipcRenderer.on('olive:browser-state', handler);
    return () => ipcRenderer.removeListener('olive:browser-state', handler);
  },
  // Text a person chose to send to Chat from a page's context menu; page content never arrives here on its own.
  onBrowserAsk: (listener: (text: string) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, text: unknown) => { if (typeof text === 'string' && text.length <= 24000) listener(text); };
    ipcRenderer.on('olive:browser-ask', handler);
    return () => ipcRenderer.removeListener('olive:browser-ask', handler);
  },
  setInterfaceScale: (factor: number) =>
    ipcRenderer.invoke("olive:interface-scale", factor),
  attachFiles: (chat_id: string, files: File[]) => {
    if (!Array.isArray(files) || !files.length || files.length > 32)
      throw new Error("Drop between 1 and 32 local files");
    const paths = files.map((file) => webUtils.getPathForFile(file));
    if (paths.some((path) => !path))
      throw new Error("Only files backed by local disk can be attached");
    return ipcRenderer.invoke("olive:dropped-files", { chat_id, paths });
  },
  call: <M extends Method>(method: M, args: Arguments<M>) =>
    ipcRenderer.invoke("olive:call", { id: crypto.randomUUID(), method, args }),
  openWorkspace: () => ipcRenderer.invoke("olive:workspace"),
  chooseDirectory: () => ipcRenderer.invoke("olive:choose-directory"),
  fileAction: (input: FileAction) =>
    ipcRenderer.invoke("olive:file-action", input),
  preview: (input: PreviewAction) => ipcRenderer.invoke("olive:preview", input),
  onPreviewClosed: (listener: () => void) => {
    const handler = () => listener();
    ipcRenderer.on("olive:preview-closed", handler);
    return () => ipcRenderer.removeListener("olive:preview-closed", handler);
  },
  stopControl: () => ipcRenderer.invoke("olive:stop-control"),
  openExternal: (url: string) => ipcRenderer.invoke("olive:external", url),
  subscribe: (listener: (event: unknown) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, value: unknown) =>
      listener(value);
    ipcRenderer.on("olive:event", handler);
    return () => ipcRenderer.removeListener("olive:event", handler);
  },
});

// No capability is exposed: this DOM flag only suspends decorative rendering.
let windowVisible = true;
const applyVisibility = () => {
  if (document.documentElement)
    document.documentElement.dataset.windowVisible = String(windowVisible);
};
const visibility = (_event: Electron.IpcRendererEvent, value: unknown) => {
  if (typeof value !== "boolean") return;
  windowVisible = value;
  applyVisibility();
};
ipcRenderer.on("olive:visibility", visibility);
window.addEventListener("DOMContentLoaded", applyVisibility, { once: true });
window.addEventListener(
  "unload",
  () => ipcRenderer.removeListener("olive:visibility", visibility),
  { once: true },
);
