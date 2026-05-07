param(
  [string]$SamplePath = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiDir = Join-Path $Root "apps\api"
$Runner = Join-Path $Root "scripts\verify_paper_parser.py"

if (-not $SamplePath) {
  $sample = Get-ChildItem -Path (Join-Path $Root "data") -Recurse -File -Include *.txt,*.md -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $sample) {
    throw "No UTF-8 text/markdown sample found. Use -SamplePath to specify a sample file."
  }
  $SamplePath = $sample.FullName
}

$ResolvedSamplePath = (Resolve-Path $SamplePath -ErrorAction Stop).Path

& python $Runner $ResolvedSamplePath $ApiDir
