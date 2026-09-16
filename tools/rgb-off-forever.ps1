# לזכרה של עלמה ז״ל
# Turn the RGB off and keep it off across every reboot.
#
# WHY THE OLD SCRIPT DID NOT HOLD
# -------------------------------
# tools/kill-rgb.ps1 disables vendor software (Aura, Armoury, iCUE...). That
# stops anything from SETTING a colour — but the G.Skill Trident Z RGB DIMMs in
# this machine have their own controller, and its power-on default is LIT. With
# no software talking to them they simply run their built-in rainbow.
#
# So nobody "turned the LEDs on". Something stopped turning them OFF, and the
# off was never made permanent. The board is an ASUS Z270F, and its BIOS Aura
# settings do not reach the DIMMs — those live on the SMBus and answer to
# software only. That is why this has to run at every boot.
#
# Needs administrator: SMBus access is privileged. This script elevates itself.

#Requires -Version 5.1
$ErrorActionPreference = "Continue"

$OpenRGB  = "D:\CLAUDE\tools\openrgb\OpenRGB.exe"
$TaskName = "ALMA-RGB-Off"

# ---- elevate if needed ----
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "  elevating..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList @(
        "-NoProfile","-ExecutionPolicy","Bypass","-File","`"$PSCommandPath`"")
    return
}

if (-not (Test-Path $OpenRGB)) { Write-Host "  OpenRGB not found at $OpenRGB" -ForegroundColor Red; pause; return }

Write-Host ""
Write-Host "  === what OpenRGB can actually see ===" -ForegroundColor Cyan
& $OpenRGB --noautoconnect --list-devices 2>&1 | Select-Object -First 40

Write-Host ""
Write-Host "  === writing black to every device ===" -ForegroundColor Cyan
# Static + 000000 is the only setting that survives; brightness 0 alone is
# reverted by some controllers on the next power cycle.
& $OpenRGB --noautoconnect --mode static --color 000000 2>&1 | Select-Object -First 20

# ---- make it stick across reboots ----
Write-Host ""
Write-Host "  === registering the boot task ===" -ForegroundColor Cyan
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute $OpenRGB `
    -Argument "--noautoconnect --mode static --color 000000"
# At boot AND at logon: the SMBus is not always ready the instant the service
# host starts, and a 30 s delay on the boot trigger costs nothing.
$t1 = New-ScheduledTaskTrigger -AtStartup
$t1.Delay = "PT30S"
$t2 = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $t1,$t2 `
    -Principal $principal -Settings $settings `
    -Description "Writes black to all RGB devices at boot. The G.Skill DIMMs default to lit, so this must run every time." | Out-Null

$info = Get-ScheduledTask -TaskName $TaskName
Write-Host ""
Write-Host ("  task '{0}' registered - state {1}" -f $TaskName, $info.State) -ForegroundColor Green
Write-Host ""
Write-Host "  Look at the RAM now. If it is dark, reboot once to prove the task holds." -ForegroundColor Green
Write-Host "  If it is still lit, OpenRGB did not reach the DIMMs - tell Claude what" -ForegroundColor Yellow
Write-Host "  the device list above printed." -ForegroundColor Yellow
Write-Host ""
pause
