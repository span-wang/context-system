@echo off
setlocal
cd /d "%~dp0"
set "PS_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS_EXE%" set "PS_EXE=pwsh.exe"
"%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
if errorlevel 1 (
  echo.
  echo Startup failed. Check data\logs for details.
  pause
  exit /b 1
)
echo.
echo Exam Kit is running. Closing this window will not stop the services.
echo To stop them, double click stop.bat or the Chinese-named stop shortcut.
pause
