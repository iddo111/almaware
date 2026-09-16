@echo off
echo Installing watchdogs and Haiku health check...
powershell -ExecutionPolicy Bypass -Command ^
  "$WD='D:\CLAUDE\tools\watchdogs'; $PY=(Get-Command python).Source; $HK='D:\CLAUDE\tools\haiku-healthcheck\haiku_healthcheck.py'; $PS='powershell.exe'; ^
  $tasks=@( ^
    @{N='CpuHeatWatchdog';E=$PS;A=\"-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File '$WD\cpu_heat_watchdog.ps1'\";M=1}, ^
    @{N='GpuHeatWatchdog';E=$PS;A=\"-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File '$WD\gpu_heat_watchdog.ps1'\";M=1}, ^
    @{N='DiskWatchdog';E=$PS;A=\"-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File '$WD\disk_watchdog.ps1'\";M=1}, ^
    @{N='PopupWatchdog';E=$PS;A=\"-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File '$WD\popup_watchdog.ps1'\";M=1}, ^
    @{N='HaikuHealthCheck';E=$PY;A=\"'$HK'\";M=30} ^
  ); ^
  foreach($t in $tasks){ ^
    Unregister-ScheduledTask -TaskName $t.N -Confirm:$false -EA SilentlyContinue; ^
    $a=New-ScheduledTaskAction -Execute $t.E -Argument $t.A; ^
    $tr=@((New-ScheduledTaskTrigger -AtLogOn),(New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes $t.M) -Once -At '12:00am')); ^
    $s=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 0); ^
    Register-ScheduledTask -TaskName $t.N -Action $a -Trigger $tr -Settings $s -Force | Out-Null; ^
    Write-Host 'OK' $t.N ^
  }"
echo.
echo Done. Press any key to close.
pause
