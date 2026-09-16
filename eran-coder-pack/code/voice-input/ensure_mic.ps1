# ensure_mic.ps1 - ALMAWARE diamond always-on: register the Hebrew mic watchdog.
#
# Registers (idempotently) a Scheduled Task "ALMAWARE-HebMic-Diamond" that runs
# supervisor.py at logon. The supervisor keeps voice_input.py alive across crashes;
# this task keeps the supervisor itself alive across logon / reboot.
#
# Run once (elevated not required for a per-user logon task):
#   powershell -ExecutionPolicy Bypass -File D:\CLAUDE\voice-input\ensure_mic.ps1
#
# לזכרה של עלמה ז״ל - iddoperez.ai
$ErrorActionPreference = 'Stop'

$taskName = 'ALMAWARE-HebMic-Diamond'
$py       = 'C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe'
$dir      = 'D:\CLAUDE\voice-input'
$script   = Join-Path $dir 'supervisor.py'

if (-not (Test-Path $py)) {
  Write-Warning "Python not found at $py - task will be registered but may not run."
}
if (-not (Test-Path $script)) {
  throw "supervisor.py not found at $script - aborting registration."
}

# Run supervisor.py from the project dir. -WorkingDirectory keeps relative imports
# (mic/router/transcribe/...) and the history/ log path resolving correctly.
$action = New-ScheduledTaskAction -Execute $py -Argument "`"$script`"" -WorkingDirectory $dir

# At-logon trigger so the always-on mic comes back after every sign-in / reboot.
$trigger = New-ScheduledTaskTrigger -AtLogOn

# Run as the current interactive user (the mic types into the user's focused window,
# so it must run in the interactive session, not as SYSTEM).
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
  -LogonType Interactive -RunLevel Limited

# Diamond settings: restart the *task* if it ever stops, no execution time limit
# (always-on), allow on battery, and don't let an existing instance block a new one.
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -MultipleInstances IgnoreNew

# Remove any prior registration so re-running this script is idempotent.
try {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
  Write-Host "Removed existing task '$taskName' (re-registering)."
} catch {
  # not registered yet - fine
}

Register-ScheduledTask -TaskName $taskName `
  -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
  -Description 'ALMAWARE diamond always-on Hebrew PC mic watchdog (supervisor.py -> voice_input.py).' | Out-Null

Write-Host "Registered Scheduled Task '$taskName' (at logon)."
Write-Host "Start it now with:  Start-ScheduledTask -TaskName '$taskName'"
Write-Host "Or launch directly: $dir\start_mic_diamond.bat"
