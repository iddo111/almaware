# ELEVATE-MIC.ps1 — make the ALMA mic run elevated so it can type into Grok (admin windows).
# Launched (already elevated) by RUN-ELEVATE-MIC.bat. Safe: only touches the mic (gui.py).

# 1. stop any current (non-elevated) mic so we don't get double-typing
Get-CimInstance Win32_Process -Filter "name='pythonw.exe'" |
  Where-Object { $_.CommandLine -like '*gui.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# 2. register an elevated scheduled task for the mic (auto-runs at login, highest privileges)
$py = "C:\Users\<user>\AppData\Local\Programs\Python\Python313\pythonw.exe"
$action    = New-ScheduledTaskAction -Execute $py -Argument "gui.py" -WorkingDirectory "D:\CLAUDE\alma-mic"
$principal = New-ScheduledTaskPrincipal -UserId ($env:USERDOMAIN + "\" + $env:USERNAME) -LogonType Interactive -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "ALMA-MIC" -Action $action -Principal $principal -Settings $settings -Force | Out-Null

# 3. start it now (elevated, no further UAC)
Start-ScheduledTask -TaskName "ALMA-MIC"

Write-Host ""
Write-Host "  OK - ALMA-MIC now runs ELEVATED and can type into Grok." -ForegroundColor Green
Write-Host "  It will also auto-start elevated on every login."
Write-Host "  (Test: focus Grok, dictate a sentence - it should appear.)"
Write-Host ""
Start-Sleep -Seconds 6
