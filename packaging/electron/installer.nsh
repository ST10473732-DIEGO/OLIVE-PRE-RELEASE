; OLIVE additions to electron-builder's per-user NSIS installer (OLIVE-Setup-<version>.exe).
;
; - A fresh install goes to %LOCALAPPDATA%\Programs\OLIVE (the per-user program root).
;   A one-click per-user installer otherwise names that folder after the npm package
;   (olive-desktop); see preInit. An existing install keeps its recorded location.
; - The Start Menu entry is created by electron-builder (createStartMenuShortcut).
; - The desktop shortcut is optional: the interactive installer asks once on a fresh
;   install; silent installs and updates never add one.
; - Uninstall removes the installed application files ($INSTDIR) and the shortcuts only.
;   OLIVE user data (%USERPROFILE%\.olive or a configured profile), runtimes and models
;   (%LOCALAPPDATA%\OLIVE) are outside $INSTDIR and are never deleted automatically.

!macro preInit
  ; electron-builder documents seeding InstallLocation here to change the default folder.
  ; Its per-user setup reads this value first and still honours /D=. Only seeded when
  ; absent, so an update never moves an installed OLIVE; the uninstaller deletes the key.
  !ifndef BUILD_UNINSTALLER
    SetRegView 64
    Push $0
    Push $1
    Push $2
    ReadRegStr $0 HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation
    ${if} $0 == ""
      ; Same per-user program root electron-builder uses: FOLDERID_UserProgramFiles.
      StrCpy $0 "$LOCALAPPDATA\Programs"
      StrCpy $2 0
      System::Call 'SHELL32::SHGetKnownFolderPath(g "{5CD7AEE2-2219-4A67-B85D-6C9CE15660CB}", i 0x00008000, p 0, *p .r2)i.r1'
      ${if} $1 == 0
        System::Call 'KERNEL32::lstrcpynW(w .r0, p r2, i ${NSIS_MAX_STRLEN})p'
      ${endif}
      ${if} $2 != 0
        System::Call 'OLE32::CoTaskMemFree(p r2)'
      ${endif}
      WriteRegStr HKCU "${INSTALL_REGISTRY_KEY}" InstallLocation "$0\${PRODUCT_FILENAME}"
    ${endif}
    Pop $2
    Pop $1
    Pop $0
  !endif
!macroend

!macro customInstall
  ${ifNot} ${isUpdated}
  ${andIfNot} ${Silent}
  ${andIfNot} ${FileExists} "$DESKTOP\${SHORTCUT_NAME}.lnk"
    MessageBox MB_YESNO|MB_ICONQUESTION "Add an OLIVE shortcut to your desktop?" /SD IDNO IDNO oliveNoDesktopShortcut
    CreateShortCut "$DESKTOP\${SHORTCUT_NAME}.lnk" "$appExe" "" "$appExe" 0 "" "" "${APP_DESCRIPTION}"
    ClearErrors
    WinShell::SetLnkAUMI "$DESKTOP\${SHORTCUT_NAME}.lnk" "${APP_ID}"
    oliveNoDesktopShortcut:
  ${endIf}
!macroend

!macro customUnInstall
  ; Only the optional shortcut created above; an update keeps it.
  ${ifNot} ${isUpdated}
    ${if} ${FileExists} "$DESKTOP\${SHORTCUT_NAME}.lnk"
      WinShell::UninstShortcut "$DESKTOP\${SHORTCUT_NAME}.lnk"
      Delete "$DESKTOP\${SHORTCUT_NAME}.lnk"
    ${endIf}
  ${endIf}
!macroend
