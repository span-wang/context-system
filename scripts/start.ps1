param(
  [int]$ApiPort = 8000,
  [int]$WebPort = 3000,
  [switch]$UseLocalMySql,
  [int]$MySqlPort = 3309,
  [string]$MySqlDatabase = "exam_kit_local",
  [switch]$NoInstall,
  [switch]$NoBrowser,
  [switch]$NoTunnel,
  [string]$TunnelConfigPath = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiDir = Join-Path $Root "apps\api"
$WebDir = Join-Path $Root "apps\web"
$DataDir = Join-Path $Root "data"
$CacheDir = Join-Path $DataDir "cache"
$LogDir = Join-Path $DataDir "logs"
$RunDir = Join-Path $DataDir "run"
$VenvDir = Join-Path $ApiDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$PipExe = Join-Path $VenvDir "Scripts\pip.exe"
$PipCacheDir = Join-Path $CacheDir "pip"
$TunnelExe = Join-Path $Root "deploy\cloudflare\cloudflared.exe"
if (-not (Test-Path -LiteralPath $TunnelExe -PathType Leaf)) {
  $TunnelExe = Join-Path $Root "deploy\cloudflare\cloudflared_run.exe"
}
$TunnelConfig = if ($TunnelConfigPath) {
  if ([System.IO.Path]::IsPathRooted($TunnelConfigPath)) {
    $TunnelConfigPath
  } else {
    Join-Path $Root $TunnelConfigPath
  }
} else {
  Join-Path $Root "deploy\cloudflare\config.yml"
}
$LocalMySqlScript = Join-Path $Root "scripts\start-local-mysql.ps1"
$LocalMySqlInfoPath = Join-Path $RunDir "mysql-local-$MySqlPort.json"
$LocalMySqlDbUrl = $null

New-Item -ItemType Directory -Force -Path $CacheDir, $LogDir, $RunDir, $PipCacheDir | Out-Null

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Http([string]$Url) {
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
    return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
  } catch {
    return $false
  }
}

function Wait-Http([string]$Url, [int]$TimeoutSeconds = 45) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-Http $Url) { return $true }
    Start-Sleep -Milliseconds 800
  }
  return $false
}

function Get-ListenProcessId([int]$Port) {
  $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($connection) { return [int]$connection.OwningProcess }
  return $null
}

function Find-FreePort([int]$StartPort) {
  for ($port = $StartPort; $port -lt ($StartPort + 50); $port++) {
    if (-not (Get-ListenProcessId $port)) { return $port }
  }
  throw "No free port found from $StartPort to $($StartPort + 49)."
}

function Get-ProjectNextDevProcesses {
  return @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
      $_.CommandLine -and
      $_.CommandLine.Contains([string]$WebDir) -and
      (
        $_.CommandLine -match "next[\\/]+dist[\\/]+bin[\\/]+next" -or
        $_.CommandLine -match "next[\\/]+dist[\\/]+server[\\/]+lib[\\/]+start-server\.js"
      )
    } | Sort-Object ProcessId | Select-Object -Unique ProcessId, Name, CommandLine
  )
}

function Format-ProcessIds([object[]]$Processes) {
  if (-not $Processes -or $Processes.Count -eq 0) {
    return "none"
  }
  return (($Processes | ForEach-Object { [string]$_.ProcessId }) -join ", ")
}

function Save-Pid([string]$Name, [int]$ProcessId) {
  Set-Content -LiteralPath (Join-Path $RunDir "$Name.pid") -Value $ProcessId -Encoding ascii
}

