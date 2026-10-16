param(
    [int]$Port = 8001,
    [string]$Graph = "premise_codex_demo",
    [switch]$PollGitHub
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Create the project .venv and install requirements.lock first."
}

# Process-local overrides: preserve .env and avoid a second GitHub poller by default.
$env:LLM_PROVIDER = "codex-cli"
$env:GRAPH_NAME = $Graph
$env:FALKORDB_HOST = "127.0.0.1"
$env:FALKORDB_PORT = "6379"
$env:PUBLIC_BASE_URL = "http://localhost:$Port"
$env:POLL_ENABLED = if ($PollGitHub) { "true" } else { "false" }
$env:AUTO_FIX_PR = if ($PollGitHub) { "true" } else { "false" }

if (-not $PollGitHub) {
    & $pythonExe -m premise.cli demo
    if ($LASTEXITCODE -ne 0) { throw "Could not prepare the separate Codex demo graph." }
}
Write-Host "Premise with local Codex CLI: http://localhost:$Port"
& $pythonExe -m premise.cli serve --web-port $Port
exit $LASTEXITCODE
