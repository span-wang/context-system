param(
  [int]$Port = 3307,
  [string]$Database = "exam_kit_local",
  [string]$User = "examkit",
  [string]$Password = "examkit123",
  [string]$RootPassword = "root123456",
  [switch]$Reinitialize
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$DataDir = Join-Path $Root "data"
$RunDir = Join-Path $DataDir "run"
$MysqlRoot = Join-Path $DataDir "mysql-local-$Port"
$MysqlDataDir = Join-Path $MysqlRoot "data"
$MysqlLogDir = Join-Path $MysqlRoot "logs"
$MysqlTmpDir = Join-Path $MysqlRoot "tmp"
$InitSqlPath = Join-Path $MysqlRoot "init.sql"
$ConfigPath = Join-Path $MysqlRoot "my.ini"
$PidPath = Join-Path $RunDir "mysql-local-$Port.pid"
$InfoPath = Join-Path $RunDir "mysql-local-$Port.json"
$MySqlDExe = (Get-Command mysqld.exe -ErrorAction Stop).Source
$MySqlExe = (Get-Command mysql.exe -ErrorAction Stop).Source
$MySqlAdminExe = (Get-Command mysqladmin.exe -ErrorAction Stop).Source

function To-MySqlPath([string]$PathValue) {
  return $PathValue.Replace("\", "/")
}

New-Item -ItemType Directory -Force -Path $RunDir, $MysqlRoot, $MysqlLogDir, $MysqlTmpDir | Out-Null

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-ListenProcessId([int]$TargetPort) {
  $connection = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($connection) { return [int]$connection.OwningProcess }
  return $null
}

function Wait-Tcp([int]$TargetPort, [int]$TimeoutSeconds = 45) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Get-ListenProcessId $TargetPort) { return $true }
    Start-Sleep -Milliseconds 700
  }
  return $false
}

function Wait-MySqlReady([int]$TargetPort, [int]$TimeoutSeconds = 60) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      & $MySqlAdminExe --protocol=tcp --host=127.0.0.1 --port=$TargetPort --user=root --password=$RootPassword ping | Out-Null
      if ($LASTEXITCODE -eq 0) { return $true }
    } catch {
      # Ignore until ready.
    }
    Start-Sleep -Milliseconds 900
  }
  return $false
}

function Ensure-DatabaseAccess([int]$TargetPort, [string]$TargetDatabase, [string]$TargetUser, [string]$TargetPassword) {
  $sql = @"
CREATE USER IF NOT EXISTS '$TargetUser'@'127.0.0.1' IDENTIFIED BY '$TargetPassword';
CREATE USER IF NOT EXISTS '$TargetUser'@'localhost' IDENTIFIED BY '$TargetPassword';
CREATE DATABASE IF NOT EXISTS $TargetDatabase CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON $TargetDatabase.* TO '$TargetUser'@'127.0.0.1';
GRANT ALL PRIVILEGES ON $TargetDatabase.* TO '$TargetUser'@'localhost';
FLUSH PRIVILEGES;
"@

  & $MySqlExe --protocol=tcp --host=127.0.0.1 --port=$TargetPort --user=root --password=$RootPassword -e $sql
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to ensure database/user grants for local MySQL on port $TargetPort."
  }
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

function Stop-LocalMySqlIfRunning([int]$TargetPort) {
  if (Test-Path -LiteralPath $PidPath) {
    $pidText = Get-Content -LiteralPath $PidPath -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pidText) {
      Stop-ProcessTree ([int]$pidText)
    }
    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
  }

  $listeningPid = Get-ListenProcessId $TargetPort
  if ($listeningPid) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $listeningPid" -ErrorAction SilentlyContinue
    $commandLine = if ($proc) { [string]$proc.CommandLine } else { "" }
    $looksLikeLocalMysql = $commandLine.Contains([string]$MysqlRoot) -or $commandLine.Contains("mysqld")
    if ($looksLikeLocalMysql) {
      Stop-ProcessTree $listeningPid
    } else {
      throw "Port $TargetPort is in use by another process (pid=$listeningPid); refusing to stop it automatically."
    }
  }
}

if ($Reinitialize -and (Test-Path -LiteralPath $MysqlRoot)) {
  Write-Step "Reinitialize local MySQL data directory"
  Stop-LocalMySqlIfRunning $Port
  Remove-Item -LiteralPath $MysqlRoot -Recurse -Force
  New-Item -ItemType Directory -Force -Path $MysqlRoot, $MysqlLogDir, $MysqlTmpDir | Out-Null
}

