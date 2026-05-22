param(
  [string]$Device = "gpu:0"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiDir = Join-Path $Root "apps\api"
$PythonExe = Join-Path $ApiDir ".venv\Scripts\python.exe"
$CacheHome = Join-Path $Root "data\cache\paddlex"
$AlignScript = Join-Path $Root "scripts\align_paddle_gpu_runtime.ps1"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
  throw "Python virtual environment not found: $PythonExe"
}

New-Item -ItemType Directory -Force -Path $CacheHome | Out-Null

if (Test-Path -LiteralPath $AlignScript -PathType Leaf) {
  & $AlignScript
}

$CacheHomeShort = @'
import sys
from ctypes import create_unicode_buffer, windll
from pathlib import Path

path = str(Path(sys.argv[1]).resolve())
buffer = create_unicode_buffer(4096)
result = windll.kernel32.GetShortPathNameW(path, buffer, len(buffer))
print(buffer.value if result > 0 and buffer.value else path)
'@ | & $PythonExe - $CacheHome

$env:PADDLEOCR_VL15_RUNTIME = "local"
$env:PADDLEOCR_VL15_DEVICE = $Device
$env:PADDLE_PDX_CACHE_HOME = $CacheHomeShort.Trim()
$env:PADDLE_PDX_MODEL_SOURCE = "modelscope"
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = "true"
$env:PADDLE_PDX_DISABLE_DEVICE_FALLBACK = "true"

Write-Host "==> Local PaddleOCR-VL1.5 install" -ForegroundColor Cyan
Write-Host "Device: $Device"
Write-Host "Cache : $($env:PADDLE_PDX_CACHE_HOME)"

@'
import os
from paddlex import create_pipeline

pipeline = create_pipeline(
    pipeline="PaddleOCR-VL-1.5",
    device=os.getenv("PADDLEOCR_VL15_DEVICE") or "gpu:0",
)
print("paddleocr-vl15-local-ready")
print(type(pipeline).__name__)
'@ | & $PythonExe -
