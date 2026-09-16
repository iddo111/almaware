# Internal helper: registers the AudioWatchdog scheduled task
# Called by the bash installer - run with powershell -File

$TASK_NAME = 'AudioWatchdog'
$SCRIPT_PATH = 'D:\CLAUDE\tools\audio-watchdog\audio_watchdog.ps1'

# Delete existing
schtasks /Delete /TN $TASK_NAME /F 2>$null | Out-Null

# Build XML
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Monitors and auto-corrects audio defaults to keep Focusrite Scarlett Solo USB as Default Playback and Default Communications device.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
    <TimeTrigger>
      <Repetition>
        <Interval>PT1M</Interval>
        <Duration>P365D</Duration>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2026-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "$SCRIPT_PATH"</Arguments>
    </Exec>
  </Actions>
</Task>
"@

$xmlPath = "$env:TEMP\AudioWatchdog_task.xml"
[System.IO.File]::WriteAllText($xmlPath, $xml, [System.Text.Encoding]::Unicode)

$r = schtasks /Create /TN $TASK_NAME /XML $xmlPath /F
Write-Host $r
Remove-Item $xmlPath -Force -ErrorAction SilentlyContinue

# Start immediately
$r2 = schtasks /Run /TN $TASK_NAME
Write-Host "Start: $r2"

Start-Sleep -Seconds 3

$q = schtasks /Query /TN $TASK_NAME /FO LIST
Write-Host $q
