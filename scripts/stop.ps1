param(
  [switch]$AlsoKnownPorts
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RunDir = Join-Path $Root "data\run"
$PortsPath = Join-Path $RunDir "ports.json"
$script:VisitedStopIds = @{}
$script:ProtectedProcessIds = @{}

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-ContainsIgnoreCase([string]$Value, [string]$Needle) {
  if (-not $Value -or -not $Needle) { return $false }
  return ($Value.IndexOf($Needle, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
}

function Get-ProcessSnapshot {
  return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
}

function Get-SnapshotProcess([object[]]$Snapshot, [int]$ProcessId) {
  return $Snapshot | Where-Object { [int]$_.ProcessId -eq $ProcessId } | Select-Object -First 1
}

function Initialize-ProtectedProcesses {
  $snapshot = Get-ProcessSnapshot
  $currentId = [int]$PID
  while ($currentId -gt 0 -and -not $script:ProtectedProcessIds.ContainsKey($currentId)) {
    $script:ProtectedProcessIds[$currentId] = $true
    $current = Get-SnapshotProcess $snapshot $currentId
    if (-not $current) { break }
    $currentId = [int]$current.ParentProcessId
  }
}

function Stop-ProcessTree([int]$ProcessId, [object[]]$Snapshot = $null) {
  if ($script:VisitedStopIds.ContainsKey($ProcessId)) { return }
  $script:VisitedStopIds[$ProcessId] = $true
  if (-not $Snapshot) { $Snapshot = Get-ProcessSnapshot }

  $children = $Snapshot | Where-Object { [int]$_.ParentProcessId -eq $ProcessId }
  foreach ($child in $children) {
    Stop-ProcessTree ([int]$child.ProcessId) $Snapshot
  }

  if ($script:ProtectedProcessIds.ContainsKey($ProcessId)) {
    return
  }

  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if ($process) {
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
  }
}

function Test-ProjectPort([int]$Port) {
  try {
    $result = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/system/healthz" -TimeoutSec 2
    if ($result.name -eq "exam-kit") { return $true }
  } catch {
    # Not an API port.
  }
  try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/generate" -UseBasicParsing -TimeoutSec 2
    if ($response.Content -like "*Exam Kit*") { return $true }
  } catch {
    # Not a web port.
  }
  return $false
}

function Test-ProjectProcess([object]$ProcessInfo) {
  if (-not $ProcessInfo) { return $false }
  $commandLine = [string]$ProcessInfo.CommandLine
  $executablePath = [string]$ProcessInfo.ExecutablePath
  return (
    (Test-ContainsIgnoreCase $commandLine $Root) -or
    (Test-ContainsIgnoreCase $executablePath $Root)
  )
}

function Test-ProjectProcessOrAncestor([int]$ProcessId, [object[]]$Snapshot) {
  $seen = @{}
  $currentId = $ProcessId
  while ($currentId -gt 0 -and -not $seen.ContainsKey($currentId)) {
    $seen[$currentId] = $true
    $processInfo = Get-SnapshotProcess $Snapshot $currentId
    if (-not $processInfo) { return $false }
    if (Test-ProjectProcess $processInfo) { return $true }
    $currentId = [int]$processInfo.ParentProcessId
  }
  return $false
}

function Get-RecordedPorts {
  $ports = New-Object System.Collections.Generic.List[int]
  $ports.Add(3000)
  $ports.Add(8000)

  if (Test-Path -LiteralPath $PortsPath) {
    try {
      $portInfo = Get-Content -Raw -LiteralPath $PortsPath | ConvertFrom-Json
      if ($portInfo.api_port) { $ports.Add([int]$portInfo.api_port) }
      if ($portInfo.web_port) { $ports.Add([int]$portInfo.web_port) }
      if ($portInfo.mysql_port) { $ports.Add([int]$portInfo.mysql_port) }
    } catch {
      Write-Host "ports.json could not be parsed; falling back to known ports." -ForegroundColor DarkYellow
    }
  }

  Get-ChildItem -LiteralPath $RunDir -Filter "mysql-local-*.json" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
      $mysqlInfo = Get-Content -Raw -LiteralPath $_.FullName | ConvertFrom-Json
      if ($mysqlInfo.port) { $ports.Add([int]$mysqlInfo.port) }
    } catch {
      Write-Host "$($_.Name) could not be parsed; skipped." -ForegroundColor DarkYellow
    }
  }

  return @($ports | Sort-Object -Unique)
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
  $snapshot = Get-ProcessSnapshot
  $processInfo = Get-SnapshotProcess $snapshot $targetPid
  $children = @($snapshot | Where-Object { [int]$_.ParentProcessId -eq $targetPid })
  if ($processInfo -or $children.Count -gt 0) {
    Write-Step "Stop $Name pid=$targetPid"
    Stop-ProcessTree $targetPid $snapshot
  }
  if (-not $processInfo -and $children.Count -eq 0) {
    Write-Host "$Name pid=$targetPid is not running."
  }
  Remove-Item -LiteralPath $path -Force
}

