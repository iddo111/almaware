# register_task.ps1 - register Bank-Backup-Orchestrator scheduled task.
# Fires every 6 hours, runs hidden, no UAC.
# ASCII only.
$ErrorActionPreference = 'Stop'

$taskName = 'Bank-Backup-Orchestrator'

# Build action: python orchestrator.py
$pythonExe = (Get-Command python -ErrorAction Stop).Source
$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument '"D:\CLAUDE\tools\bank_backup\orchestrator.py"' `
    -WorkingDirectory 'D:\CLAUDE\tools\bank_backup'

# Trigger: every 6 hours, starting in 5 minutes
$start = (Get-Date).AddMinutes(5)
$trigger = New-ScheduledTaskTrigger -Once -At $start `
    -RepetitionInterval (New-TimeSpan -Hours 6) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

# Run hidden, even when user not logged in (so it survives the night)
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType S4U `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 5) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -Hidden

# Unregister existing (idempotent)
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "Unregistering existing task..."
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description 'Bank-grade unified backup: PC + laptop + A70 + git + gdrive + Mint SSD. Fires every 6h.'

Write-Output "Registered. Next run: $start"
Get-ScheduledTask -TaskName $taskName | Format-List TaskName, State
