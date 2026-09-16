#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Installs the AudioWatchdog as a Windows Scheduled Task.
    Run this script once as Administrator.
#>

$TASK_NAME   = 'AudioWatchdog'
$SCRIPT_PATH = 'D:\CLAUDE\tools\audio-watchdog\audio_watchdog.ps1'
$CURRENT_USER = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

Write-Host "Installing AudioWatchdog Scheduled Task..."
Write-Host "  Script : $SCRIPT_PATH"
Write-Host "  RunAs  : $CURRENT_USER"

# Remove existing task if present
Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false -ErrorAction SilentlyContinue

# Action: run PowerShell hidden
$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$SCRIPT_PATH`""

# Trigger 1: At logon (for the current user)
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $CURRENT_USER

# Trigger 2: Daily repeating every 1 minute (covers the case watchdog crashes)
# The watchdog itself loops every 30s, but we also restart it every minute as insurance.
$triggerRepeat = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 1) `
    -Once -At (Get-Date) -RepetitionDuration ([TimeSpan]::MaxValue)

# Settings: allow multiple instances (Stop existing, start new)
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -DisallowDemandStart:$false

# Principal: run as current user, only when logged in
$principal = New-ScheduledTaskPrincipal `
    -UserId $CURRENT_USER `
    -LogonType Interactive `
    -RunLevel Highest

# Register with BOTH triggers
Register-ScheduledTask `
    -TaskName $TASK_NAME `
    -Action $action `
    -Trigger @($triggerLogon, $triggerRepeat) `
    -Settings $settings `
    -Principal $principal `
    -Description "Monitors and auto-corrects Windows audio default devices to keep Focusrite Scarlett Solo USB as Default Playback and Default Communications." `
    -Force

Write-Host ""
Write-Host "Task registered. Starting it now..."
Start-ScheduledTask -TaskName $TASK_NAME

$status = (Get-ScheduledTask -TaskName $TASK_NAME).State
Write-Host "Task state: $status"
Write-Host ""
Write-Host "Done. The AudioWatchdog is now running."
Write-Host "Log file: D:\CLAUDE\tools\audio-watchdog\audio_watchdog.log"
