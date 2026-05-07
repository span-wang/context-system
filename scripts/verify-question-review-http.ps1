param(
  [string]$ApiBase = "",
  [int]$TimeoutSeconds = 30,
  [string]$Username = "admin",
  [string]$Password = "admin123456"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$PortsPath = Join-Path $Root "data\run\ports.json"
$ApiDir = Join-Path $Root "apps\api"
$VenvPython = Join-Path $ApiDir ".venv\Scripts\python.exe"
$Runner = Join-Path $Root "scripts\verify_question_review_http.py"

function Resolve-ApiBase {
  if ($ApiBase) {
    return $ApiBase.TrimEnd("/")
  }
  if (Test-Path -LiteralPath $PortsPath) {
    $ports = Get-Content -Raw -LiteralPath $PortsPath | ConvertFrom-Json
    if ($ports.api_base) {
      return ([string]$ports.api_base).TrimEnd("/")
    }
  }
  return "http://127.0.0.1:8000"
}

if (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
  $Python = $VenvPython
} else {
  $Python = (Get-Command python -ErrorAction Stop).Source
}

$ResolvedApiBase = Resolve-ApiBase
Write-Host "Verifying question review write APIs at $ResolvedApiBase"

& $Python $Runner `
  --api-base $ResolvedApiBase `
  --timeout $TimeoutSeconds `
  --username $Username `
  --password $Password

if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
