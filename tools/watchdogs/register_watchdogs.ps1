# Register all 4 watchdog scheduled tasks
# Run this script once (as the current user) to install the tasks.
# Re-run to update/replace existing registrations.

$WatchdogDir = "D:\CLAUDE\tools\watchdogs"
$PowerShell  = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

$watchdogs = @(
    @{ TaskName = "CpuHeatWatchdog"; Script = "$WatchdogDir\cpu_heat_watchdog.ps1" },
    @{ TaskName = "GpuHeatWatchdog"; Script = "$WatchdogDir\gpu_heat_watchdog.ps1" },
    @{ TaskName = "DiskWatchdog";    Script = "$WatchdogDir\disk_watchdog.ps1"     },
    @{ TaskName = "PopupWatchdog";   Script = "$WatchdogDir\popup_watchdog.ps1"    }
)

foreach ($w in $watchdogs) {
    Write-Host "Registering $($w.TaskName)..."

    # Remove existing task silently
    Unregister-ScheduledTask -TaskName $w.TaskName -Confirm:$false -ErrorAction SilentlyContinue

    $action = New-ScheduledTaskAction `
        -Execute $PowerShell `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$($w.Script)`""

    # Trigger 1: at logon
    $triggerLogon = New-ScheduledTaskTrigger -AtLogOn

    # Trigger 2: repeat every 1 minute indefinitely (daily trigger + repetition)
    $triggerRepeat = New-ScheduledTaskTrigger -Daily -At "00:00"
    $triggerRepeat.Repetition = New-Object Microsoft.Management.Infrastructure.CimInstance -ArgumentList @(
        "MSFT_TaskRepetitionPattern", "Root/Microsoft/Windows/TaskScheduler"
    )

    # Build repetition via XML approach — most reliable cross-version method
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
    <TimeTrigger>
      <Repetition>
        <Interval>PT1M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2000-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <Hidden>true</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$PowerShell</Command>
      <Arguments>-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "$($w.Script)"</Arguments>
    </Exec>
  </Actions>
</Task>
"@

    try {
        Register-ScheduledTask -TaskName $w.TaskName -Xml $xml -Force | Out-Null
        Write-Host "  OK — $($w.TaskName) registered"
    } catch {
        Write-Host "  ERROR registering $($w.TaskName): $_"
    }
}

Write-Host ""
Write-Host "Done. Run watchdog_status.ps1 to verify."
