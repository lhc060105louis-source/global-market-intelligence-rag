[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Mock,
    [double]$WatchSeconds = 0
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$serviceRoot = Join-Path $repoRoot "rag\service"
$python = Join-Path $serviceRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Python was not found. Create rag\service\.venv or put Python on PATH."
    }
    $python = $command.Source
}

$script = Join-Path $serviceRoot "scripts\sync_kol_platform.py"
if (-not (Test-Path -LiteralPath $script)) {
    throw "Formal KOL synchronization script is missing: $script"
}

$arguments = @($script)
if ($DryRun) { $arguments += "--dry-run" }
if ($Mock) { $arguments += "--mock" }
if ($WatchSeconds -gt 0) { $arguments += @("--watch-seconds", [string]$WatchSeconds) }
& $python @arguments
exit $LASTEXITCODE
