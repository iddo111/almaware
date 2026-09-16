# Install a logon scheduled task that auto-starts the fully-auto Hebrew mic.
# Run from an elevated PowerShell:  powershell -ExecutionPolicy Bypass -File install-task.ps1
# Remove with:  Unregister-ScheduledTask -TaskName "Claude-HebrewMicAuto" -Confirm:$false
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$py   = (Get-Command python).Source
$script = Join-Path $here "voice_input.py"

$action  = New-ScheduledTaskAction -Execute $py -Argument "`"$script`" --vad --enter" -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName "Claude-HebrewMicAuto" -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal -Force -Description "Fully-auto Hebrew mic -> STT -> auto-type+Enter into focused window (ERAN-AAL)."
Write-Host "Installed scheduled task 'Claude-HebrewMicAuto' (runs at logon)." -ForegroundColor Green
