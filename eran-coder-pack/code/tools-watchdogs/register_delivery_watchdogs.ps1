# Register the two 2026-09-05 watchers so they survive a reboot.
#
# > BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
# > output, not a proxy.
#
# WHY THIS FILE EXISTS
# --------------------
# The whole finding of 2026-09-05 was that this workspace does not lack
# instruments -- it lacks anything that RUNS them:
#
#   * RAMCHAT\receipts.py, written 09-04 as the fix for the microphone going
#     silent, has ZERO callers. Its own docstring: "a rule nobody can check is
#     a wish." It was one. Run by hand once tonight it immediately found 6 real
#     violations, one lock 2,562 hours old.
#   * eran-brain\holobrain2\watchdog\watch_relay.py, written 09-01, was never
#     scheduled. Its own docstring: "an instrument nobody checks is an
#     instrument that has already failed quietly." Meanwhile the eran3 learning
#     watchdog it carries fired every 3 minutes and wrote 105 alarms nobody read.
#
# So a watchdog that dies on the next reboot is not a fix, it is the same bug
# with a longer fuse. This file is the difference between a tool and a gate.
#
# Modelled on register_watchdogs.ps1 (the house pattern), with two differences:
# these two RUN A LOOP INTERNALLY, so they need a logon trigger and no time
# repetition, and MultipleInstancesPolicy=IgnoreNew so a manual start plus the
# scheduled one can never both hold the file.
#
# Priority 7 = BELOW_NORMAL. That is not decoration: on 2026-09-03 heavy
# normal-priority work on this PC starved Iddo's live microphone and 78% of his
# decodes came back empty. Nothing this file registers may ever outrank his mic.
#
#   .\register_delivery_watchdogs.ps1          install / update
#   .\register_delivery_watchdogs.ps1 -Remove  uninstall
#
# To undo by hand:
#   Unregister-ScheduledTask -TaskName KeshevDeliveryWatchdog -Confirm:$false
#   Unregister-ScheduledTask -TaskName SiblingAlarmRelay      -Confirm:$false

param([switch]$Remove)

$Python = "C:\Program Files\Python312\python.exe"
if (-not (Test-Path $Python)) { $Python = (Get-Command python).Source }

$tasks = @(
    @{
        Name = "KeshevDeliveryWatchdog"
        Dir  = "D:\CLAUDE\tools\watchdogs"
        Args = "keshev_delivery_watchdog.py --quiet"
        Desc = "The only KESHEV check that measures the PRODUCT: verdict=='typed' means text actually reached Iddo's chat, not that a server answered 200. Read-only on the live mic; also runs RAMCHAT\receipts.py, which nothing else calls."
    },
    @{
        Name = "SiblingAlarmRelay"
        Dir  = "D:\CLAUDE\eran-brain\holobrain2\watchdog"
        Args = "relay_loop.py"
        Desc = "Carries the eran3 learning-watchdog's alarms into RAMCHAT. The relay existed since 2026-09-01 and was never scheduled, so 105 alarms went unread for four days."
    }
)

foreach ($t in $tasks) {
    Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false -ErrorAction SilentlyContinue
    if ($Remove) { Write-Host "removed $($t.Name)"; continue }

    if (-not (Test-Path (Join-Path $t.Dir ($t.Args -split ' ')[0]))) {
        Write-Host "SKIP $($t.Name): script not found in $($t.Dir)" -ForegroundColor Yellow
        continue
    }

    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>$($t.Desc)</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
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
    <RestartOnFailure>
      <Interval>PT5M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
    <Hidden>true</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$Python</Command>
      <Arguments>$($t.Args)</Arguments>
      <WorkingDirectory>$($t.Dir)</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

    Register-ScheduledTask -TaskName $t.Name -Xml $xml -Force | Out-Null
    $reg = Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
    if ($reg) {
        Write-Host ("registered {0}  state={1}" -f $t.Name, $reg.State) -ForegroundColor Green
    } else {
        Write-Host ("FAILED to register {0}" -f $t.Name) -ForegroundColor Red
    }
}

if (-not $Remove) {
    Write-Host ""
    Write-Host "--- verification: what the scheduler actually holds ---"
    Get-ScheduledTask -TaskName KeshevDeliveryWatchdog, SiblingAlarmRelay -ErrorAction SilentlyContinue |
        Select-Object TaskName, State,
            @{n = 'Trigger'; e = { $_.Triggers[0].CimClass.CimClassName } },
            @{n = 'Priority'; e = { $_.Settings.Priority } } |
        Format-Table -AutoSize
}
