param(
  [string]$ApiBase = "",
  [int]$TimeoutSeconds = 15,
  [switch]$SkipLearningDetails
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$PortsPath = Join-Path $Root "data\run\ports.json"
$Payloads = @{}

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

function Get-ItemCount($Payload) {
  if ($null -eq $Payload) { return 0 }
  return @($Payload).Count
}

function Invoke-ReadCheck([string]$Name, [string]$Path, [int]$MinCount = -1, [switch]$ExpectMySqlReady) {
  $url = "$script:ResolvedApiBase$Path"
  try {
    $payload = Invoke-RestMethod -Uri $url -TimeoutSec $TimeoutSeconds
    $Payloads[$Name] = $payload
    $count = Get-ItemCount $payload
    $ok = $true
    $detail = "ok"

    if ($MinCount -ge 0 -and $count -lt $MinCount) {
      $ok = $false
      $detail = "expected at least $MinCount item(s), got $count"
    }
    if ($ExpectMySqlReady -and -not $payload.summary.mysql_ready) {
      $ok = $false
      $detail = "mysql_ready is not true"
    }

    return [pscustomobject]@{
      Name = $Name
      Path = $Path
      Ok = $ok
      Count = $count
      Detail = $detail
    }
  } catch {
    return [pscustomobject]@{
      Name = $Name
      Path = $Path
      Ok = $false
      Count = 0
      Detail = $_.Exception.Message
    }
  }
}

$script:ResolvedApiBase = Resolve-ApiBase
Write-Host "Verifying professional platform read APIs at $ResolvedApiBase"

$results = @()
$results += Invoke-ReadCheck "system.status" "/platform/api/system/status" -ExpectMySqlReady
$results += Invoke-ReadCheck "question_bank.practice_sets" "/platform/api/question-bank/practice-sets" 1
$results += Invoke-ReadCheck "question_bank.mock_exams" "/platform/api/question-bank/mock-exams" 1
$results += Invoke-ReadCheck "learning.practice_sets" "/platform/api/learning/practice-sets" 1
$results += Invoke-ReadCheck "learning.sessions" "/platform/api/learning/sessions" 1
$results += Invoke-ReadCheck "learning.wrong_book" "/platform/api/learning/wrong-book" 1
$results += Invoke-ReadCheck "learning.mastery" "/platform/api/learning/mastery" 1
$results += Invoke-ReadCheck "workflow.topics" "/platform/api/workflow/topics" 1

if (-not $SkipLearningDetails -and $Payloads.ContainsKey("learning.sessions")) {
  $sessions = @($Payloads["learning.sessions"])
  if ($sessions.Count -gt 0 -and $sessions[0].id) {
    $results += Invoke-ReadCheck "learning.session_detail" "/platform/api/learning/sessions/$($sessions[0].id)" 1
  }
}

$results | Format-Table Name, Ok, Count, Detail -AutoSize

$failures = @($results | Where-Object { -not $_.Ok })
if ($failures.Count -gt 0) {
  Write-Error "Read API regression failed: $($failures.Count) check(s) failed."
  exit 1
}

Write-Host "All professional platform read API checks passed." -ForegroundColor Green
