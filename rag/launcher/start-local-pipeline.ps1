[CmdletBinding()]
param([switch]$OpenBrowser)

$ErrorActionPreference = "Stop"

function Read-Port([string]$Name, [int]$Default) {
    $raw = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($raw)) { return $Default }
    [int]$value = 0
    if (-not [int]::TryParse($raw, [ref]$value) -or $value -lt 1 -or $value -gt 65535) {
        throw "$Name must be an integer between 1 and 65535; received '$raw'."
    }
    return $value
}

$ragHubPort = Read-Port "RAG_HUB_PORT" 8001
$frontendPort = Read-Port "RAG_FRONTEND_PORT" 8010
$cVocPort = Read-Port "C_VOC_PORT" 8765
$bEndPort = Read-Port "B_END_PORT" 8000
$kolPort = Read-Port "KOL_PLATFORM_PORT" 8766
$ragHubUrl = "http://127.0.0.1:$ragHubPort"
$frontendUrl = "http://127.0.0.1:$frontendPort"
$cVocUrl = "http://127.0.0.1:$cVocPort"
$bEndUrl = "http://127.0.0.1:$bEndPort"
$kolUrl = "http://127.0.0.1:$kolPort"

$ragRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $ragRoot "..")).Path
$serviceRoot = Join-Path $ragRoot "service"
$frontendRoot = Join-Path $ragRoot "frontend-v2"
$cRoot = Join-Path $repoRoot "customer-voc\sentiment-analysis\voc-sentiment-analysis"
$bRoot = Join-Path $repoRoot "b2b-public-sector\week7\compliance-sales-support"
$kolRoot = Join-Path $repoRoot "creator-intelligence\global-creator-assessment-platform"
$kolDataDir = Join-Path $repoRoot ".local-kol-platform"

function Test-LocalPort([int]$Port) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Resolve-Python([string[]]$Candidates) {
    foreach ($candidate in $Candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return $python.Source }
    throw "Python 3.11/3.12 was not found."
}

function Read-EnvValue([string]$Path, [string]$Key) {
    if (-not (Test-Path -LiteralPath $Path)) { return "" }
    $line = Get-Content -LiteralPath $Path | Where-Object { $_ -match "^$([regex]::Escape($Key))=" } | Select-Object -First 1
    if (-not $line) { return "" }
    return $line.Split("=", 2)[1].Trim().Trim('"').Trim("'")
}

function Set-EnvValue([string]$Path, [string]$Key, [string]$Value) {
    $lines = @()
    if (Test-Path -LiteralPath $Path) { $lines = @(Get-Content -LiteralPath $Path) }
    $pattern = "^$([regex]::Escape($Key))="
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pattern) {
            $lines[$i] = "$Key=$Value"
            $found = $true
            break
        }
    }
    if (-not $found) { $lines += "$Key=$Value" }
    [IO.File]::WriteAllLines($Path, $lines, [Text.UTF8Encoding]::new($false))
}

function Is-PlaceholderSecret([string]$Value) {
    $normalized = if ($null -eq $Value) { "" } else { $Value.Trim().ToLowerInvariant() }
    return $normalized -in @(
        "",
        "replace-me",
        "replace_with_rag_hub_api_key",
        "replace-with-shared-secret"
    )
}

function Start-ServiceIfNeeded([string]$Name, [int]$Port, [string]$Python, [string]$WorkingDirectory, [string[]]$Arguments) {
    if (Test-LocalPort $Port) {
        Write-Host "[OK] $Name is already running on port $Port." -ForegroundColor Green
        return $false
    }
    Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -WindowStyle Hidden
    Write-Host "[..] Starting $Name on port $Port..."
    return $true
}

function Wait-LocalPort([string]$Name, [int]$Port, [int]$Attempts = 10) {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        if (Test-LocalPort $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    Write-Warning "$Name did not accept connections on port $Port after $($Attempts * 0.5) seconds."
    return $false
}

function Test-CVocInstance([int]$Port, [string]$ExpectedRoot) {
    if (-not (Test-LocalPort $Port)) { return $false }
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        $dbPath = [string]$health.db
        if ([string]::IsNullOrWhiteSpace($dbPath)) { return $false }
        $expectedPath = [IO.Path]::GetFullPath($ExpectedRoot).TrimEnd('\') + '\'
        $actualPath = [IO.Path]::GetFullPath($dbPath)
        return $actualPath.StartsWith($expectedPath, [StringComparison]::OrdinalIgnoreCase)
    } catch {
        return $false
    }
}

function Test-KolInstance([int]$Port) {
    if (-not (Test-LocalPort $Port)) { return $false }
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        return [string]$health.status -eq "ok"
    } catch {
        return $false
    }
}

