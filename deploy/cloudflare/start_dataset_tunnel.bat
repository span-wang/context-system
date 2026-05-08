@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "CLOUDFLARED_EXE=%SCRIPT_DIR%cloudflared.exe"
if exist "%SCRIPT_DIR%cloudflared_run.exe" set "CLOUDFLARED_EXE=%SCRIPT_DIR%cloudflared_run.exe"
set "CONFIG_FILE=%SCRIPT_DIR%config.dataset.yml"

if not exist "%CLOUDFLARED_EXE%" (
  echo [ERROR] Missing cloudflared executable in %SCRIPT_DIR%
  exit /b 1
)

if not exist "%CONFIG_FILE%" (
  echo [ERROR] Missing config.dataset.yml in %SCRIPT_DIR%
  exit /b 1
)

echo Starting dataset Cloudflare Tunnel using %CONFIG_FILE%
"%CLOUDFLARED_EXE%" tunnel --config "%CONFIG_FILE%" --protocol http2 run
