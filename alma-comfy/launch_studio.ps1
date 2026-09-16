$ErrorActionPreference = "Stop"

$studioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$studioScript = Join-Path $studioRoot "studio_server.py"
$logRoot = Join-Path $studioRoot "logs"
$stdoutLog = Join-Path $logRoot "studio.out.log"
$stderrLog = Join-Path $logRoot "studio.err.log"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and
    ($_.CommandLine.Contains($studioScript) -or
     ($_.CommandLine -match '(^|[\\/\s])studio_server\.py([\s"]|$)'))
}
if ($existing) {
    if (@($existing).Count -ne 1) {
        throw "More than one ALMA Studio process exists; refusing to guess."
    }
    $listener = Get-NetTCPConnection -State Listen -LocalAddress "127.0.0.1" -LocalPort 8810 -ErrorAction SilentlyContinue
    if (-not $listener -or $listener.OwningProcess -ne $existing.ProcessId) {
        throw "An ALMA Studio process exists but does not own loopback port 8810."
    }
    $manifest = Invoke-RestMethod -Uri "http://127.0.0.1:8810/api/manifest" -TimeoutSec 10
    if (($manifest.nodes.id -join ',') -ne 'dgx3,dgx4') {
        throw "The running Studio violates the DGX3/DGX4 worker allocation."
    }
    Write-Output ("Canonical ALMA Studio already healthy: PID " + $existing.ProcessId)
    exit 0
}

$python = (Get-Command python.exe).Source
$process = Start-Process `
    -FilePath $python `
    -ArgumentList @("-u", $studioScript, "--host", "127.0.0.1", "--port", "8810") `
    -WorkingDirectory $studioRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 250
    try {
        $manifest = Invoke-RestMethod -Uri "http://127.0.0.1:8810/api/manifest" -TimeoutSec 3
    }
    catch {
        $manifest = $null
    }
} until (($manifest -and ($manifest.nodes.id -join ',') -eq 'dgx3,dgx4') -or (Get-Date) -ge $deadline -or $process.HasExited)

if (-not $manifest -or ($manifest.nodes.id -join ',') -ne 'dgx3,dgx4') {
    throw "ALMA Studio did not pass the DGX3/DGX4 allocation gate."
}
Write-Output ("ALMA Studio started: PID " + $process.Id)
Write-Output ("Logs: " + $stdoutLog + " and " + $stderrLog)
