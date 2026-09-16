$ErrorActionPreference = 'Continue'
$Dir  = 'D:\CLAUDE\web-ai-harness'
$Log  = Join-Path $Dir 'logs\router-service.log'
$Port = 8801
New-Item -ItemType Directory -Force -Path (Split-Path $Log) | Out-Null

function Say($m) {
    $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'), $m
    Add-Content -Path $Log -Value $line -Encoding utf8
    # keep the log from growing without bound over months of uptime
    if ((Get-Item $Log -EA SilentlyContinue).Length -gt 5MB) {
        $keep = Get-Content $Log -Tail 2000
        Set-Content -Path $Log -Value $keep -Encoding utf8
    }
}

Say "watchdog starting (pid $PID)"
$proc = $null

while ($true) {
    $alive = $false
    if ($proc -and -not $proc.HasExited) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" `
                 -Headers @{ Authorization = "Bearer $env:COLI_API_KEY" } `
                 -TimeoutSec 15 -UseBasicParsing
            # 200 = fine. 401 also proves it is serving: the auth layer answered,
            # which is a live router, not a dead port.
            if ($r.StatusCode -eq 200 -or $r.StatusCode -eq 401) { $alive = $true }
        } catch {
            if ($_.Exception.Response.StatusCode.value__ -eq 401) { $alive = $true }
        }
        if (-not $alive) { Say "health check failed - recycling"; try { $proc.Kill() } catch {} ; Start-Sleep 3 }
    }

    if (-not $alive) {
        # Clear anything squatting the port. Windows lets two processes bind the
        # same port via SO_REUSEADDR and both answer, which produces baffling
        # intermittent failures - so make sure we are the only one.
        Get-NetTCPConnection -LocalPort $Port -State Listen -EA SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }
        Start-Sleep 2

        Say "starting router"
        $proc = Start-Process -FilePath 'py' `
            -ArgumentList '-3.13', (Join-Path $Dir 'glm_router.py') `
            -WorkingDirectory $Dir -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $Dir 'logs\router-stdout.log') `
            -RedirectStandardError  (Join-Path $Dir 'logs\router-stderr.log')
        Say "started pid $($proc.Id)"
        Start-Sleep 20   # let the health poller find its backends before we judge it
    }

    Start-Sleep 30
}
