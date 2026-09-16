# FINISH-STAGE1-ELEVATED.ps1 — infra-rebuild Stage 1, the two elevation-gated leftovers. 2026-08-12
# Run FROM AN ELEVATED PowerShell (right-click -> Run as administrator). Idempotent.
#
# Does exactly two things the non-elevated Stage-1 session could not:
#   1. Stage 1.4(d): register ALMA-Orphan-LHM (LibreHardwareMonitor :8085 thermal eyes,
#      logon +PT10M). LHM's exe manifest is requireAdministrator -> task must be RunLevel
#      Highest -> registration needs an elevated shell (same caveat as SNAPSHOT\RESTORE.md).
#   2. Stage 1.5: disable the failing task IDDO-AntFarm-Hybrid-Watchdog-10min (0x2 every
#      10 min; its XML is already exported to D:\CLAUDE\_genizah\autostart-20260812\).
#      Its ACL was minted elevated, so disabling needs elevation too.
#
# Plan: D:\CLAUDE\infra-rebuild\PHASE1-INFRA-INQUIRY.md  (Stage 1.4 / 1.5)
# Prime directive: does NOT touch ALMA-MIC-Elevated or any audio device.

$ErrorActionPreference = 'Stop'
$elev = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $elev) { throw 'This script must run from an ELEVATED shell (Run as administrator).' }

# ---- 1. ALMA-Orphan-LHM ------------------------------------------------------
$u = "$env:COMPUTERNAME\$env:USERNAME"
$exe = 'C:\Users\<user>\AppData\Local\Microsoft\WinGet\Packages\LibreHardwareMonitor.LibreHardwareMonitor_Microsoft.Winget.Source_8wekyb3d8bbwe\LibreHardwareMonitor.exe'
if (-not (Test-Path $exe)) { throw "LHM exe not found at $exe" }

$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
$trigger   = New-ScheduledTaskTrigger -AtLogOn -User $u
$trigger.Delay = 'PT10M'
$action    = New-ScheduledTaskAction -Execute $exe -WorkingDirectory (Split-Path $exe)
$principal = New-ScheduledTaskPrincipal -UserId $u -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName 'ALMA-Orphan-LHM' -Trigger $trigger -Action $action -Settings $settings -Principal $principal -Description 'infra-rebuild Stage 1.4 (2026-08-12): LibreHardwareMonitor :8085 thermal eyes at logon +PT10M. Temporary until ASM adoption. Plan: D:\CLAUDE\infra-rebuild\PHASE1-INFRA-INQUIRY.md' -Force | Out-Null
$rl = (Get-ScheduledTask 'ALMA-Orphan-LHM').Principal.RunLevel
if ("$rl" -ne 'Highest') { throw "ALMA-Orphan-LHM RunLevel is '$rl', not Highest - something downgraded it." }
Write-Host "1. ALMA-Orphan-LHM registered, RunLevel=Highest. LHM at next logon +10min -> http://localhost:8085/data.json"

# ---- 2. disable the 0x2 spam task -------------------------------------------
$tn = 'IDDO-AntFarm-Hybrid-Watchdog-10min'
$xml = 'D:\CLAUDE\_genizah\autostart-20260812\IDDO-AntFarm-Hybrid-Watchdog-10min.xml'
if (-not (Test-Path $xml)) { throw "Genizah XML missing at $xml - export before disabling (archive law)." }
Disable-ScheduledTask -TaskName $tn | Out-Null
Write-Host "2. $tn disabled (state: $((Get-ScheduledTask $tn).State)). Rollback: Enable-ScheduledTask '$tn' or re-import $xml"

Write-Host 'FINISH-STAGE1-ELEVATED: done.'
