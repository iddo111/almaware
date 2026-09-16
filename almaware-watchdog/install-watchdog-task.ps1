# Registers the ALMAWARE-Watchdog scheduled task: at logon + every 2 minutes,
# run one safe health pass (starts any down service, kills nothing).
# Reversible: Unregister-ScheduledTask -TaskName 'ALMAWARE-Watchdog' -Confirm:$false
$ErrorActionPreference = 'Stop'
$script = 'D:\CLAUDE\almaware-watchdog\ensure-almaware-suite.ps1'
$exe = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $exe) { $exe = (Get-Command powershell).Source }

$action  = New-ScheduledTaskAction -Execute $exe `
             -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" -Once"
$tLogon  = New-ScheduledTaskTrigger -AtLogOn
$tRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
             -RepetitionInterval (New-TimeSpan -Minutes 2)
$set     = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
             -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName 'ALMAWARE-Watchdog' -Action $action -Trigger @($tLogon,$tRepeat) `
  -Settings $set -Description 'Keeps the ALMAWARE always-on suite alive (mic/Quorum/Shiri/dashboard). Safe, additive, restarts-only.' -Force | Out-Null
Write-Host 'Registered scheduled task: ALMAWARE-Watchdog (logon + every 2 min).'
