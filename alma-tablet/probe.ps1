# alma-tablet / probe.ps1 - plug the tablet in, run this, know everything in 20 seconds.
#
# The single most important thing to learn BEFORE touching the bootloader is whether this
# particular SM-T220 can be unlocked at all, and whether it can be recovered if the flash
# goes wrong. Everything else is reversible; those two are not. So this reads the device
# rather than assuming, and it reads it in whatever state the tablet happens to be in:
# normal Android, recovery, sideload, or Download (Odin) mode.
#
#   powershell -ExecutionPolicy Bypass -File probe.ps1

$ErrorActionPreference = 'SilentlyContinue'

$adb = @(
  "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe",
  "D:\platform-tools\adb.exe",
  "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

$fastboot = $adb -replace 'adb\.exe$', 'fastboot.exe'

if (-not $adb) { Write-Host "adb not found. Install with: winget install Google.PlatformTools" -ForegroundColor Red; exit 1 }
Write-Host "using $adb`n" -ForegroundColor DarkGray

function Line($k, $v, $col = 'White') {
  Write-Host ("  {0,-26}" -f $k) -NoNewline -ForegroundColor DarkGray
  Write-Host $v -ForegroundColor $col
}

Write-Host "SAMSUNG GALAXY TAB A7 LITE (SM-T220) - DEVICE PROBE" -ForegroundColor Cyan
Write-Host ("=" * 62)

# ---- what state is it in? ----
& $adb start-server | Out-Null
$devs = (& $adb devices) -split "`r?`n" | Where-Object { $_ -match "`t" }
$fb = (& $fastboot devices) -split "`r?`n" | Where-Object { $_.Trim() }

if (-not $devs -and -not $fb) {
  Line "state" "NOTHING CONNECTED" Yellow
  Write-Host ""
  Write-Host "  If it IS plugged in:" -ForegroundColor Yellow
  Write-Host "   - normal Android: Settings > About > tap Build number 7x, then"
  Write-Host "     Developer options > USB debugging ON, and accept the RSA prompt"
  Write-Host "   - it may be sitting in Recovery: that only speaks adb in 'Apply"
  Write-Host "     update from ADB' (sideload) mode, which answers almost nothing"
  Write-Host "   - Download/Odin mode speaks neither adb nor fastboot on Samsung -"
  Write-Host "     it needs Odin or Heimdall"
  exit 0
}

if ($fb) { Line "state" "FASTBOOT ($fb)" Green }
if ($devs) {
  $mode = if ($devs -match 'recovery') { 'RECOVERY' }
          elseif ($devs -match 'sideload') { 'SIDELOAD' }
          elseif ($devs -match 'unauthorized') { 'UNAUTHORIZED - accept the prompt on the tablet' }
          else { 'ANDROID (adb)' }
  Line "state" $mode $(if ($mode -like 'UNAUTH*') { 'Red' } else { 'Green' })
}

# ---- identity ----
$props = @{
  'model'            = 'ro.product.model'
  'device codename'  = 'ro.product.device'
  'android version'  = 'ro.build.version.release'
  'security patch'   = 'ro.build.version.security_patch'
  'build id'         = 'ro.build.display.id'
  'SoC'              = 'ro.board.platform'
  'region / CSC'     = 'ro.csc.sales_code'
  'bootloader'       = 'ro.boot.bootloader'
  'treble (GSI ok?)' = 'ro.treble.enabled'
  'vndk version'     = 'ro.vndk.version'
}
Write-Host ""
Write-Host "IDENTITY" -ForegroundColor Cyan
foreach ($k in $props.Keys) {
  $v = (& $adb shell getprop $props[$k]) -replace "`r|`n", ''
  if ($v) { Line $k $v }
}

# ---- the two questions that actually matter ----
Write-Host ""
Write-Host "THE TWO IRREVERSIBLE QUESTIONS" -ForegroundColor Cyan

$oem = (& $adb shell getprop sys.oem_unlock_allowed) -replace "`r|`n", ''
$unl = (& $adb shell getprop ro.boot.flash.locked) -replace "`r|`n", ''
$warranty = (& $adb shell getprop ro.boot.warranty_bit) -replace "`r|`n", ''
$verified = (& $adb shell getprop ro.boot.verifiedbootstate) -replace "`r|`n", ''

Line "OEM unlock allowed" $(switch ($oem) { '1' { 'YES - unlockable' } '0' { 'NO - toggle is off or absent' } default { "unknown ($oem)" } }) `
     $(if ($oem -eq '1') { 'Green' } else { 'Yellow' })
Line "bootloader locked" $(switch ($unl) { '1' { 'LOCKED (stock)' } '0' { 'ALREADY UNLOCKED' } default { "unknown ($unl)" } })
Line "KNOX warranty bit" $(switch ($warranty) { '1' { 'ALREADY TRIPPED - nothing left to lose' } '0' { 'INTACT - unlocking burns it, permanently' } default { "unknown ($warranty)" } }) `
     $(if ($warranty -eq '1') { 'Green' } else { 'Yellow' })
Line "verified boot state" $verified

Write-Host ""
Write-Host "  KNOX is a physical e-fuse. Once tripped it can NEVER be reset - not by" -ForegroundColor Yellow
Write-Host "  reflashing stock, not by Samsung. Samsung Pay, Secure Folder and Health" -ForegroundColor Yellow
Write-Host "  data stay dead forever. The tablet itself keeps working fine." -ForegroundColor Yellow

# ---- hardware worth knowing before buying anything ----
Write-Host ""
Write-Host "HARDWARE" -ForegroundColor Cyan
Line "total RAM" (((& $adb shell cat /proc/meminfo) -split "`n" | Select-String 'MemTotal') -replace '\s+', ' ')
Line "CPU cores" ((& $adb shell nproc) -replace "`r|`n", '')
Line "kernel" ((& $adb shell uname -r) -replace "`r|`n", '')
$otg = (& $adb shell 'ls /sys/class/typec 2>/dev/null; getprop sys.usb.controller') -replace "`r|`n", ' '
Line "usb controller" $otg
Line "wifi chip" ((& $adb shell getprop ro.hardware.wlan) -replace "`r|`n", '')

Write-Host ""
Write-Host ("=" * 62)
Write-Host "Nothing above changed anything on the tablet. This script only READS." -ForegroundColor Green
