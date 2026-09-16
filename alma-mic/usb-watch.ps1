# ALMAWARE USB WATCH - live monitor for a device appearing on the bus.
# צופה בזמן אמת מתי מכשיר USB נכנס.
#
# Run this, then try a different cable or port. It tells you the INSTANT
# Windows sees anything new - no guessing, no re-asking.
#
#   powershell -ExecutionPolicy Bypass -File usb-watch.ps1
#   powershell -ExecutionPolicy Bypass -File usb-watch.ps1 -Match BRIO
#
# A camera LED coming on only proves it is getting 5 volts. It says nothing
# about the data lines. If nothing ever appears here, the data path is dead:
# almost always a charge-only cable, a damaged cable, or a dead port.

param(
    [string]$Match = '',        # optional filter, e.g. BRIO or 046D
    [int]$Seconds = 300
)

function Snapshot {
    Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty InstanceId
}

function Describe($id) {
    $d = Get-PnpDevice -InstanceId $id -ErrorAction SilentlyContinue
    if ($d) { "$($d.Class.PadRight(14)) $($d.FriendlyName)" } else { $id }
}

Write-Host ""
Write-Host "  ALMAWARE USB WATCH" -ForegroundColor Cyan
Write-Host "  watching for $Seconds seconds - plug/unplug now" -ForegroundColor DarkGray
if ($Match) { Write-Host "  filter: $Match" -ForegroundColor DarkGray }
Write-Host ("  " + ("-" * 66)) -ForegroundColor DarkGray

$before = Snapshot
Write-Host ("  baseline: {0} devices present" -f $before.Count) -ForegroundColor DarkGray
Write-Host ""

$deadline = (Get-Date).AddSeconds($Seconds)
$seen = @{}

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 900
    $now = Snapshot

    foreach ($id in ($now | Where-Object { $before -notcontains $_ })) {
        if ($seen.ContainsKey($id)) { continue }
        $seen[$id] = $true
        $desc = Describe $id
        if ($Match -and ($id -notmatch $Match) -and ($desc -notmatch $Match)) { continue }
        Write-Host ("  + {0}  ARRIVED  {1}" -f (Get-Date -Format 'HH:mm:ss'), $desc) -ForegroundColor Green
    }
    foreach ($id in ($before | Where-Object { $now -notcontains $_ })) {
        if ($seen.ContainsKey("gone:$id")) { continue }
        $seen["gone:$id"] = $true
        Write-Host ("  - {0}  REMOVED  {1}" -f (Get-Date -Format 'HH:mm:ss'), $id) -ForegroundColor DarkYellow
    }
    $before = $now
}

Write-Host ""
if ($seen.Count -eq 0) {
    Write-Host "  NOTHING CHANGED on the USB bus." -ForegroundColor Red
    Write-Host "  The data lines are not connecting. In order of likelihood:" -ForegroundColor Red
    Write-Host "    1. Charge-only USB-C cable  - swap for one you have moved FILES with"
    Write-Host "    2. Damaged cable or a loose plug at the camera end"
    Write-Host "    3. Dead port - use a rear motherboard USB 3.0 socket, not a hub"
} else {
    Write-Host ("  {0} change(s) detected." -f $seen.Count) -ForegroundColor Green
}
Write-Host ""