foreach ($required in @(
    (Join-Path $serviceRoot "app\main.py"),
    (Join-Path $serviceRoot ".env"),
    (Join-Path $cRoot "app_server.py"),
    (Join-Path $cRoot ".env"),
    (Join-Path $frontendRoot "server.py"),
    (Join-Path $frontendRoot "dist\index.html"),
    (Join-Path $bRoot "api\main.py"),
    (Join-Path $bRoot "requirements.txt"),
    (Join-Path $kolRoot "app\main.py"),
    (Join-Path $kolRoot "requirements.txt")
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required local file is missing: $required"
    }
}

$servicePython = Resolve-Python @(
    (Join-Path $serviceRoot ".venv\Scripts\python.exe")
)
$cPython = Resolve-Python @(
    (Join-Path $cRoot "venv312\Scripts\python.exe"),
    $servicePython
)
$bPython = Resolve-Python @(
    (Join-Path $bRoot ".venv\Scripts\python.exe"),
    $servicePython
)
$kolPython = Resolve-Python @(
    (Join-Path $kolRoot ".venv\Scripts\python.exe"),
    $servicePython
)

if ((Test-LocalPort $cVocPort) -and -not (Test-CVocInstance $cVocPort $cRoot)) {
    throw "C_VOC_PORT $cVocPort is occupied by another service, not customer-voc/sentiment-analysis/voc-sentiment-analysis. Stop that service or choose another C_VOC_PORT."
}
if ((Test-LocalPort $kolPort) -and -not (Test-KolInstance $kolPort)) {
        throw "KOL_PLATFORM_PORT $kolPort is occupied by another service, not the Global Creator Assessment Platform. Stop that service or choose another KOL_PLATFORM_PORT."
}

$serviceEnv = Join-Path $serviceRoot ".env"
$cEnv = Join-Path $cRoot ".env"
$serviceKey = Read-EnvValue $serviceEnv "RAG_HUB_API_KEY"
$cKey = Read-EnvValue $cEnv "RAG_HUB_API_KEY"
if ((-not (Is-PlaceholderSecret $serviceKey)) -and (Is-PlaceholderSecret $cKey)) {
    Set-EnvValue $cEnv "RAG_HUB_API_KEY" $serviceKey
} elseif ((Is-PlaceholderSecret $serviceKey) -and (-not (Is-PlaceholderSecret $cKey))) {
    Set-EnvValue $serviceEnv "RAG_HUB_API_KEY" $cKey
} elseif ((-not (Is-PlaceholderSecret $serviceKey)) -and (-not (Is-PlaceholderSecret $cKey)) -and ($serviceKey -cne $cKey)) {
    throw "RAG_HUB_API_KEY differs between the RAG service and C-side .env files. Resolve the mismatch before starting the local pipeline."
}
$serviceKey = Read-EnvValue $serviceEnv "RAG_HUB_API_KEY"
Set-EnvValue $cEnv "RAG_HUB_URL" $ragHubUrl
Set-EnvValue $cEnv "C_RAG_PUSH_ENABLED" "true"
Set-EnvValue $cEnv "C_RAG_SNAPSHOT_MODE" "historical"

if (Get-Command docker -ErrorAction SilentlyContinue) {
    $dockerInfoExitCode = 1
    $previousDockerErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker info 1>$null 2>$null
        $dockerInfoExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousDockerErrorAction
    }
    if ($dockerInfoExitCode -eq 0) {
        $containers = @(& docker ps -a --format "{{.Names}}" 1>$null 2>$null)
        foreach ($container in @("maxkb", "ollama")) {
            if ($containers -contains $container) {
                & docker start $container 1>$null 2>$null
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning "Docker container '$container' could not be started."
                }
            }
        }
    } else {
        Write-Warning "Docker Desktop is unavailable; MaxKB/Ollama containers were not started."
    }
}

