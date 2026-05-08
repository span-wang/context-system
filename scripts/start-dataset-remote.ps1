param(
  [int]$ApiPort = 8000,
  [int]$WebPort = 3000,
  [switch]$UseLocalMySql,
  [int]$MySqlPort = 3309,
  [string]$MySqlDatabase = "exam_kit_local",
  [switch]$NoInstall,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Runner = Join-Path $Root "scripts\start.ps1"
$DatasetTunnelConfig = Join-Path $Root "deploy\cloudflare\config.dataset.yml"

if (-not (Test-Path -LiteralPath $DatasetTunnelConfig -PathType Leaf)) {
  throw "Missing dataset tunnel config: $DatasetTunnelConfig. Run deploy\\cloudflare\\configure_dataset_tunnel.ps1 first."
}

& $Runner `
  -ApiPort $ApiPort `
  -WebPort $WebPort `
  -UseLocalMySql:$UseLocalMySql `
  -MySqlPort $MySqlPort `
  -MySqlDatabase $MySqlDatabase `
  -NoInstall:$NoInstall `
  -NoBrowser:$NoBrowser `
  -TunnelConfigPath $DatasetTunnelConfig
