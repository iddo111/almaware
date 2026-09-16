<#
install-watchdog.ps1
====================
Registers (or re-registers) the hourly Windows Scheduled Task
'ALMAWARE-A70-Dispatch-Watchdog' that runs watchdog.ps1.

The task:
  - runs every 1 hour, indefinitely (TimeTrigger repetition, no end)
  - also runs ~2 min after logon (so a reboot does not leave a gap)
  - runs hidden (no console window): pwsh/powershell -NoProfile -ExecutionPolicy Bypass
  - highest privileges when this installer is run elevated (so it can
    Start-Service Tailscale and kill wedged processes); least privilege otherwise
  - idempotent: re-running replaces the existing task cleanly

Registration uses schtasks.exe /Create /XML (works with or without the
ScheduledTasks PowerShell module, and in restricted shells where the cmdlets
are blocked). For full self-heal (runs while logged off + Start-Service), run
this from an ELEVATED PowerShell.

Usage:
  pwsh -NoProfile -ExecutionPolicy Bypass -File D:\CLAUDE\dispatch-fix\install-watchdog.ps1
  pwsh -File install-watchdog.ps1 -Unregister      # remove the task
  pwsh -File install-watchdog.ps1 -RunNow          # register + run once immediately

Per Iddo's conventions: no emoji, ASCII output.
#>
[CmdletBinding()]
param(
    [switch]$Unregister,
    [switch]$RunNow
)

$ErrorActionPreference = 'Stop'

$TaskName = 'ALMAWARE-A70-Dispatch-Watchdog'
$Root     = 'D:\CLAUDE\dispatch-fix'
$Script   = Join-Path $Root 'watchdog.ps1'

if (-not (Test-Path $Script)) { throw "watchdog.ps1 not found at $Script" }

# Prefer pwsh 7 if present, else Windows PowerShell.
$pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $pwsh) { $pwsh = (Get-Command powershell -ErrorAction SilentlyContinue).Source }
if (-not $pwsh) { $pwsh = 'powershell.exe' }

function Remove-TaskIfPresent {
    # /Delete is a no-op-ish if absent; suppress its error.
    schtasks.exe /Delete /TN $TaskName /F 2>$null | Out-Null
}

if ($Unregister) {
    Remove-TaskIfPresent
    Write-Host "Done. '$TaskName' is unregistered."
    return
}

# ---- elevation -> RunLevel + LogonType -------------------------------------
$isAdmin = (New-Object System.Security.Principal.WindowsPrincipal(
    [System.Security.Principal.WindowsIdentity]::GetCurrent())
).IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)

$me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($isAdmin) {
    $runLevel = 'HighestAvailable'
    # S4U = run whether or not the user is logged on, no stored password.
    $logonType = 'S4U'
    $mode = 'Highest + S4U (runs logged-off, elevated self-heal)'
} else {
    $runLevel = 'LeastPrivilege'
    $logonType = 'InteractiveToken'
    $mode = 'LeastPrivilege + Interactive (runs when logged on)'
}

# Command + args (XML-escaped). WindowStyle Hidden keeps it silent.
$cmd  = $pwsh
$args = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`""

function XmlEsc([string]$s) {
    return ($s -replace '&', '&amp;' -replace '<', '&lt;' -replace '>', '&gt;' -replace '"', '&quot;')
}
$cmdX  = XmlEsc $cmd
$argsX = XmlEsc $args
$meX   = XmlEsc $me
$descX = XmlEsc 'ALMAWARE A70 dispatch watchdog: checks pc-listener + Tailscale + A70 + MQTT broker hourly and self-heals the PC-side pieces. Remote-offline conditions are logged as human gates. See D:\CLAUDE\dispatch-fix\README.md'

# StartBoundary one minute from now (local time, schtasks expects local).
$start = (Get-Date).AddMinutes(1).ToString('yyyy-MM-ddTHH:mm:ss')

# Task Scheduler 1.2 XML. Two triggers:
#   - TimeTrigger: repeats every PT1H, no <Duration> => indefinite.
#   - LogonTrigger: 2 min after this user logs on.
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>$descX</Description>
    <Author>$meX</Author>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT1H</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>$start</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>$meX</UserId>
      <Delay>PT2M</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$meX</UserId>
      <LogonType>$logonType</LogonType>
      <RunLevel>$runLevel</RunLevel>
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
    <Hidden>true</Hidden>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>2</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$cmdX</Command>
      <Arguments>$argsX</Arguments>
      <WorkingDirectory>$Root</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

$xmlPath = Join-Path $env:TEMP 'almaware-a70-watchdog-task.xml'
# Task Scheduler XML must be UTF-16.
Set-Content -Path $xmlPath -Value $xml -Encoding Unicode

Remove-TaskIfPresent
$out = schtasks.exe /Create /TN $TaskName /XML $xmlPath /F 2>&1
$rc = $LASTEXITCODE
Remove-Item $xmlPath -ErrorAction SilentlyContinue

if ($rc -ne 0) {
    Write-Host ($out | Out-String)
    throw "schtasks /Create failed (exit $rc). If this says access denied, run from an elevated PowerShell."
}

Write-Host "Registered '$TaskName' [$mode] (hourly + logon+2m) using $pwsh."
Write-Host "  Script: $Script"
Write-Host "  Log:    $Root\watchdog.log"
Write-Host "  Health: $Root\state\watchdog-health.json"
if (-not $isAdmin) {
    Write-Host "NOTE: not elevated -> LeastPrivilege/Interactive (runs only while logged on,"
    Write-Host "      and cannot Start-Service Tailscale). Re-run from an ELEVATED PowerShell"
    Write-Host "      to upgrade to Highest+S4U (runs logged-off + full self-heal)."
}

# ---- verify ----------------------------------------------------------------
$q = schtasks.exe /Query /TN $TaskName /FO LIST 2>&1
if ($LASTEXITCODE -eq 0) {
    $status = ($q | Select-String -Pattern '^\s*Status:\s*(.+)$').Matches.Value
    Write-Host "Verified: $($status.Trim())"
} else {
    throw "Verification failed: task not found after register."
}

if ($RunNow) {
    Write-Host "Running the task once now..."
    schtasks.exe /Run /TN $TaskName | Out-Null
    Write-Host "Started. Tail the log: Get-Content '$Root\watchdog.log' -Tail 30 -Wait"
}
