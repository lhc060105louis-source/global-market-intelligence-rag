param([switch]$Smoke)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$BuildRoot = Join-Path $Root ".build/windows"
$Venv = Join-Path $BuildRoot "venv"
$Dist = Join-Path $Root "dist/windows"
$AppName = "KOL合作管理平台"

Remove-Item $BuildRoot,$Dist -Recurse -Force -ErrorAction SilentlyContinue
New-Item $BuildRoot,$Dist -ItemType Directory -Force | Out-Null
py -3 -m venv $Venv
$Python = Join-Path $Venv "Scripts/python.exe"
& $Python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else "Python 3.10+ is required")'
& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Root "requirements.txt") PyInstaller
& $Python -m PyInstaller --noconfirm --clean --workpath (Join-Path $BuildRoot "work") --distpath $Dist (Join-Path $Root "packaging/kol-platform.spec")

$Executable = Join-Path $Dist "$AppName/$AppName.exe"
if ($Smoke) {
  $Process = Start-Process $Executable -PassThru
  Start-Sleep -Seconds 3
  if ($Process.HasExited) { throw "Smoke launch failed" }
  Stop-Process -Id $Process.Id -Force
  Write-Host "Smoke launch passed: $Executable"
  exit 0
}

$ISCC = if ($env:ISCC) { $env:ISCC } else { "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $ISCC)) { throw "ISCC not found; set the ISCC environment variable" }
& $ISCC "/DSourceDir=$Dist\$AppName" (Join-Path $Root "packaging/windows/installer.iss")