if (Get-ListenProcessId $Port) {
  Write-Step "MySQL local instance already listening on port $Port; ensure database and grants"
  Ensure-DatabaseAccess -TargetPort $Port -TargetDatabase $Database -TargetUser $User -TargetPassword $Password
  $dbUrl = "mysql+pymysql://{0}:{1}@127.0.0.1:{2}/{3}?charset=utf8mb4" -f $User, $Password, $Port, $Database
  @{
    port = $Port
    database = $Database
    user = $User
    password = $Password
    root_password = $RootPassword
    db_url = $dbUrl
    started_at = (Get-Date).ToString("s")
  } | ConvertTo-Json | Set-Content -LiteralPath $InfoPath -Encoding utf8
  Write-Host "Local MySQL is ready." -ForegroundColor Green
  Write-Host "DB_URL=$dbUrl"
  exit 0
}

$config = @"
[mysqld]
port=$Port
bind-address=127.0.0.1
mysqlx=0
basedir=$(To-MySqlPath ([IO.Path]::GetDirectoryName([IO.Path]::GetDirectoryName($MySqlDExe))))
datadir=$(To-MySqlPath $MysqlDataDir)
tmpdir=$(To-MySqlPath $MysqlTmpDir)
log-error=$(To-MySqlPath (Join-Path $MysqlLogDir "mysqld.err.log"))
pid-file=$(To-MySqlPath (Join-Path $MysqlRoot "mysqld.pid"))
secure-file-priv=
character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci
default-time-zone=+08:00
"@
Set-Content -LiteralPath $ConfigPath -Value $config -Encoding ascii

if (-not (Test-Path -LiteralPath $MysqlDataDir)) {
  Write-Step "Initialize local MySQL data directory"
@"
ALTER USER 'root'@'localhost' IDENTIFIED BY '$RootPassword';
CREATE USER IF NOT EXISTS '$User'@'127.0.0.1' IDENTIFIED BY '$Password';
CREATE USER IF NOT EXISTS '$User'@'localhost' IDENTIFIED BY '$Password';
CREATE DATABASE IF NOT EXISTS $Database CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON $Database.* TO '$User'@'127.0.0.1';
GRANT ALL PRIVILEGES ON $Database.* TO '$User'@'localhost';
FLUSH PRIVILEGES;
"@ | Set-Content -LiteralPath $InitSqlPath -Encoding ascii

  & $MySqlDExe --defaults-file=$ConfigPath --initialize-insecure --init-file=$InitSqlPath
  if ($LASTEXITCODE -ne 0) {
    throw "mysqld --initialize-insecure failed."
  }
}

Write-Step "Start local MySQL instance on port $Port"
$mysqlOut = Join-Path $MysqlLogDir "mysqld.out.log"
$mysqlErr = Join-Path $MysqlLogDir "mysqld.start.err.log"
$mysqlProc = Start-Process -FilePath $MySqlDExe `
  -ArgumentList @("--defaults-file=$ConfigPath", "--console") `
  -WorkingDirectory $MysqlRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput $mysqlOut `
  -RedirectStandardError $mysqlErr `
  -PassThru

Set-Content -LiteralPath $PidPath -Value $mysqlProc.Id -Encoding ascii

if (-not (Wait-Tcp $Port 45)) {
  throw "Local MySQL startup timed out before the port became available. Check $mysqlErr"
}

if (-not (Wait-MySqlReady $Port 90)) {
  throw "Local MySQL startup timed out before the server became ready. Check $mysqlErr"
}

Ensure-DatabaseAccess -TargetPort $Port -TargetDatabase $Database -TargetUser $User -TargetPassword $Password

$dbUrl = "mysql+pymysql://{0}:{1}@127.0.0.1:{2}/{3}?charset=utf8mb4" -f $User, $Password, $Port, $Database

@{
  port = $Port
  database = $Database
  user = $User
  password = $Password
  root_password = $RootPassword
  db_url = $dbUrl
  started_at = (Get-Date).ToString("s")
} | ConvertTo-Json | Set-Content -LiteralPath $InfoPath -Encoding utf8

Write-Host "Local MySQL is ready." -ForegroundColor Green
Write-Host "DB_URL=$dbUrl"
