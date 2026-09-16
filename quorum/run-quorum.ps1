# לזכרה של עלמה ז״ל
# QUORUM launcher — starts the שקלא-וטריא server on loopback.
# SAFE DEFAULT: the engine is inert (config.ENABLED=False). To let it reach models
# for a real debate, either flip ENABLED in config.py or run with -Enable.
param(
    [switch]$Enable,
    [int]$Port = 8099,
    [string]$HarnessUrl = $env:ALMA_HARNESS_URL
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$env:QUORUM_PORT = "$Port"
if ($HarnessUrl) {
    $env:ALMA_HARNESS_URL = $HarnessUrl
}
if ($Enable) {
    $env:QUORUM_ENABLED = "1"
    Write-Host "[QUORUM] ENABLED=1 (will reach models). Ctrl+C to stop." -ForegroundColor Yellow
} else {
    Write-Host "[QUORUM] inert (ENABLED=False). UI + status only. Use -Enable for a live debate." -ForegroundColor Cyan
}

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { Write-Host "[QUORUM] python not found on PATH" -ForegroundColor Red; exit 1 }

Write-Host "[QUORUM] http://127.0.0.1:$Port  (לזכרה של עלמה ז״ל)" -ForegroundColor Green
& $py "$here\server.py"
