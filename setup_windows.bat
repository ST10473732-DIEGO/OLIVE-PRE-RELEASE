@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH.
  echo Install Python 3.11 or newer, then run this file again.
  exit /b 1
)

if not exist .venv (
  python -m venv .venv
  if errorlevel 1 exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Setup complete.
echo Make sure Ollama is installed and running, then run run_olive.bat
endlocal
