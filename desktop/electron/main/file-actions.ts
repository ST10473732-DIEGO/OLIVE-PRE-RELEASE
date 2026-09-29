import { BrowserWindow, dialog, shell } from "electron";
import { writeFile } from "node:fs/promises";
import { fileActionSchema } from "../file-actions";
import type { Backend } from "./backend";

export async function fileAction(
  window: BrowserWindow,
  backend: Backend,
  input: unknown,
) {
  const value = fileActionSchema.parse(input);
  if(value.action === 'connect-file-select') {
    const chosen = await dialog.showOpenDialog(window, {title:'Select one file to send', properties:['openFile']});
    if(chosen.canceled || chosen.filePaths.length !== 1) return null;
    return backend.request('connect.file_prepare', {device_id:value.device_id,path:chosen.filePaths[0]});
  }
  if(value.action === 'connect-file-save') {
    const chosen = await dialog.showSaveDialog(window, {title:'Save received file to a new file',defaultPath:'OLIVE-received-file'});
    if(chosen.canceled || !chosen.filePath) return null;
    return backend.request('connect.file_export', {transfer_id:value.transfer_id,path:chosen.filePath});
  }
  if(value.action==='media-import') {
    const chosen=await dialog.showOpenDialog(window,{title:'Preserve an original image for REIMAGINE',properties:['openFile'],filters:[{name:'Raster image',extensions:['png','jpg','jpeg','webp','bmp']}]});
    if(chosen.canceled||chosen.filePaths.length!==1)return null;
    return backend.request('media.import',{path:chosen.filePaths[0]});
  }
  if(value.action==='media-export') {
    // Generated Chat media keeps its own file name and type; legacy edits default to PNG.
    const file=await backend.request('media.artifact_file',{artifact_id:value.artifact_id}).catch(()=>null) as {filename?:string}|null;
    const chosen=await dialog.showSaveDialog(window,{title:'Export a new media artifact',defaultPath:file?.filename||'OLIVE-image.png'});
    if(chosen.canceled||!chosen.filePath)return null;
    return backend.request('media.export',{artifact_id:value.artifact_id,path:chosen.filePath});
  }
  if(value.action==='media-open') {
    // Opens a verified generated image/audio/video in the system viewer. It is
    // data only: OLIVE grants it no permission and never executes it.
    const file=await backend.request('media.artifact_file',{artifact_id:value.artifact_id}) as {path:string};
    const failure=await shell.openPath(file.path);
    if(failure)throw new Error('The system could not open this media file.');
    return {opened:true};
  }
  if(value.action === "mail-google-client") {
    const chosen=await dialog.showOpenDialog(window,{title:"Import registered Google Desktop app client",properties:["openFile"],filters:[{name:"Google desktop client",extensions:["json"]}]});
    if(chosen.canceled || chosen.filePaths.length!==1)return null;
    return backend.request("mail.google_import",{path:chosen.filePaths[0]});
  }
  const { action } = value;
  if(value.action === "mail-import" || value.action === "mail-attach") {
    const chosen=await dialog.showOpenDialog(window,{title:value.action==="mail-import"?"Import local EML":"Attach a snapshot of this file",properties:["openFile"],...(value.action==="mail-import"?{filters:[{name:"Email message",extensions:["eml"]}]}:{})});
    if(chosen.canceled || chosen.filePaths.length!==1)return null;
    return value.action==="mail-import" ? backend.request("mail.import_preview",{path:chosen.filePaths[0]}) : backend.request("mail.attach",{record_id:value.record_id,revision:value.revision,path:chosen.filePaths[0]});
  }
  if(value.action === "mail-export" || value.action === "mail-save-attachment") {
    const chosen=await dialog.showSaveDialog(window,{title:"Export readable personal mail content",defaultPath:value.action==="mail-export"?"OLIVE-message.eml":"OLIVE-attachment"});
    if(chosen.canceled || !chosen.filePath)return null;
    return value.action==="mail-export" ? backend.request("mail.export",{record_id:value.record_id,path:chosen.filePath}) : backend.request("mail.save_attachment",{record_id:value.record_id,attachment_id:value.attachment_id,path:chosen.filePath});
  }
  if(value.action === "personal-import" || value.action === "profile-avatar") {
    const extensions=value.action === "profile-avatar" ? ["png","jpg","jpeg"] : [value.format];
    const chosen=await dialog.showOpenDialog(window,{title:"Choose local personal data",properties:["openFile"],filters:[{name:"Local file",extensions}]});
    if(chosen.canceled || chosen.filePaths.length!==1)return null;
    return value.action === "profile-avatar" ? backend.request("profile.avatar",{path:chosen.filePaths[0]}) :
      backend.request("personal.import_preview",{path:chosen.filePaths[0],kind:value.kind,format:value.format,...(value.calendar_id?{calendar_id:value.calendar_id}:{})});
  }
  if(value.action === "personal-export") {
    const chosen=await dialog.showSaveDialog(window,{title:"Export local personal data",defaultPath:`OLIVE-${value.kind}.${value.format}`,filters:[{name:"Local export",extensions:[value.format]}]});
    if(chosen.canceled || !chosen.filePath)return null;
    return backend.request("personal.export",{path:chosen.filePath,kind:value.kind,format:value.format});
  }
  if(value.action === "notes-export") {
    // Only the chosen path crosses to the backend; note text never passes through here.
    const base=Array.from(value.name||"OLIVE note").filter(c=>c.charCodeAt(0)>=32&&!'\\/:*?"<>|'.includes(c)).join("").trim().slice(0,80)||"OLIVE note";
    const chosen=await dialog.showSaveDialog(window,{title:"Export note",defaultPath:`${base}.${value.format}`,filters:[{name:value.format==="md"?"Markdown":"Plain text",extensions:[value.format]}]});
    if(chosen.canceled || !chosen.filePath)return null;
    return backend.request("notes.export",{note_id:value.note_id,path:chosen.filePath,format:value.format});
  }
  if(value.action === "notes-import") {
    const chosen=await dialog.showOpenDialog(window,{title:"Import a text file as a note",properties:["openFile"],filters:[{name:"Text",extensions:["txt","md","markdown","text"]}]});
    if(chosen.canceled || chosen.filePaths.length!==1)return null;
    return backend.request("notes.import",{path:chosen.filePaths[0]});
  }
  if(value.action === "desktop-launch") {
    const chosen = await dialog.showOpenDialog(window, {
      title:"Choose local code to review and launch",
      properties:["openFile"],
      filters:[{name:value.kind === "python" ? "Python script" : "Application", extensions:[value.kind === "python" ? "py" : "exe"]}],
    });
    if(chosen.canceled || chosen.filePaths.length !== 1) return null;
    return backend.request("desktop.launch_local",{path:chosen.filePaths[0],kind:value.kind});
  }
  if (
    value.action === "export-download" ||
    value.action === "desktop-export-download"
  ) {
    const selected = await dialog.showSaveDialog(window, {
      title: "Export quarantined download to a new file",
      defaultPath: "OLIVE-download.bin",
    });
    if (selected.canceled || !selected.filePath) return null;
    return backend.request(
      value.action === "desktop-export-download"
        ? "desktop.save_download"
        : "research.export_download",
      {
        download_id: value.download_id,
        destination: selected.filePath,
      },
    );
  }
  if (
    ["backup", "export-memory", "export-chat", "diagnostics"].includes(action)
  ) {
    const selected = await dialog.showSaveDialog(window, {
      title: action === "backup" ? "Back up OLIVE" : "Export local data",
      defaultPath:
        action === "backup"
          ? "OLIVE-backup.zip"
          : action === "export-chat"
            ? "OLIVE-chat.md"
            : `OLIVE-${action}.json`,
      filters:
        action === "backup"
          ? [{ name: "OLIVE backup", extensions: ["zip"] }]
          : [
              {
                name: "Local export",
                extensions:
                  action === "export-chat" ? ["md", "json"] : ["json"],
              },
            ],
    });
    if (selected.canceled || !selected.filePath) return null;
    if (action === "backup")
      return backend.request("data.backup", { path: selected.filePath });
    if (value.action === "diagnostics") {
      const data = await backend.request("data.diagnostics", {
        chat_id: value.chat_id,
      });
      await writeFile(selected.filePath, JSON.stringify(data, null, 2), "utf8");
      return "Diagnostics exported";
    }
    return backend.request("data.export", {
      path: selected.filePath,
      kind: action === "export-memory" ? "memory" : "chat",
      ...(value.action === "export-chat" ? { chat_id: value.chat_id } : {}),
    });
  }
  const selected = await dialog.showOpenDialog(window, {
    title:
      action === "restore"
        ? "Choose a OLIVE backup to restore"
        : action === "workspace"
          ? "Approve a workspace folder"
          : action === "ocr"
            ? "Choose the OCR executable"
            : "Choose local source files",
    properties:
      action === "workspace"
        ? ["openDirectory"]
        : action === "attach"
          ? ["openFile", "multiSelections"]
          : ["openFile"],
    ...(action === "restore"
      ? { filters: [{ name: "OLIVE backup", extensions: ["zip"] }] }
      : {}),
  });
  if (selected.canceled || !selected.filePaths.length) return null;
  const path = selected.filePaths[0];
  switch (value.action) {
    case "browser-upload":
      return backend.request("desktop.browser_upload", {
        target_id: value.target_id,
        path,
      });
    case "attach":
      if (selected.filePaths.length > 30)
        throw new Error("Select at most 30 files at a time");
      return backend.request("knowledge.attach", {
        chat_id: value.chat_id,
        paths: selected.filePaths,
        permanent: value.permanent || false,
      });
    case "relink":
      return backend.request("knowledge.relink", {
        chat_id: value.chat_id,
        document_id: value.document_id,
        path,
      });
    case "workspace":
      return backend.request("data.create_workspace", {
        path,
        title: value.title,
        trust_level: value.trust_level || "approved",
        ...(value.project_id ? { project_id: value.project_id } : {}),
      });
    case "ocr":
      return path;
    case "restore": {
      const response = await dialog.showMessageBox(window, {
        type: "warning",
        message: "Restore this OLIVE backup?",
        detail: `${path}\nA safety backup is made first. Stop active work before restoring. Restart OLIVE afterwards.`,
        buttons: ["Cancel", "Restore"],
        defaultId: 0,
        cancelId: 0,
      });
      return response.response === 1
        ? backend.request("data.restore", { path, confirmed: true })
        : null;
    }
  }
}
