# KESHEV-FABLE clean restart — ELEVATED (the live mic runs elevated so SendInput
# survives UIPI: "TYPED ok lied for weeks" — INSIGHTS §1.4). Run via:
#   Start-Process pwsh -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','D:\CLAUDE\keshev-fable\tools\restart-elevated.ps1'
# A non-elevated shell cannot see the elevated mic's command line nor kill it —
# that is WHY this script exists. It writes a plain-text log next to the journal.
$ErrorActionPreference = "Continue"
$log = "D:\CLAUDE\keshev-fable\state\restart-elevated.log"
function Say($m) { $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $m; Write-Host $line; Add-Content -Path $log -Value $line -Encoding utf8 }

$me = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
$elev = $me.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Say "=== restart-elevated begin (elevated=$elev) ==="
if (-not $elev) { Say "NOT elevated — refusing (the new mic would be UIPI-blind). Re-run with -Verb RunAs."; Start-Sleep 4; exit 2 }

# 1. stop every keshev-fable app.main, loop until none remain
for ($i = 0; $i -lt 8; $i++) {
    $ps = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\.main' -and $_.CommandLine -notmatch 'restart-elevated' })
    if ($ps.Count -eq 0) { break }
    Say ("round {0}: stopping {1} app.main pid(s): {2}" -f $i, $ps.Count, (($ps | ForEach-Object { $_.ProcessId }) -join ','))
    $ps | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}
$left = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\.main' }).Count
if ($left -gt 0) { Say "ABORT: $left app.main still alive"; Start-Sleep 5; exit 1 }
Start-Sleep -Seconds 2   # let WASAPI release the BRIO

# 2. start exactly ONE, elevated (inherits this shell's token)
$env:KESHEV_OWNER_FLOOR = "0.60"     # clause-4 owner gate, enforce (measured 2026-08-19)
# 2026-08-20 08:58: 0.020 was chopping him mid-sentence — 5 fragment-drops vs 3
# typed in one hour, every drop a 0.4-0.6 s blip decoding as "you". gates.py's
# GATE_RMS=0.008 is the value CALIBRATED on 854 live segments (speech median
# 0.0276, floor p90 0.0060); 0.020 sat inside his own speech distribution, so
# the pauses between his words closed the segment. Back to the measured floor.
$env:KESHEV_GATE        = "0.008"    # energy gate; the window slider/AUTO can move it live
# KESHEV_LOGPROB_FLOOR deliberately NOT set: the calibrated -0.6 stays. Below it,
# EN garbage now gets the LANG_FLIP rescue (forced he) instead of being dropped.
$env:PYTHONIOENCODING   = "utf-8"
$py = "C:\Users\<user>\AppData\Local\Programs\Python\Python313\python.exe"
Say "starting ONE new mic: $py -m app.main (cwd D:\CLAUDE\keshev-fable)"
Start-Process -FilePath $py -ArgumentList "-m","app.main" -WorkingDirectory "D:\CLAUDE\keshev-fable" -WindowStyle Minimized
Start-Sleep -Seconds 6
$now = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\.main' })
Say ("now running: {0} app.main pid(s): {1}" -f $now.Count, (($now | ForEach-Object { $_.ProcessId }) -join ','))
Say "=== restart-elevated end ==="
Start-Sleep -Seconds 2
