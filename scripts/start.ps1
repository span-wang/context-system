param(
  [int]$ApiPort = 8000,
  [int]$WebPort = 3000,
  [switch]$NoInstall,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiDir = Join-Path $Root "apps\api"
$WebDir = Join-Path $Root "apps\web"
$DataDir = Join-Path $Root "data"
$LogDir = Join-Path $DataDir "logs"
$RunDir = Join-Path $DataDir "run"
$VenvDir = Join-Path $ApiDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$PipExe = Join-Path $VenvDir "Scripts\pip.exe"

New-Item -ItemType Directory -Force -Path $LogDir, $RunDir | Out-Null

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

function Save-Pid([string]$Name, [int]$ProcessId) {
  Set-Content -LiteralPath (Join-Path $RunDir "$Name.pid") -Value $ProcessId -Encoding ascii
}

function Save-PortInfo([int]$Api, [int]$Web) {
  $json = @{
    api_port = $Api
    web_port = $Web
    api_base = "http://127.0.0.1:$Api"
    web_url = "http://127.0.0.1:$Web"
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
    & $PipExe install --timeout 120 --retries 5 -r $requirements
    if ($LASTEXITCODE -ne 0) { throw "API dependency installation failed." }
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
  if (Test-Http $ApiHealth) {
    Write-Step "API already running on port $ApiPort; reusing it"
  } else {
    $ApiPort = Find-FreePort ($ApiPort + 1)
    Write-Step "API port is occupied; using port $ApiPort"
  }
}

$ApiHealth = "http://127.0.0.1:$ApiPort/api/system/healthz"
if (-not (Test-Http $ApiHealth)) {
  Write-Step "Start API: $ApiHealth"
  $apiOut = Join-Path $LogDir "api.out.log"
  $apiErr = Join-Path $LogDir "api.err.log"
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
}

$WebUrl = "http://127.0.0.1:$WebPort/generate"
if (Get-ListenProcessId $WebPort) {
  if (Test-Http $WebUrl) {
    Write-Step "Web already running on port $WebPort; reusing it"
  } else {
    $WebPort = Find-FreePort ($WebPort + 1)
    Write-Step "Web port is occupied; using port $WebPort"
  }
}

$WebUrl = "http://127.0.0.1:$WebPort/generate"
if (-not (Test-Http $WebUrl)) {
  Write-Step "Start web: http://127.0.0.1:$WebPort"
  $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
  $oldApiBase = $env:NEXT_PUBLIC_API_BASE
  $env:NEXT_PUBLIC_API_BASE = "http://127.0.0.1:$ApiPort"
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
    $env:NEXT_PUBLIC_API_BASE = $oldApiBase
  }
  if (-not (Wait-Http $WebUrl 90)) {
    throw "Web startup timed out. Check log: $webErr"
  }
}

Save-PortInfo $ApiPort $WebPort

Write-Host ""
Write-Host "Exam Kit is ready." -ForegroundColor Green
Write-Host "Web: http://127.0.0.1:$WebPort"
Write-Host "API: http://127.0.0.1:$ApiPort"
Write-Host "Logs: $LogDir"

if (-not $NoBrowser) {
  Start-Process "http://127.0.0.1:$WebPort"
}
