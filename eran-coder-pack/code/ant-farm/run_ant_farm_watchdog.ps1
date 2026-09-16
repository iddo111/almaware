[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
$ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
$server = Join-Path $root "server.py"
$logDir = Join-Path $root "data\logs"
$watchdogLog = Join-Path $logDir "watchdog.log"
$serverLog = Join-Path $logDir "server.log"

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Write-WatchdogLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
    Add-Content -LiteralPath $watchdogLog -Value "$stamp $Message"
}

function Test-ListeningPort {
    param([int]$Port)
    # 2026-08-12 infra-rebuild Stage 1.3 (PHASE1-INFRA-INQUIRY.md): liveness truth is the
    # real-output probe on http://127.0.0.1:8765/api/health (Test-AntFarm below, server.py:396).
    # This occupancy guard must only count listeners that actually conflict with server.py's
    # 127.0.0.1 bind. tailscale serve holds tailnet addresses (100.x / fd7a:...) on this port
    # and livelocked this watchdog ("occupied; no takeover") while 127.0.0.1:8765 was free.
    $conflicting = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -in @('127.0.0.1', '0.0.0.0', '::', '::1') }
    return [bool]$conflicting
}

function Test-AntFarm {
    try {
        $health = Invoke-RestMethod `
            -Uri "http://127.0.0.1:8765/api/health" `
            -Method Get `
            -TimeoutSec 4
        return $health.service -eq "ok"
    }
    catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python was not found at $python"
}
if (-not (Test-Path -LiteralPath $server)) {
    throw "Ant Farm server was not found at $server"
}

Set-Location -LiteralPath $root
Write-WatchdogLog "Watchdog started as $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)."

while ($true) {
    try {
        if (-not (Test-ListeningPort -Port 11434)) {
            if (-not (Test-Path -LiteralPath $ollama)) {
                throw "Ollama was not found at $ollama"
            }
            Write-WatchdogLog "Ollama was not listening; starting it."
            Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
            Start-Sleep -Seconds 3
        }

        if (Test-AntFarm) {
            Start-Sleep -Seconds 10
            continue
        }

        if (Test-ListeningPort -Port 8765) {
            Write-WatchdogLog "Port 8765 is occupied by a process that did not pass Ant Farm health; no takeover attempted."
            Start-Sleep -Seconds 10
            continue
        }

        Write-WatchdogLog "Ant Farm was unavailable; starting server.py."
        & $python $server *>> $serverLog
        $exitCode = $LASTEXITCODE
        Write-WatchdogLog "server.py exited with code $exitCode; retrying."
    }
    catch {
        Write-WatchdogLog "Watchdog iteration failed: $($_.Exception.Message)"
    }

    Start-Sleep -Seconds 5
}
