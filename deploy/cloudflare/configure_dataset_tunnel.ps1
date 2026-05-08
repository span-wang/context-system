param(
  [Parameter(Mandatory = $true)]
  [string]$TunnelId,
  [Parameter(Mandatory = $true)]
  [string]$Hostname,
  [string]$CredentialsFile = "",
  [int]$WebPort = 3000
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $ScriptDir "configure_named_tunnel.ps1"

& $Runner `
  -TunnelId $TunnelId `
  -Hostname $Hostname `
  -CredentialsFile $CredentialsFile `
  -WebPort $WebPort `
  -OutputPath "config.dataset.yml"
