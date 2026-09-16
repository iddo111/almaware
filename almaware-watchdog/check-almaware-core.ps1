# ALMAWARE core status monitor.
# Default mode is read-only. -Repair may start the HUD collector only when no
# collector PID is alive. It never stops, kills, or restarts a live process and
# it performs no network or DGX actions.
[CmdletBinding()]
param(
    [switch]$Repair,
    [switch]$WriteLog,
    [switch]$Json,
    [switch]$Loop,
    [ValidateRange(10, 3600)]
    [int]$FreshSeconds = 30,
    [ValidateRange(1, 60)]
    [int]$WaitSeconds = 15,
    [ValidateRange(30, 3600)]
    [int]$IntervalSeconds = 120
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$hudDir = Join-Path $repoRoot 'almaware-hud'
$collectorPath = Join-Path $hudDir 'collector.py'
$pidPath = Join-Path $hudDir 'collector.pid'
$statusPath = Join-Path $repoRoot 'almaware-cockpit\status.json'
$logPath = Join-Path $PSScriptRoot 'core-monitor.log'

function Read-CollectorState {
    $pidValue = $null
    $processAlive = $false
    if (Test-Path -LiteralPath $pidPath) {
        $rawPid = (Get-Content -Raw -LiteralPath $pidPath).Trim()
        if ($rawPid -match '^\d+$') {
            $pidValue = [int]$rawPid
            $processAlive = $null -ne (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)
        }
    }

    $statusValid = $false
    $statusFresh = $false
    $statusAgeSeconds = $null
    $statusState = $null
    $statusPid = $null
    $statusError = $null
    if (Test-Path -LiteralPath $statusPath) {
        try {
            $statusItem = Get-Item -LiteralPath $statusPath
            $statusAgeSeconds = [math]::Round(((Get-Date) - $statusItem.LastWriteTime).TotalSeconds, 1)
            $status = Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json
            $statusValid = $null -ne $status.meta
            $statusState = $status.meta.state
            $statusPid = $status.meta.collector_pid
            $statusFresh = $statusValid -and ($statusAgeSeconds -le $FreshSeconds)
        }
        catch {
            $statusError = $_.Exception.Message
        }
    }
    else {
        $statusError = 'status.json is missing'
    }

    $healthy = $processAlive -and $statusFresh -and ($statusPid -eq $pidValue)
    $reason = if ($healthy) {
        'healthy'
    }
    elseif ($processAlive -and -not $statusFresh) {
        'collector_alive_status_stale_manual_check_required'
    }
    elseif ($processAlive) {
        'collector_alive_status_invalid_manual_check_required'
    }
    elseif ($statusFresh) {
        'collector_not_running_status_recent'
    }
    else {
        'collector_not_running_status_stale_or_missing'
    }

    [pscustomobject]@{
        checked_at = (Get-Date).ToString('o')
        healthy = $healthy
        reason = $reason
        collector_pid = $pidValue
        process_alive = $processAlive
        status_path = $statusPath
        status_valid = $statusValid
        status_fresh = $statusFresh
        status_age_seconds = $statusAgeSeconds
        status_state = $statusState
        status_pid = $statusPid
        status_error = $statusError
    }
}

function Start-CollectorConservatively {
    $pythonw = 'C:\Users\<user>\AppData\Local\Programs\Python\Python313\pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonw)) {
        $pythonw = (Get-Command pythonw.exe -ErrorAction Stop).Source
    }
    Start-Process -FilePath $pythonw `
        -ArgumentList @($collectorPath, '--log-level', 'INFO') `
        -WorkingDirectory $hudDir -WindowStyle Hidden | Out-Null
}

function Invoke-CoreMonitorPass {
    $before = Read-CollectorState
    $action = 'none'
    $result = $before

    if ($Repair -and -not $before.healthy) {
        if ($before.process_alive) {
            # A live-but-stale collector may be blocked in a probe. Starting another
            # writer would make diagnosis worse, so leave it untouched.
            $action = 'refused_live_process'
        }
        else {
            $action = 'start_requested'
            Start-CollectorConservatively
            $deadline = (Get-Date).AddSeconds($WaitSeconds)
            do {
                Start-Sleep -Seconds 1
                $result = Read-CollectorState
            } while (-not $result.healthy -and (Get-Date) -lt $deadline)
            if ($result.healthy) { $action = 'started' } else { $action = 'start_failed' }
        }
    }

    $report = [ordered]@{
        monitor = 'ALMAWARE-Core-Monitor'
        action = $action
        healthy = $result.healthy
        reason = $result.reason
        checked_at = $result.checked_at
        collector_pid = $result.collector_pid
        process_alive = $result.process_alive
        status_fresh = $result.status_fresh
        status_age_seconds = $result.status_age_seconds
        status_state = $result.status_state
        status_pid = $result.status_pid
        status_error = $result.status_error
    }

    [pscustomobject]@{ Report = $report; Healthy = [bool]$result.healthy }
}

$monitorMutex = $null
if ($Loop) {
    $createdNew = $false
    $monitorMutex = [System.Threading.Mutex]::new(
        $true, 'Local\ALMAWARE_CORE_MONITOR_V1', [ref]$createdNew
    )
    if (-not $createdNew) { exit 0 }
}

try {
    do {
        $pass = Invoke-CoreMonitorPass
        $jsonLine = $pass.Report | ConvertTo-Json -Compress
        if ($WriteLog) { Add-Content -LiteralPath $logPath -Value $jsonLine }
        if ($Json) { $jsonLine } else { [pscustomobject]$pass.Report | Format-List }

        if (-not $Loop) {
            if (-not $pass.Healthy) { exit 1 }
            break
        }
        Start-Sleep -Seconds $IntervalSeconds
    } while ($true)
}
finally {
    if ($null -ne $monitorMutex) {
        try { $monitorMutex.ReleaseMutex() } catch { }
        $monitorMutex.Dispose()
    }
}
