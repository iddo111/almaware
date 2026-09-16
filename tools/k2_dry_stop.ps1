# ============================================================================
# K2 Plus — stop the filament dry cycle (chamber heater OFF).
#
#   Durable location ON PURPOSE. The previous version of this script lived in
#   %LOCALAPPDATA%\Temp\claude\... — a TEMP directory. Windows temp-cleanup or
#   Storage Sense can delete that at any time, which would silently break the
#   auto-stop and leave the chamber heater running unattended. Never put a
#   safety-critical stop script in Temp.
#
#   Sends BOTH forms: M141 S0 (what the Creality firmware's chamber controller
#   actually tracks) and SET_HEATER_TEMPERATURE (the Klipper-native form).
#   Verified 2026-08-13: a bare SET_HEATER_TEMPERATURE returns "ok" but does
#   NOT change the target — the firmware re-asserts its own M141 value.
#
#   Task: ALMA-Filament-Dry-Stop
# ============================================================================
$ErrorActionPreference = 'SilentlyContinue'

$printer = '<lan-ip>'
$log     = 'D:\CLAUDE\tools\k2_dry_stop.log'
$stamp   = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

function Send-Script($s) {
    $enc = [uri]::EscapeDataString($s)
    try {
        $r = Invoke-RestMethod -Uri "http://$printer`:7125/printer/gcode/script?script=$enc" -Method Post -TimeoutSec 25
        return "ok:$($r.result)"
    } catch { return "FAIL:$($_.Exception.Message)" }
}

$a = Send-Script 'M141 S0'
$b = Send-Script 'SET_HEATER_TEMPERATURE HEATER=chamber_heater TARGET=0'

Start-Sleep -Seconds 4

# Verify the REAL state, never trust the "ok" (Broken Windows Law)
$target = 'UNKNOWN'; $temp = 'UNKNOWN'
try {
    $q  = Invoke-RestMethod -Uri "http://$printer`:7125/printer/objects/query?heater_generic%20chamber_heater" -TimeoutSec 10
    $ch = $q.result.status.'heater_generic chamber_heater'
    $target = $ch.target
    $temp   = [math]::Round($ch.temperature, 2)
} catch {}

$verdict = if ($target -eq 0) { 'VERIFIED OFF' } else { "STILL ON (target=$target) — NEEDS ATTENTION" }
Add-Content -LiteralPath $log -Encoding UTF8 -Value "$stamp  M141=$a  SETHEATER=$b  chamber temp=$temp target=$target  => $verdict"