function Get-TunnelHostnames {
  if (-not (Test-Path -LiteralPath $TunnelConfig -PathType Leaf)) {
    return @()
  }
  $lines = Get-Content -LiteralPath $TunnelConfig -ErrorAction SilentlyContinue
  $hosts = @()
  foreach ($line in $lines) {
    if ($line -match '^\s*-\s+hostname:\s*(.+?)\s*$' -or $line -match '^\s*hostname:\s*(.+?)\s*$') {
      $tunnelHostname = $matches[1].Trim().Trim("'`"")
      if ($tunnelHostname) {
        $hosts += $tunnelHostname
      }
    }
  }
  return @($hosts | Select-Object -Unique)
}

function Start-TunnelIfReady {
  if ($NoTunnel) {
    Write-Host "Tunnel: disabled by switch." -ForegroundColor DarkYellow
    return
  }
  if (-not (Test-Path -LiteralPath $TunnelExe -PathType Leaf)) {
    Write-Host "Tunnel: skipped because cloudflared executable is missing." -ForegroundColor DarkYellow
    return
  }
  if (-not (Test-Path -LiteralPath $TunnelConfig -PathType Leaf)) {
    Write-Host "Tunnel: skipped because tunnel config is missing: $TunnelConfig" -ForegroundColor DarkYellow
    return
  }

  Write-Step "Start Cloudflare named tunnel"
  $tunnelOut = Join-Path $LogDir "tunnel.out.log"
  $tunnelErr = Join-Path $LogDir "tunnel.err.log"
  $tunnelConfigDir = Split-Path -Parent $TunnelConfig
  $tunnelConfigFile = Split-Path -Leaf $TunnelConfig
  $tunnelProc = Start-Process -FilePath $TunnelExe `
    -ArgumentList @("tunnel", "--config", $tunnelConfigFile, "--protocol", "http2", "run") `
    -WorkingDirectory $tunnelConfigDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $tunnelOut `
    -RedirectStandardError $tunnelErr `
    -PassThru
  Save-Pid "tunnel" $tunnelProc.Id
}

function Save-PortInfo([int]$Api, [int]$Web, [string[]]$PublicHosts) {
  $publicUrl = $null
  if ($PublicHosts -and $PublicHosts.Count -gt 0) {
    $publicUrl = "https://$($PublicHosts[0])"
  }
  $json = @{
    api_port = $Api
    web_port = $Web
    api_base = "http://127.0.0.1:$Api"
    web_url = "http://127.0.0.1:$Web"
    public_web_url = $publicUrl
    public_hostnames = @($PublicHosts)
    use_local_mysql = [bool]$UseLocalMySql
    mysql_port = if ($UseLocalMySql) { $MySqlPort } else { $null }
    mysql_db_url = if ($UseLocalMySql) { $LocalMySqlDbUrl } else { $null }
    started_at = (Get-Date).ToString("s")
  } | ConvertTo-Json
  Set-Content -LiteralPath (Join-Path $RunDir "ports.json") -Value $json -Encoding utf8
}

function Install-ApiDeps {
  if ($NoInstall) { return }
  if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Step "Create Python virtual environment"
    $systemPython = (Get-Command python -ErrorAction Stop).Source
    & $systemPython -m venv $VenvDir
  }
  $stamp = Join-Path $VenvDir ".requirements.stamp"
  $requirements = Join-Path $ApiDir "requirements.txt"
  $needsInstall = -not (Test-Path -LiteralPath $stamp)
  if (-not $needsInstall) {
    $needsInstall = (Get-Item -LiteralPath $requirements).LastWriteTime -gt (Get-Item -LiteralPath $stamp).LastWriteTime
  }
  if ($needsInstall) {
    Write-Step "Install API dependencies"
    $oldPipCacheDir = $env:PIP_CACHE_DIR
    $oldPipDisableVersionCheck = $env:PIP_DISABLE_PIP_VERSION_CHECK
    $env:PIP_CACHE_DIR = $PipCacheDir
    $env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
    try {
      & $PythonExe -m pip install --cache-dir $PipCacheDir --timeout 120 --retries 5 -r $requirements
      if ($LASTEXITCODE -ne 0) {
        throw "API dependency installation failed. pip cache dir: $PipCacheDir"
      }
    } finally {
      $env:PIP_CACHE_DIR = $oldPipCacheDir
      $env:PIP_DISABLE_PIP_VERSION_CHECK = $oldPipDisableVersionCheck
    }
    Set-Content -LiteralPath $stamp -Value (Get-Date).ToString("s") -Encoding ascii
  }
}

function Install-WebDeps {
  if ($NoInstall) { return }
  $nodeModules = Join-Path $WebDir "node_modules"
  $packageLock = Join-Path $WebDir "package-lock.json"
  $needsInstall = -not (Test-Path -LiteralPath $nodeModules)
  if (-not $needsInstall -and (Test-Path -LiteralPath $packageLock)) {
    $needsInstall = (Get-Item -LiteralPath $packageLock).LastWriteTime -gt (Get-Item -LiteralPath $nodeModules).LastWriteTime
  }
  if ($needsInstall) {
    Write-Step "Install web dependencies"
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    Push-Location $WebDir
    try {
      & $npm install
      if ($LASTEXITCODE -ne 0) { throw "Web dependency installation failed." }
    } finally {
      Pop-Location
    }
  }
}

