[CmdletBinding()]
param(
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

$taskName = "ALMAWARE Ant Farm"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$watchdog = Join-Path $root "run_ant_farm_watchdog.ps1"
$powershell = (Get-Command powershell.exe -ErrorAction Stop).Source

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    if ($task.State -ne "Running") {
        Start-ScheduledTask -TaskName $taskName
    }
}
else {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watchdog`""
    Start-Process -FilePath $powershell -ArgumentList $arguments -WindowStyle Hidden
}

$deadline = (Get-Date).AddSeconds(30)
$health = $null
do {
    try {
        $health = Invoke-RestMethod `
            -Uri "http://127.0.0.1:8765/api/health" `
            -Method Get `
            -TimeoutSec 4
    }
    catch {
        Start-Sleep -Seconds 1
    }
} until (($health.service -eq "ok") -or ((Get-Date) -ge $deadline))

if ($health.service -ne "ok") {
    throw "Ant Farm did not become healthy within 30 seconds."
}

if (-not $NoOpen) {
    Start-Process "http://127.0.0.1:8765/"
}

$health | ConvertTo-Json -Depth 6
