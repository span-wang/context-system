param(
  [string]$SqlitePath = "",
  [int]$MySqlPort = 3309,
  [string]$MySqlDatabase = "exam_kit_migrate_20260509",
  [switch]$ReinitializeMySql,
  [switch]$TruncateTarget,
  [switch]$SeedData
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiDir = Join-Path $Root "apps\api"
$VenvPython = Join-Path $ApiDir ".venv\Scripts\python.exe"
$MigrateScript = Join-Path $PSScriptRoot "migrate_sqlite_to_mysql.py"
$DbMigrateScript = Join-Path $PSScriptRoot "db-migrate.ps1"
$LocalMySqlScript = Join-Path $PSScriptRoot "start-local-mysql.ps1"
$RunDir = Join-Path $Root "data\run"
$LocalMySqlInfoPath = Join-Path $RunDir "mysql-local-$MySqlPort.json"

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
  throw "Python virtual environment not found: $VenvPython"
}
if (-not (Test-Path -LiteralPath $MigrateScript)) {
  throw "Migration script not found: $MigrateScript"
}

if (-not $SqlitePath) {
  $SqlitePath = Join-Path $Root "data\app.db"
}

$startArgs = @(
  "-Port", "$MySqlPort",
  "-Database", $MySqlDatabase
)
if ($ReinitializeMySql) {
  $startArgs += "-Reinitialize"
}

Write-Step "Start local MySQL"
& $LocalMySqlScript @startArgs
if ($LASTEXITCODE -ne 0) {
  throw "Local MySQL startup failed."
}
if (-not (Test-Path -LiteralPath $LocalMySqlInfoPath)) {
  throw "Local MySQL info file not found: $LocalMySqlInfoPath"
}
$mysqlInfo = Get-Content -Raw -LiteralPath $LocalMySqlInfoPath | ConvertFrom-Json
$dbUrl = [string]$mysqlInfo.db_url
if (-not $dbUrl) {
  throw "Local MySQL info file does not contain db_url."
}

Write-Step "Run Alembic migrations on MySQL"
$oldDbUrl = $env:DB_URL
try {
  $env:DB_URL = $dbUrl
  & $DbMigrateScript -Revision head -MySqlPort $MySqlPort -MySqlDatabase $MySqlDatabase
  if ($LASTEXITCODE -ne 0) {
    throw "Alembic migration failed."
  }

  Write-Step "Copy SQLite data into MySQL"
  $copyArgs = @(
    $MigrateScript,
    "--sqlite-path", $SqlitePath,
    "--mysql-url", $dbUrl
  )
  if ($TruncateTarget) {
    $copyArgs += "--truncate"
  }
  & $VenvPython @copyArgs
  if ($LASTEXITCODE -ne 0) {
    throw "SQLite to MySQL copy failed."
  }

  if ($SeedData) {
    Write-Step "Seed missing demo data after import"
    & $VenvPython -c "from app.db.bootstrap import initialize_database; initialize_database(run_migrations=False, seed_data=True); print('seeded')"
    if ($LASTEXITCODE -ne 0) {
      throw "Database seeding failed."
    }
  }
} finally {
  $env:DB_URL = $oldDbUrl
}

Write-Host ""
Write-Host "SQLite to MySQL migration completed." -ForegroundColor Green
Write-Host "Source SQLite: $SqlitePath"
Write-Host "Target MySQL: $dbUrl"