function Start-LocalMySqlIfRequested {
  if (-not $UseLocalMySql) { return }
  if (-not (Test-Path -LiteralPath $LocalMySqlScript -PathType Leaf)) {
    throw "Local MySQL script not found: $LocalMySqlScript"
  }

  Write-Step "Start local MySQL: 127.0.0.1:$MySqlPort / $MySqlDatabase"
  & $LocalMySqlScript -Port $MySqlPort -Database $MySqlDatabase
  if ($LASTEXITCODE -ne 0) {
    throw "Local MySQL startup failed."
  }
  if (-not (Test-Path -LiteralPath $LocalMySqlInfoPath)) {
    throw "Local MySQL info file not found: $LocalMySqlInfoPath"
  }
  $mysqlInfo = Get-Content -Raw -LiteralPath $LocalMySqlInfoPath | ConvertFrom-Json
  $script:LocalMySqlDbUrl = [string]$mysqlInfo.db_url
  if (-not $LocalMySqlDbUrl) {
    throw "Local MySQL info file does not contain db_url."
  }
}

Write-Step "Check dependencies"
Get-Command node -ErrorAction Stop | Out-Null
Get-Command npm.cmd -ErrorAction Stop | Out-Null
Install-ApiDeps
Install-WebDeps

if (-not (Test-Path -LiteralPath $PythonExe)) {
  $PythonExe = (Get-Command python -ErrorAction Stop).Source
}

$ApiHealth = "http://127.0.0.1:$ApiPort/api/system/healthz"
if (Get-ListenProcessId $ApiPort) {
  if ((-not $UseLocalMySql) -and (Test-Http $ApiHealth)) {
    Write-Step "API already running on port $ApiPort; reusing it"
  } else {
    $ApiPort = Find-FreePort ($ApiPort + 1)
    Write-Step "API port is occupied; using port $ApiPort"
  }
}

$ApiHealth = "http://127.0.0.1:$ApiPort/api/system/healthz"
$WebUrl = "http://127.0.0.1:$WebPort/generate"
$ReuseExistingWeb = $false
$ProjectNextDevProcesses = Get-ProjectNextDevProcesses
if ($UseLocalMySql -and $ProjectNextDevProcesses.Count -gt 0) {
  $existingPids = Format-ProcessIds $ProjectNextDevProcesses
  $webPortOccupied = [bool](Get-ListenProcessId $WebPort)
  $webHealthy = Test-Http $WebUrl
  if (($ApiPort -eq 8000) -and $webPortOccupied -and $webHealthy) {
    Write-Host "UseLocalMySql: detected existing apps\\web next dev process(es): $existingPids" -ForegroundColor DarkYellow
    Write-Host "UseLocalMySql: reusing the existing Web on port $WebPort because this repository should not run a second Next.js dev server." -ForegroundColor DarkYellow
    Write-Host "UseLocalMySql: if you need a fresh Web bound to a new API chain, stop the existing Web first with scripts\\stop.ps1 -AlsoKnownPorts and rerun." -ForegroundColor DarkYellow
    $ReuseExistingWeb = $true
  } else {
    $conflictReason = if ($ApiPort -ne 8000) {
      "API port moved to $ApiPort, so the existing Web would not point at the new API chain."
    } elseif (-not $webPortOccupied) {
      "A project Next.js process exists, but the requested Web port $WebPort is not reusable."
    } else {
      "The existing Web on port $WebPort is not responding, so it cannot be safely reused."
    }
    throw "UseLocalMySql detected existing apps\\web next dev process(es): $existingPids. This repository should not run a second Next.js dev server. $conflictReason Stop the existing Web first with scripts\\stop.ps1 -AlsoKnownPorts, or reuse the current 3000/8000 chain before starting a new local-MySQL pair."
  }
}

Start-LocalMySqlIfRequested

$TunnelHosts = Get-TunnelHostnames
$PublicWebUrl = if ($TunnelHosts.Count -gt 0) { "https://$($TunnelHosts[0])" } else { $null }

