param(
  [switch]$AlsoKnownPorts
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$RunDir = Join-Path $Root "data\run"

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Stop-ProcessTree([int]$ProcessId) {
  $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
  foreach ($child in $children) {
    Stop-ProcessTree ([int]$child.ProcessId)
  }
  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if ($process) {
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
  }
}

function Test-ProjectPort([int]$Port) {
  if ($Port -eq 8000) {
    try {
      $result = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/system/healthz" -TimeoutSec 2
      return ($result.name -eq "exam-kit")
    } catch {
      return $false
    }
  }
  if ($Port -eq 3000) {
    try {
      $response = Invoke-WebRequest -Uri "http://127.0.0.1:3000/generate" -UseBasicParsing -TimeoutSec 2
      return ($response.Content -like "*Exam Kit*")
    } catch {
      return $false
    }
  }
  return $false
}

function Stop-PidFile([string]$Name) {
  $path = Join-Path $RunDir "$Name.pid"
  if (-not (Test-Path -LiteralPath $path)) {
    Write-Host "$Name pid file not found; skipped."
    return
  }
  $pidText = (Get-Content -LiteralPath $path -ErrorAction SilentlyContinue | Select-Object -First 1)
  if (-not $pidText) {
    Remove-Item -LiteralPath $path -Force
    return
  }
  $targetPid = [int]$pidText
  $process = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
  if ($process) {
    Write-Step "Stop $Name pid=$targetPid"
    Stop-ProcessTree $targetPid
  } else {
    Write-Host "$Name pid=$targetPid is not running."
  }
  Remove-Item -LiteralPath $path -Force
}

function Stop-PortIfProject([int]$Port) {
  $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  foreach ($connection in $connections) {
    $pidValue = [int]$connection.OwningProcess
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $pidValue" -ErrorAction SilentlyContinue
    $matchesRoot = $proc -and $proc.CommandLine -and $proc.CommandLine.Contains([string]$Root)
    $matchesHealth = Test-ProjectPort $Port
    if ($matchesRoot -or $matchesHealth) {
      Write-Step "Stop project process on port $Port pid=$pidValue"
      Stop-ProcessTree $pidValue
    }
  }
}

Stop-PidFile "web"
Stop-PidFile "api"

if ($AlsoKnownPorts) {
  Stop-PortIfProject 3000
  Stop-PortIfProject 8000
}

Write-Host "Stopped." -ForegroundColor Green
