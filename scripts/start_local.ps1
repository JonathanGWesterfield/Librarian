<#
.SYNOPSIS
Starts the config-driven Docker Compose Librarian stack on Windows PowerShell.

.DESCRIPTION
Runs the Docker-resident provider resolver, then starts only the optional
Docker Ollama services needed by config/librarian.json. It never reads
settings or secrets from shell environment variables.

.EXAMPLE
./scripts/start_local.ps1

.EXAMPLE
./scripts/start_local.ps1 -Foreground -WithWorkers

.EXAMPLE
pwsh -File scripts/start_local.ps1 -NoBuild
#>
[CmdletBinding()]
param(
    [switch]$Foreground,
    [switch]$NoBuild,
    [switch]$WithWorkers
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "[librarian] Docker Compose v2 is required. Install and start a Docker runtime, then rerun."
}
& docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "[librarian] Docker Compose v2 is required." }
& docker info | Out-Null
if ($LASTEXITCODE -ne 0) { throw "[librarian] Docker is not running. Start Docker Desktop, then rerun." }

New-Item -ItemType Directory -Force -Path data, .runtime, config/secrets | Out-Null
if (-not (Test-Path config/librarian.json)) {
    Copy-Item config/librarian.example.json config/librarian.json
    Write-Host "[librarian] Created config/librarian.json from the example."
}
& docker compose --profile config-resolver run --rm --build config-resolver
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$selection = Get-Content .runtime/librarian.state.json -Raw | ConvertFrom-Json
if ($null -eq $selection.docker_ollama_enabled -or $selection.docker_ollama_enabled -isnot [bool]) {
    throw "[librarian] Configuration resolver did not produce a valid Docker-Ollama selection."
}
foreach ($name in @("api_port", "web_port")) {
    try { $value = [Convert]::ToInt32($selection.$name) } catch { throw "[librarian] Configuration resolver did not produce a valid $name." }
    if ($value -lt 1 -or $value -gt 65535) { throw "[librarian] Configuration resolver did not produce a valid $name." }
}

$composePrefix = @("compose", "-f", "docker-compose.yml", "-f", ".runtime/librarian.compose.json")
if ($WithWorkers) { $composePrefix += @("--profile", "workers") }

function Show-OllamaInitDiagnostics {
    param([string[]]$ComposePrefix)

    Write-Error "[librarian] ollama-init did not complete successfully. Current service state:"
    & docker @ComposePrefix ps --all ollama-init
    Write-Error "[librarian] ollama-init logs (last 100 lines):"
    & docker @ComposePrefix logs --tail 100 ollama-init
}

function Wait-OllamaInit {
    param([string[]]$ComposePrefix)

    $timeoutSeconds = 900
    $deadline = [DateTime]::UtcNow.AddSeconds($timeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $containerId = (& docker @ComposePrefix ps --all --quiet ollama-init) | Select-Object -First 1
        if ($LASTEXITCODE -ne 0) {
            Show-OllamaInitDiagnostics -ComposePrefix $ComposePrefix
            throw "[librarian] Could not inspect the ollama-init service."
        }
        if ($null -ne $containerId -and $containerId.Trim()) {
            $containerId = $containerId.Trim()
            $inspection = & docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' $containerId
            if ($LASTEXITCODE -eq 0) {
                $parts = $inspection -split '\s+', 2
                $state = $parts[0]
                $exitCode = if ($parts.Count -gt 1) { $parts[1] } else { "unknown" }
                if ($state -in @("exited", "dead")) {
                    if ($exitCode -eq "0") { return }
                    Write-Error "[librarian] ollama-init exited with code $exitCode."
                    Show-OllamaInitDiagnostics -ComposePrefix $ComposePrefix
                    throw "[librarian] Docker Ollama initialization failed."
                }
            }
        }
        Start-Sleep -Seconds 2
    }

    Write-Error "[librarian] Timed out after $timeoutSeconds seconds waiting for ollama-init to exit successfully."
    Show-OllamaInitDiagnostics -ComposePrefix $ComposePrefix
    throw "[librarian] Docker Ollama initialization timed out."
}

function Confirm-DockerOllamaModels {
    param([string[]]$ComposePrefix)

    $override = Get-Content .runtime/librarian.compose.json -Raw | ConvertFrom-Json
    $configured = [string]$override.services.'ollama-init'.environment.OLLAMA_INIT_MODELS
    if (-not $configured) { return }
    $models = @($configured -split ',' | Where-Object { $_ })
    $modelList = & docker @ComposePrefix exec -T ollama ollama list
    if ($LASTEXITCODE -ne 0) {
        throw "[librarian] Could not list models from the configured Docker Ollama service."
    }
    $available = @($modelList | Select-Object -Skip 1 | ForEach-Object {
        ($_.Trim() -split '\s+')[0]
    })
    $missing = @($models | Where-Object {
        $expected = $_
        -not ($available | Where-Object {
            $_ -eq $expected -or ($expected -notmatch ':' -and $_ -eq "${expected}:latest")
        })
    })
    if ($missing.Count -gt 0) {
        Write-Error "[librarian] Configured Docker Ollama models are unavailable after initialization: $($missing -join ', ')"
        Write-Error "[librarian] Docker Ollama models currently available:"
        $modelList | Write-Error
        throw "[librarian] Docker Ollama model verification failed."
    }
}

if ($selection.docker_ollama_enabled) {
    $composePrefix += @("--profile", "docker-ollama")
    $build = @()
    if (-not $NoBuild) { $build += "--build" }
    & docker @composePrefix up @build -d opensearch ollama
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & docker @composePrefix up @build -d ollama-init
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Wait-OllamaInit -ComposePrefix $composePrefix
    Confirm-DockerOllamaModels -ComposePrefix $composePrefix
}

$start = @("up")
if (-not $NoBuild) { $start += "--build" }
if (-not $Foreground) { $start += "-d" }
$start += "api", "web"
if ($WithWorkers) { $start += "summary-worker" }
& docker @composePrefix @start
if ($LASTEXITCODE -eq 0) {
    Write-Host "[librarian] Stack started. API: http://localhost:$($selection.api_port)"
    Write-Host "[librarian] Web UI: http://localhost:$($selection.web_port)"
    Write-Host "[librarian] Inspect readiness with: docker compose ps"
}
exit $LASTEXITCODE
