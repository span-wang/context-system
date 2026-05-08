param(
  [Parameter(Mandatory = $true)]
  [string]$TunnelId,
  [Parameter(Mandatory = $true)]
  [string]$Hostname,
  [string]$CredentialsFile = "",
  [int]$WebPort = 3000,
  [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutputPath) {
  $OutputPath = Join-Path $ScriptDir "config.yml"
} elseif (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
  $OutputPath = Join-Path $ScriptDir $OutputPath
}

if (-not $CredentialsFile) {
  $CredentialsFile = Join-Path $env:USERPROFILE ".cloudflared\$TunnelId.json"
}

$content = @(
  "tunnel: $TunnelId"
  "credentials-file: $CredentialsFile"
  ""
  "ingress:"
  "  - hostname: $Hostname"
  "    service: http://127.0.0.1:$WebPort"
  "  - service: http_status:404"
) -join [Environment]::NewLine

Set-Content -LiteralPath $OutputPath -Value $content -Encoding utf8
Write-Host "Wrote $OutputPath" -ForegroundColor Green
Write-Host "Public hostname: https://$Hostname" -ForegroundColor Green
