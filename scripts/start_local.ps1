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
if ($selection.docker_ollama_enabled) {
    $composePrefix += @("--profile", "docker-ollama")
    $build = @()
    if (-not $NoBuild) { $build += "--build" }
    & docker @composePrefix up @build -d opensearch ollama
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & docker @composePrefix up @build -d ollama-init
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & docker @composePrefix wait ollama-init
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
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
