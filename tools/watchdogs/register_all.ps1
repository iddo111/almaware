$WD = "D:\CLAUDE\tools\watchdogs"
$PY = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PY) { $PY = "python" }
$HK = "D:\CLAUDE\tools\haiku-healthcheck\haiku_healthcheck.py"
$PS = "powershell.exe"

function RegTask($name, $script_or_exe, $args_str, $interval_min) {
    # Remove existing
    schtasks /delete /tn $name /f 2>$null | Out-Null

    # Create with logon trigger + repeat
    $repeat = "PT${interval_min}M"
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>$name</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
    <TimeTrigger>
      <Repetition>
        <Interval>$repeat</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2000-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$script_or_exe</Command>
      <Arguments>$args_str</Arguments>
    </Exec>
  </Actions>
</Task>
"@
    $tmpXml = [System.IO.Path]::GetTempFileName() + ".xml"
    [System.IO.File]::WriteAllText($tmpXml, $xml, [System.Text.Encoding]::Unicode)
    $out = schtasks /create /tn $name /xml $tmpXml /f 2>&1
    Remove-Item $tmpXml -Force -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK  $name (every ${interval_min}min)"
    } else {
        Write-Host "  ERR $name : $out"
    }
}

Write-Host "Registering watchdogs and Haiku health check..."
RegTask "CpuHeatWatchdog"  $PS "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$WD\cpu_heat_watchdog.ps1`"" 1
RegTask "GpuHeatWatchdog"  $PS "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$WD\gpu_heat_watchdog.ps1`"" 1
RegTask "DiskWatchdog"     $PS "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$WD\disk_watchdog.ps1`"" 1
RegTask "PopupWatchdog"    $PS "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$WD\popup_watchdog.ps1`"" 1
RegTask "HaikuHealthCheck" $PY "`"$HK`"" 30

Write-Host ""
Write-Host "Status:"
schtasks /query /fo LIST /tn "CpuHeatWatchdog"  2>$null | Select-String "Status"
schtasks /query /fo LIST /tn "GpuHeatWatchdog"  2>$null | Select-String "Status"
schtasks /query /fo LIST /tn "DiskWatchdog"     2>$null | Select-String "Status"
schtasks /query /fo LIST /tn "PopupWatchdog"    2>$null | Select-String "Status"
schtasks /query /fo LIST /tn "HaikuHealthCheck" 2>$null | Select-String "Status"
