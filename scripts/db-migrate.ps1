param(
  [string]$Revision = "head",
  [switch]$UseLocalMySql,
  [int]$MySqlPort = 3309,
  [string]$MySqlDatabase = "exam_kit_local",
  [switch]$SeedData,
  [switch]$SkipMigrate
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiDir = Join-Path $Root "apps\api"
$VenvPython = Join-Path $ApiDir ".venv\Scripts\python.exe"
$LocalMySqlScript = Join-Path $Root "scripts\start-local-mysql.ps1"
$RunDir = Join-Path $Root "data\run"
$LocalMySqlInfoPath = Join-Path $RunDir "mysql-local-$MySqlPort.json"

function Write-Step([string]$Message) {
  Write-Host "==> $Message" -ForegroundColor Cyan
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
  throw "Python virtual environment not found: $VenvPython"
}

$oldDbUrl = $env:DB_URL
$oldAutoMigrate = $env:DB_AUTO_MIGRATE
$oldSeedOnStartup = $env:DB_SEED_ON_STARTUP
$oldMigrationTarget = $env:DB_MIGRATION_TARGET

try {
  if ($UseLocalMySql) {
    if (-not (Test-Path -LiteralPath $LocalMySqlScript -PathType Leaf)) {
      throw "Local MySQL script not found: $LocalMySqlScript"
    }
    Write-Step "Start local MySQL for migration"
    & $LocalMySqlScript -Port $MySqlPort -Database $MySqlDatabase
    if ($LASTEXITCODE -ne 0) {
      throw "Local MySQL startup failed."
    }
    if (-not (Test-Path -LiteralPath $LocalMySqlInfoPath)) {
      throw "Local MySQL info file not found: $LocalMySqlInfoPath"
    }
    $mysqlInfo = Get-Content -Raw -LiteralPath $LocalMySqlInfoPath | ConvertFrom-Json
    $env:DB_URL = [string]$mysqlInfo.db_url
    Write-Host "DB_URL=$($env:DB_URL)"
  }

  $env:DB_AUTO_MIGRATE = "false"
  $env:DB_SEED_ON_STARTUP = $(if ($SeedData) { "true" } else { "false" })
  $env:DB_MIGRATION_TARGET = $Revision

  if (-not $SkipMigrate) {
    Write-Step "Run Alembic upgrade to $Revision"
    Push-Location $ApiDir
    try {
      & $VenvPython -m alembic upgrade $Revision
      if ($LASTEXITCODE -ne 0) {
        throw "Alembic upgrade failed."
      }
    } finally {
      Pop-Location
    }
  }

  Push-Location $ApiDir
  try {
    Write-Step "Inspect migration status"
    & $VenvPython -c "from app.db.bootstrap import get_migration_status; import json; print(json.dumps(get_migration_status(), ensure_ascii=False, indent=2))"
    if ($LASTEXITCODE -ne 0) {
      throw "Migration status inspection failed."
    }

    if ($SeedData) {
      Write-Step "Seed database"
      & $VenvPython -c "from app.db.bootstrap import initialize_database; initialize_database(run_migrations=False, seed_data=True); print('seeded')"
      if ($LASTEXITCODE -ne 0) {
        throw "Database seeding failed."
      }
    }
  } finally {
    Pop-Location
  }
} finally {
  $env:DB_URL = $oldDbUrl
  $env:DB_AUTO_MIGRATE = $oldAutoMigrate
  $env:DB_SEED_ON_STARTUP = $oldSeedOnStartup
  $env:DB_MIGRATION_TARGET = $oldMigrationTarget
}
