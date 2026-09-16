# Watchdog Status — prints scheduled task status + last 5 log lines for each watchdog

$tasks = @(
    @{ Name = "CpuHeatWatchdog"; Log = "D:\CLAUDE\tools\watchdogs\logs\cpu_heat.log";  Label = "CPU Heat Watchdog"  },
    @{ Name = "GpuHeatWatchdog"; Log = "D:\CLAUDE\tools\watchdogs\logs\gpu_heat.log";  Label = "GPU Heat Watchdog"  },
    @{ Name = "DiskWatchdog";    Log = "D:\CLAUDE\tools\watchdogs\logs\disk.log";       Label = "Disk Watchdog"      },
    @{ Name = "PopupWatchdog";   Log = "D:\CLAUDE\tools\watchdogs\logs\popup.log";      Label = "Popup Watchdog"     }
)

$sep = "=" * 70

foreach ($t in $tasks) {
    Write-Host ""
    Write-Host $sep
    Write-Host "  $($t.Label)  [$($t.Name)]"
    Write-Host $sep

    # Scheduled task status
    try {
        $task = Get-ScheduledTask -TaskName $t.Name -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -TaskName $t.Name -ErrorAction SilentlyContinue
        $state     = $task.State
        $lastRun   = if ($info.LastRunTime   -and $info.LastRunTime   -gt [datetime]"1900-01-01") { $info.LastRunTime.ToString("yyyy-MM-dd HH:mm:ss")   } else { "never" }
        $nextRun   = if ($info.NextRunTime   -and $info.NextRunTime   -gt [datetime]"1900-01-01") { $info.NextRunTime.ToString("yyyy-MM-dd HH:mm:ss")   } else { "n/a"   }
        $lastResult = $info.LastTaskResult
        Write-Host "  Task State   : $state"
        Write-Host "  Last Run     : $lastRun"
        Write-Host "  Last Result  : $lastResult (0 = success)"
        Write-Host "  Next Run     : $nextRun"
    } catch {
        Write-Host "  Task State   : NOT REGISTERED (run register_watchdogs.ps1)"
    }

    # Last 5 log lines
    Write-Host ""
    Write-Host "  Last 5 log lines ($($t.Log)):"
    if (Test-Path $t.Log) {
        $lines = Get-Content $t.Log -Tail 5
        if ($lines) {
            foreach ($line in $lines) { Write-Host "    $line" }
        } else {
            Write-Host "    (log is empty)"
        }
    } else {
        Write-Host "    (log file not found - watchdog has not run yet)"
    }
}

Write-Host ""
Write-Host $sep
Write-Host "  Status check complete - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host $sep
Write-Host ""