if (-not (Test-Http $ApiHealth)) {
  Write-Step "Start API: $ApiHealth"
  $apiOut = Join-Path $LogDir "api.out.log"
  $apiErr = Join-Path $LogDir "api.err.log"
  $oldDbUrl = $env:DB_URL
  if ($UseLocalMySql) {
    $env:DB_URL = $LocalMySqlDbUrl
  }
  try {
    $apiProc = Start-Process -FilePath $PythonExe `
      -ArgumentList @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
      -WorkingDirectory $ApiDir `
      -WindowStyle Hidden `
      -RedirectStandardOutput $apiOut `
      -RedirectStandardError $apiErr `
      -PassThru
    Save-Pid "api" $apiProc.Id
    if (-not (Wait-Http $ApiHealth 60)) {
      throw "API startup timed out. Check log: $apiErr"
    }
  } finally {
    $env:DB_URL = $oldDbUrl
  }
}

if (Get-ListenProcessId $WebPort) {
  if ($ReuseExistingWeb -or ((-not $UseLocalMySql) -and (Test-Http $WebUrl))) {
    Write-Step "Web already running on port $WebPort; reusing it"
  } else {
    $WebPort = Find-FreePort ($WebPort + 1)
    Write-Step "Web port is occupied; using port $WebPort"
  }
}

$WebUrl = "http://127.0.0.1:$WebPort/generate"
if ((-not $ReuseExistingWeb) -and (-not (Test-Http $WebUrl))) {
  Write-Step "Start web: http://127.0.0.1:$WebPort"
  $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
  $oldApiProxyTarget = $env:API_PROXY_TARGET
  $oldLayoutProxyTarget = $env:LAYOUT_PROXY_TARGET
  $oldLayoutPublicUrl = $env:NEXT_PUBLIC_LAYOUT_PUBLIC_URL
  $oldAllowedDevOrigins = $env:NEXT_ALLOWED_DEV_ORIGINS
  $oldPublicWebOrigin = $env:PUBLIC_WEB_ORIGIN
  $oldPublicWebUrl = $env:PUBLIC_WEB_URL
  $env:API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
  if (-not $env:LAYOUT_PROXY_TARGET) {
    $env:LAYOUT_PROXY_TARGET = "https://xhs.panspan.cloud"
  }
  if (-not $env:NEXT_PUBLIC_LAYOUT_PUBLIC_URL) {
    $env:NEXT_PUBLIC_LAYOUT_PUBLIC_URL = "https://xhs.panspan.cloud"
  }
  if ($TunnelHosts.Count -gt 0) {
    $env:NEXT_ALLOWED_DEV_ORIGINS = ($TunnelHosts -join ",")
    $env:PUBLIC_WEB_ORIGIN = $TunnelHosts[0]
    $env:PUBLIC_WEB_URL = $PublicWebUrl
  }
  try {
    $webOut = Join-Path $LogDir "web.out.log"
    $webErr = Join-Path $LogDir "web.err.log"
    $webProc = Start-Process -FilePath $npm `
      -ArgumentList @("run", "dev", "--", "--hostname", "127.0.0.1", "--port", "$WebPort") `
      -WorkingDirectory $WebDir `
      -WindowStyle Hidden `
      -RedirectStandardOutput $webOut `
      -RedirectStandardError $webErr `
      -PassThru
    Save-Pid "web" $webProc.Id
  } finally {
    $env:API_PROXY_TARGET = $oldApiProxyTarget
    $env:LAYOUT_PROXY_TARGET = $oldLayoutProxyTarget
    $env:NEXT_PUBLIC_LAYOUT_PUBLIC_URL = $oldLayoutPublicUrl
    $env:NEXT_ALLOWED_DEV_ORIGINS = $oldAllowedDevOrigins
    $env:PUBLIC_WEB_ORIGIN = $oldPublicWebOrigin
    $env:PUBLIC_WEB_URL = $oldPublicWebUrl
  }
  if (-not (Wait-Http $WebUrl 90)) {
    throw "Web startup timed out. Check log: $webErr"
  }
}

Save-PortInfo $ApiPort $WebPort $TunnelHosts
Start-TunnelIfReady

Write-Host ""
Write-Host "Exam Kit is ready." -ForegroundColor Green
Write-Host "Web: http://127.0.0.1:$WebPort"
Write-Host "API: http://127.0.0.1:$ApiPort"
if ($UseLocalMySql) {
  Write-Host "MySQL: $LocalMySqlDbUrl"
}
if ($PublicWebUrl) {
  Write-Host "Public Web: $PublicWebUrl"
} elseif ((-not $NoTunnel) -and (Test-Path -LiteralPath $TunnelConfig -PathType Leaf)) {
  Write-Host "Tunnel: configured, but no hostname was parsed from deploy\\cloudflare\\config.yml" -ForegroundColor DarkYellow
}
Write-Host "Logs: $LogDir"

if (-not $NoBrowser) {
  Start-Process "http://127.0.0.1:$WebPort"
}
