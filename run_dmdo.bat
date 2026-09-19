@echo off
rem Compatibility command: OLIVE was formerly DMDO.
call "%~dp0run_olive.bat" %*
exit /b %errorlevel%
