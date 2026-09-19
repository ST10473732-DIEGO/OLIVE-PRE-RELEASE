@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo OLIVE is not set up yet. Run setup_windows.bat first.
  exit /b 1
)
if not exist desktop\node_modules\.bin\electron.cmd (
  echo OLIVE desktop dependencies are missing. Run npm ci in desktop first.
  exit /b 1
)
if not exist desktop\out\electron\main.cjs (
  echo OLIVE desktop is not built. Run npm run build in desktop first.
  exit /b 1
)
call desktop\node_modules\.bin\electron.cmd desktop
endlocal