function Stop-PortIfProject([int]$Port) {
  $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  foreach ($connection in $connections) {
    $pidValue = [int]$connection.OwningProcess
    $snapshot = Get-ProcessSnapshot
    $matchesRoot = Test-ProjectProcessOrAncestor $pidValue $snapshot
    $matchesHealth = Test-ProjectPort $Port
    if ($matchesRoot -or $matchesHealth) {
      Write-Step "Stop project process on port $Port pid=$pidValue"
      Stop-ProcessTree $pidValue $snapshot
    }
  }
}

function Stop-WebWrapperProcesses([int[]]$Ports) {
  $portPattern = ($Ports | Sort-Object -Unique | ForEach-Object { [regex]::Escape([string]$_) }) -join "|"
  if (-not $portPattern) { return }
  $snapshot = Get-ProcessSnapshot
  $wrappers = @(
    $snapshot | Where-Object {
      $_.CommandLine -and
      $_.CommandLine -match "npm-cli\.js" -and
      $_.CommandLine -match "\brun\s+dev\b" -and
      $_.CommandLine -match "--port\s+($portPattern)(\s|$)"
    }
  )
  foreach ($wrapper in $wrappers) {
    if ($script:ProtectedProcessIds.ContainsKey([int]$wrapper.ProcessId)) { continue }
    Write-Step "Stop web wrapper pid=$($wrapper.ProcessId)"
    Stop-ProcessTree ([int]$wrapper.ProcessId) $snapshot
  }
}

function Stop-ProjectProcessesByPath {
  for ($pass = 1; $pass -le 3; $pass++) {
    $snapshot = Get-ProcessSnapshot
    $matches = @(
      $snapshot | Where-Object {
        -not $script:ProtectedProcessIds.ContainsKey([int]$_.ProcessId) -and
        (Test-ProjectProcess $_)
      }
    )
    if ($matches.Count -eq 0) { return }
    foreach ($processInfo in $matches) {
      Write-Step "Stop project process pid=$($processInfo.ProcessId)"
      Stop-ProcessTree ([int]$processInfo.ProcessId) $snapshot
    }
    Start-Sleep -Milliseconds 500
  }
}

Initialize-ProtectedProcesses
$ports = Get-RecordedPorts

Stop-PidFile "web"
Stop-PidFile "api"
Stop-PidFile "mysql-local"
Stop-PidFile "tunnel"

Get-ChildItem -LiteralPath $RunDir -Filter "mysql-local-*.pid" -ErrorAction SilentlyContinue | ForEach-Object {
  $name = [System.IO.Path]::GetFileNameWithoutExtension($_.Name)
  Stop-PidFile $name
}

$ports | ForEach-Object {
  Stop-PortIfProject ([int]$_)
}

Stop-WebWrapperProcesses $ports
Stop-ProjectProcessesByPath

Write-Host "Stopped." -ForegroundColor Green
