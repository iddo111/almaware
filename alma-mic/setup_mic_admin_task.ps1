# One-time elevated setup: registers ALMA-MIC-Admin so the mic can always run elevated with no UAC prompt.
$act  = New-ScheduledTaskAction -Execute 'D:\CLAUDE\alma-mic\mic_admin_launch.bat'
$prin = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
$set  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'ALMA-MIC-Admin' -Action $act -Principal $prin -Settings $set -Force
Write-Host "ALMA-MIC-Admin registered. Use Desktop\MIC.bat to start the mic elevated with no UAC."
Start-Sleep -Seconds 3
