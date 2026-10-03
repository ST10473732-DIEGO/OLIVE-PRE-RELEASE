; OLIVE additions to electron-builder's per-user NSIS installer (OLIVE-Setup-<version>.exe).
;
; - The Start Menu entry is created by electron-builder (createStartMenuShortcut).
; - The desktop shortcut is optional: the interactive installer asks once on a fresh
;   install; silent installs and updates never add one.
; - Uninstall removes the installed application files ($INSTDIR) and the shortcuts only.
;   OLIVE user data (%USERPROFILE%\.olive or a configured profile), runtimes and models
;   (%LOCALAPPDATA%\OLIVE) are outside $INSTDIR and are never deleted automatically.

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
