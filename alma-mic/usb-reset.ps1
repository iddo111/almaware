# ALMAWARE USB RESET - force Windows to re-enumerate the bus. NEEDS ADMIN.
# איפוס USB - מכריח את ווינדוס לסרוק מחדש. דורש הרשאות מנהל.
#
#   Right-click -> Run with PowerShell (as Administrator)
#   or:  powershell -ExecutionPolicy Bypass -File usb-reset.ps1
#
# Default actions are all SAFE - nothing that can disconnect your keyboard:
#   1. delete phantom Logitech/BRIO device nodes (stale entries block re-enum)
#   2. rescan the bus
#   3. restart the camera frame server
#
# -HubCycle additionally disables and re-enables the USB root hubs. That is the
# strongest reset available, but it briefly drops EVERY USB device - including
# your keyboard and mouse. Only use it with a PS/2 keyboard or via Remote
# Desktop, and never on a machine you cannot physically reach.

param([switch]$HubCycle)

$ErrorActionPreference = 'Continue'

function Admin? {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

Write-Host ""
Write-Host "  ALMAWARE USB RESET" -ForegroundColor Cyan
if (-not (Admin?)) {
    Write-Host "  NOT running as Administrator - most steps will fail." -ForegroundColor Red
    Write-Host "  Right-click this file and Run as Administrator." -ForegroundColor Red
    Write-Host ""
    exit 1
}
Write-Host "  running elevated" -ForegroundColor DarkGray
Write-Host ("  " + ("-" * 62)) -ForegroundColor DarkGray

# --- 1. phantom device nodes --------------------------------------------------
Write-Host "`n  [1] removing phantom Logitech / BRIO nodes..." -ForegroundColor Yellow
$before = (Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue).Count
$ghosts = Get-PnpDevice -ErrorAction SilentlyContinue |
    Where-Object { ($_.InstanceId -match 'VID_046D' -or $_.FriendlyName -match 'BRIO') -and
                   $_.Status -ne 'OK' }
if ($ghosts) {
    foreach ($g in $ghosts) {
        try {
            pnputil /remove-device "$($g.InstanceId)" 2>&1 | Out-Null
            Write-Host "      removed: $($g.FriendlyName) [$($g.Class)]" -ForegroundColor DarkGray
        } catch {
            Write-Host "      could not remove: $($g.FriendlyName)" -ForegroundColor DarkYellow
        }
    }
} else {
    Write-Host "      none found" -ForegroundColor DarkGray
}

# --- 2. rescan ----------------------------------------------------------------
Write-Host "`n  [2] rescanning the bus..." -ForegroundColor Yellow
pnputil /scan-devices 2>&1 | Select-Object -Last 2 | ForEach-Object { "      $_" }
Start-Sleep -Seconds 4

# --- 3. camera frame server ---------------------------------------------------
Write-Host "`n  [3] restarting camera frame server..." -ForegroundColor Yellow
foreach ($svc in 'FrameServer','FrameServerMonitor') {
    $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($s) {
        try {
            Restart-Service -Name $svc -Force -ErrorAction Stop
            Write-Host "      $svc restarted" -ForegroundColor DarkGray
        } catch { Write-Host "      $svc : $($_.Exception.Message)" -ForegroundColor DarkYellow }
    }
}

# --- 4. optional hub power cycle ---------------------------------------------
if ($HubCycle) {
    Write-Host "`n  [4] CYCLING USB ROOT HUBS - all USB devices will drop" -ForegroundColor Red
    Start-Sleep -Seconds 2
    $hubs = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
            Where-Object { $_.FriendlyName -match 'USB Root Hub' }
    foreach ($h in $hubs) {
        try {
            Disable-PnpDevice -InstanceId $h.InstanceId -Confirm:$false -ErrorAction Stop
            Start-Sleep -Milliseconds 1200
            Enable-PnpDevice -InstanceId $h.InstanceId -Confirm:$false -ErrorAction Stop
            Write-Host "      cycled: $($h.FriendlyName)" -ForegroundColor DarkGray
        } catch {
            Write-Host "      $($h.FriendlyName): $($_.Exception.Message)" -ForegroundColor DarkYellow
            try { Enable-PnpDevice -InstanceId $h.InstanceId -Confirm:$false -ErrorAction SilentlyContinue } catch {}
        }
    }
    Start-Sleep -Seconds 6
} else {
    Write-Host "`n  [4] hub power-cycle SKIPPED (add -HubCycle to force it)" -ForegroundColor DarkGray
}

# --- 5. verdict ---------------------------------------------------------------
Write-Host "`n  " + ("-" * 62) -ForegroundColor DarkGray
$after = (Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue).Count
Write-Host ("  devices present: {0} -> {1}" -f $before, $after) -ForegroundColor DarkGray
$l = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
     Where-Object { $_.InstanceId -match 'VID_046D' -or $_.FriendlyName -match 'BRIO' }
Write-Host ""
if ($l) {
    Write-Host "  BRIO IS NOW PRESENT" -ForegroundColor Green
    $l | Select-Object Status, Class, FriendlyName | Format-Table -AutoSize | Out-String -Width 130 | Write-Host
} else {
    Write-Host "  BRIO STILL NOT PRESENT" -ForegroundColor Red
    Write-Host "  Windows logged no USB arrival, so the data lines are not"
    Write-Host "  connecting. Software cannot reach a device the bus never saw."
    if (-not $HubCycle) {
        Write-Host "  Strongest remaining software step: re-run with -HubCycle" -ForegroundColor Yellow
        Write-Host "  (warning: briefly drops every USB device, keyboard included)"
    }
}
Write-Host ""
