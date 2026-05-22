param(
  [string]$TargetCudnnVersion = "9.9.0.52"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiDir = Join-Path $Root "apps\api"
$PythonExe = Join-Path $ApiDir ".venv\Scripts\python.exe"
$WheelDir = Join-Path $Root ".codex_tmp\wheels"
$WheelName = "nvidia_cudnn_cu12-$TargetCudnnVersion-py3-none-win_amd64.whl"
$WheelPath = Join-Path $WheelDir $WheelName
$OfficialSha256 = "d53036b7edad1a85b5d59580defc91e30326746fde21ffc701eb8b4d4695eca1"
$MirrorUrl = "https://pypi.tuna.tsinghua.edu.cn/packages/6f/5c/f77147ce7e27a4e9087fb34b0539ff085c68e7093e96ee85576fe31fe064/$WheelName"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
  throw "Python virtual environment not found: $PythonExe"
}

function Get-CudnnVersion {
  @'
import importlib.metadata as md
try:
    print(md.version("nvidia-cudnn-cu12"))
except Exception:
    print("")
'@ | & $PythonExe -
}

$current = (Get-CudnnVersion).Trim()
if ($current -eq $TargetCudnnVersion) {
  Write-Host "cuDNN runtime already aligned: $current" -ForegroundColor Green
  exit 0
}

New-Item -ItemType Directory -Force -Path $WheelDir | Out-Null

if (-not (Test-Path -LiteralPath $WheelPath -PathType Leaf)) {
  Write-Host "==> Download cuDNN wheel $TargetCudnnVersion" -ForegroundColor Cyan
  Invoke-WebRequest -Uri $MirrorUrl -OutFile $WheelPath -TimeoutSec 7200 -UseBasicParsing
}

$hash = (Get-FileHash -Algorithm SHA256 $WheelPath).Hash.ToLower()
if ($hash -ne $OfficialSha256) {
  throw "Wheel sha256 mismatch: expected $OfficialSha256, got $hash"
}

Write-Host "==> Install cuDNN runtime $TargetCudnnVersion" -ForegroundColor Cyan
& $PythonExe -m pip install --upgrade $WheelPath
if ($LASTEXITCODE -ne 0) {
  throw "cuDNN runtime installation failed."
}

$updated = (Get-CudnnVersion).Trim()
if ($updated -ne $TargetCudnnVersion) {
  throw "cuDNN runtime version check failed after install: $updated"
}

Write-Host "cuDNN runtime aligned to $updated" -ForegroundColor Green
