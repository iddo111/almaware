# Installs only the conservative ALMAWARE core monitor. It does not install or
# invoke the older suite watchdog, and it never manages DGX/model services.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'check-almaware-core.ps1'
$pwsh = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
if (-not $pwsh) { $pwsh = (Get-Command powershell.exe -ErrorAction Stop).Source }

$arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`" -Repair -WriteLog -Json"
$action = New-ScheduledTaskAction -Execute $pwsh -Argument $arguments
$atLogon = New-ScheduledTaskTrigger -AtLogOn
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 2)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

try {
    Register-ScheduledTask -TaskName 'ALMAWARE-Core-Monitor' -Action $action `
        -Trigger @($atLogon, $repeat) -Settings $settings `
        -Description 'Conservative local ALMAWARE Cockpit collector monitor; starts only when no collector process is alive.' `
        -Force | Out-Null
    Write-Host 'Registered scheduled task: ALMAWARE-Core-Monitor'
}
catch {
    if ($_.Exception.Message -notmatch '(?i)access.*denied|denied.*access') { throw }
    # Some managed Windows sessions deny Task Scheduler registration even for
    # user tasks. Use the current-user Run key as a non-admin fallback. The
    # monitor's named mutex prevents duplicate loops.
    $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    $loopArguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`" -Loop -Repair -WriteLog -Json -IntervalSeconds 120"
    $command = "`"$pwsh`" $loopArguments"
    New-Item -Path $runKey -Force | Out-Null
    New-ItemProperty -Path $runKey -Name 'ALMAWARE-Core-Monitor' `
        -Value $command -PropertyType String -Force | Out-Null
    Write-Host 'Task Scheduler denied access; installed HKCU Run fallback: ALMAWARE-Core-Monitor'
}
