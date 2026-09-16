# fix-bot-fixerbot-trigger-collision.ps1
#
# Root cause: Bot-FixerBot uses start-keeper.ps1 (a `while ($true)` loop).
# It registers TWO triggers:
#   1. AtLogOn (correct — survives reboot)
#   2. -Once -RepetitionInterval 5min   (WRONG — re-fires every 5 min)
# With MultipleInstancesPolicy=IgnoreNew, the 5-min trigger keeps
# colliding with the already-running keeper. Task Scheduler reports
# LastTaskResult = 0x800710E0 ("operation not queueable / task already
# running, new instance ignored"). The inner fixer is healthy
# (heartbeat + TRACKER.txt are fresh) — only the schtask's LastResult
# is cosmetically dirty.
#
# Fix: drop the 5-min repetition trigger. AtLogon + RestartCount=5
# already covers respawn cases. Run-now after the fix to clear the
# error code.
#
# Reversal: re-run register.ps1.

$ErrorActionPreference = 'Stop'
$taskName = 'Bot-FixerBot'

Write-Host "[fix] Bot-FixerBot trigger-collision repair starting"

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop

# Build replacement: keep only the AtLogOn trigger, keep the same action,
# settings, and principal.
$action    = $task.Actions[0]
$settings  = $task.Settings
$principal = $task.Principal

# Single trigger — AtLogOn for iddo1
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:COMPUTERNAME\iddo1"

# Re-register cleanly (Set-ScheduledTask cannot remove triggers)
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Register-ScheduledTask -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Bot-FixerBot - permanent meta-watcher for popup/audio/schtask/disk/WA/Alma health (every 3 min via keeper while-loop). " +
                  "AtLogOn-only trigger; 5-min repetition trigger removed 2026-04-30 to fix 0x800710E0 collision.") | Out-Null

Write-Host "[fix] re-registered with AtLogOn-only trigger"

# Run-now to clear stale LastTaskResult. Note: a keeper instance is
# already running (started at logon); the new instance will be
# ignored by MIP=IgnoreNew, but the LastTaskResult should reset to 0
# because we just executed Start-ScheduledTask manually.
# Better: kick off a one-time "freshness check" by leaving the
# already-running keeper alone and just relying on its next inner
# tick to refresh heartbeat. But to update LastTaskResult we need
# a clean fire. Strategy: stop the running task, start it fresh.

Write-Host "[fix] stopping current keeper instance"
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "[fix] starting fresh keeper instance"
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 4

$info = Get-ScheduledTaskInfo -TaskName $taskName
$state = (Get-ScheduledTask -TaskName $taskName).State
Write-Host ("[fix] AFTER: State={0} LastTaskResult=0x{1:X} LastRun={2}" -f `
    $state, [uint32]$info.LastTaskResult, $info.LastRunTime)

# Confirm heartbeat is fresh
$hb = 'D:\CLAUDE\fixer-bot\heartbeat.txt'
if (Test-Path $hb) {
    $hbAge = (Get-Date) - (Get-Item $hb).LastWriteTime
    Write-Host ("[fix] heartbeat age = {0:F0}s" -f $hbAge.TotalSeconds)
}

Write-Host "[fix] done"