if (-not (Test-LocalPort 11434)) {
    $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path -LiteralPath $ollama) {
        Start-Process -FilePath $ollama -ArgumentList @("serve") -WindowStyle Hidden
        Write-Host "[..] Starting native Ollama on port 11434..."
    }
}

$ragStarted = Start-ServiceIfNeeded "RAG Hub API" $ragHubPort $servicePython $serviceRoot @(
    "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$ragHubPort", "--env-file", ".env"
)
$cStarted = Start-ServiceIfNeeded "C-side VOC" $cVocPort $cPython $cRoot @(
    "app_server.py", "--host", "127.0.0.1", "--port", "$cVocPort"
)
if (-not (Test-Path -LiteralPath $kolDataDir)) {
    New-Item -ItemType Directory -Path $kolDataDir -Force | Out-Null
}
$env:KOL_PLATFORM_DATA_DIR = $kolDataDir
$kolStarted = Start-ServiceIfNeeded "KOL platform" $kolPort $kolPython $kolRoot @(
    "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$kolPort"
)

$env:RAG_HUB_SERVICE_ENV = $serviceEnv
$env:RAG_HUB_INTERNAL_URL = $ragHubUrl
$env:RAG_FRONTEND_PORT = "$frontendPort"
$frontendStarted = Start-ServiceIfNeeded "RAG frontend" $frontendPort $servicePython $frontendRoot @("server.py")

$bStarted = $false
$bPushEnabled = -not (Is-PlaceholderSecret $serviceKey)
if (-not $bPushEnabled) {
    Write-Warning "RAG_HUB_API_KEY is not configured; B-side will start with RAG_PUSH_ENABLED=false."
}
if (Test-LocalPort $bEndPort) {
    Write-Host "[OK] B-side business platform is already running on port $bEndPort." -ForegroundColor Green
} else {
    $bEnvironmentKeys = @("RAG_PUSH_ENABLED", "RAG_HUB_BASE_URL", "RAG_HUB_API_KEY", "B_END_PUBLIC_URL")
    $previousBEnvironment = @{}
    foreach ($key in $bEnvironmentKeys) {
        $previousBEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
    }
    try {
        $env:RAG_PUSH_ENABLED = if ($bPushEnabled) { "true" } else { "false" }
        $env:RAG_HUB_BASE_URL = $ragHubUrl
        $env:RAG_HUB_API_KEY = $serviceKey
        $env:B_END_PUBLIC_URL = $bEndUrl
        $bArguments = @(
            "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "$bEndPort"
        )
        $bEnv = Join-Path $bRoot ".env"
        if (Test-Path -LiteralPath $bEnv) {
            $bArguments += @("--env-file", ".env")
        }
        Start-Process -FilePath $bPython -ArgumentList $bArguments -WorkingDirectory $bRoot -WindowStyle Hidden
        Write-Host "[..] Starting B-side business platform on port $bEndPort..."
        $bStarted = $true
    } finally {
        foreach ($key in $bEnvironmentKeys) {
            $oldValue = $previousBEnvironment[$key]
            if ($null -eq $oldValue) {
                Remove-Item "Env:$key" -ErrorAction SilentlyContinue
            } else {
                Set-Item "Env:$key" $oldValue
            }
        }
    }
}

Wait-LocalPort "RAG Hub API" $ragHubPort | Out-Null
Wait-LocalPort "C-side VOC" $cVocPort | Out-Null
Wait-LocalPort "KOL platform" $kolPort | Out-Null
Wait-LocalPort "RAG frontend" $frontendPort | Out-Null
Wait-LocalPort "B-side business platform" $bEndPort | Out-Null
Write-Host "C-side VOC : $cVocUrl/"
Write-Host "B-side app  : $bEndUrl/"
Write-Host "KOL platform: $kolUrl/"
Write-Host "RAG frontend: $frontendUrl/"
Write-Host "RAG API     : $ragHubUrl/health"
Write-Host "MaxKB       : http://127.0.0.1:8080/"
Write-Host "KOL sync    : powershell -ExecutionPolicy Bypass -File .\sync-kol-to-rag.ps1 -DryRun"

if ($OpenBrowser) {
    Start-Process "$cVocUrl/"
    Start-Process "$bEndUrl/"
    Start-Process "$kolUrl/"
    Start-Process "$frontendUrl/"
}

exit 0
