@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "CLOUDFLARED_EXE=%SCRIPT_DIR%cloudflared.exe"
if exist "%SCRIPT_DIR%cloudflared_run.exe" set "CLOUDFLARED_EXE=%SCRIPT_DIR%cloudflared_run.exe"
set "CONFIG_FILE=%SCRIPT_DIR%config.yml"

if not exist "%CLOUDFLARED_EXE%" (
  echo [ERROR] Missing cloudflared executable in %SCRIPT_DIR%
  exit /b 1
)

if not exist "%CONFIG_FILE%" (
  echo [ERROR] Missing config.yml in %SCRIPT_DIR%
  echo Copy config.named.example.yml to config.yml and fill in your tunnel UUID + credentials-file first.
  exit /b 1
)

echo Starting named Cloudflare Tunnel using %CONFIG_FILE%
echo Recommended routing:
echo   - https://context.panspan.cloud  new platform entrance
echo Keep the original local product ports unchanged and let cloudflared connect to 127.0.0.1:3000.
"%CLOUDFLARED_EXE%" tunnel --config "%CONFIG_FILE%" --protocol http2 run
