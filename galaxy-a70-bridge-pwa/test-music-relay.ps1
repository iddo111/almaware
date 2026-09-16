param(
    [switch]$ProbeWasapi
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run setup-music-relay.ps1 first' }

Push-Location $project
try {
    & npm test
    if ($LASTEXITCODE -ne 0) { throw 'Node safety tests failed' }
    & $python '.\test\webrtc_smoke.py'
    if ($LASTEXITCODE -ne 0) { throw 'WebRTC Opus smoke test failed' }
    if ($ProbeWasapi) {
        & $python '.\test\webrtc_smoke.py' --source loopback
        if ($LASTEXITCODE -ne 0) { throw 'Integrated WASAPI-to-WebRTC test failed' }
    }
} finally {
    Pop-Location
}
