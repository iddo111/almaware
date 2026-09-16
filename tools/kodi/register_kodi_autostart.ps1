# Kodi Auto-Start Registration Script
# Configures Windows Scheduled Task for auto-start on boot
# For: iddoperez.ai

# Requires: Run as Administrator

#Requires -RunAsAdministrator

$TaskName = "KodiAutoStart"
$TaskPath = "\iddoperez.ai\"
$KodiScriptPath = "D:\CLAUDE\tools\kodi\start_kodi.cmd"
$KodiExePath = "D:\CLAUDE\tools\kodi\Kodi-portable\kodi.exe"

Write-Host "Kodi Auto-Start Configuration" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
Write-Host ""

# Verify script and executable exist
if (-not (Test-Path $KodiScriptPath)) {
    Write-Host "ERROR: Launcher script not found at: $KodiScriptPath" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $KodiExePath)) {
    Write-Host "ERROR: Kodi executable not found at: $KodiExePath" -ForegroundColor Red
    Write-Host "Please extract Kodi portable and create portable_mode file first." -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ Kodi launcher verified: $KodiScriptPath" -ForegroundColor Green
Write-Host "✓ Kodi executable verified: $KodiExePath" -ForegroundColor Green
Write-Host ""

# Check if task already exists
$ExistingTask = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue

if ($ExistingTask) {
    Write-Host "Scheduled task '$TaskName' already exists." -ForegroundColor Yellow
    Write-Host "Removing old task to create fresh configuration..." -ForegroundColor Yellow
    try {
        Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "✓ Old task removed" -ForegroundColor Green
    } catch {
        Write-Host "ERROR: Could not remove existing task. $_" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "Creating new scheduled task..." -ForegroundColor Cyan

# Create trigger (at system startup)
$Trigger = New-ScheduledTaskTrigger -AtStartup

# Create action (run the launcher script, no window)
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$KodiScriptPath`"" `
    -WorkingDirectory "D:\CLAUDE\tools\kodi"

# Create settings (allow run-on-demand, auto-restart on failure, run with highest privileges)
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -RunOnlyIfNetworkAvailable:$false

# Register the task
try {
    Register-ScheduledTask `
        -TaskPath $TaskPath `
        -TaskName $TaskName `
        -Trigger $Trigger `
        -Action $Action `
        -Settings $Settings `
        -RunLevel Highest `
        -Description "Launches Kodi Media Center on system startup (portable mode)" `
        -Force `
        -ErrorAction Stop | Out-Null

    Write-Host "✓ Scheduled task created successfully" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Could not create scheduled task. $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Task Configuration Summary:" -ForegroundColor Cyan
Write-Host "  Task Name:    $TaskName" -ForegroundColor White
Write-Host "  Task Path:    $TaskPath" -ForegroundColor White
Write-Host "  Trigger:      At System Startup" -ForegroundColor White
Write-Host "  Action:       Execute launcher script" -ForegroundColor White
Write-Host "  Run Level:    System (highest privileges)" -ForegroundColor White
Write-Host "  Auto-Restart: Yes (up to 3 times, 5-min intervals)" -ForegroundColor White
Write-Host ""

# Enable the task
try {
    Enable-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction Stop | Out-Null
    Write-Host "✓ Task enabled and ready" -ForegroundColor Green
} catch {
    Write-Host "WARNING: Could not enable task. $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Restart Windows to verify auto-start works"
Write-Host "  2. Kodi will launch automatically after boot"
Write-Host "  3. Access web interface at: http://localhost:8090"
Write-Host ""
Write-Host "To Disable Auto-Start Later:" -ForegroundColor Yellow
Write-Host "  Run (as Admin): schtasks /delete /tn `"iddoperez.ai\KodiAutoStart`" /f" -ForegroundColor Gray
Write-Host ""
Write-Host "Configuration Complete!" -ForegroundColor Green
