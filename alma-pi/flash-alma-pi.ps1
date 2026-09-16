# flash-alma-pi.ps1 — write ALMA Pi to a microSD and inject first-boot provisioning.
# Usage: pwsh -File D:\CLAUDE\alma-pi\flash-alma-pi.ps1   (add -Yes to skip confirm)
# Written 2026-08-08 by claude-cli. Image + firstrun.sh live next to this script.
param([switch]$Yes)
$ErrorActionPreference = "Stop"
$root  = Split-Path -Parent $MyInvocation.MyCommand.Path
$image = Join-Path $root "images\2026-06-18-raspios-trixie-arm64.img.xz"
$first = Join-Path $root "firstrun.sh"
if (-not (Test-Path $image)) { throw "image missing: $image" }
if (-not (Test-Path $first)) { throw "firstrun.sh missing: $first" }

# 1. find exactly one removable disk
$disks = @(Get-Disk | Where-Object { $_.BusType -in 'USB','SD','MMC' -and -not $_.IsBoot -and -not $_.IsSystem })
if ($disks.Count -eq 0) { throw "No removable disk found. Insert the microSD (card reader), then rerun." }
if ($disks.Count -gt 1) { $disks | Format-Table Number,FriendlyName,@{n='GB';e={[math]::Round($_.Size/1GB,1)}}; throw "Multiple removable disks - unplug extras and rerun." }
$d = $disks[0]
Write-Host ("Target: disk {0} '{1}' {2} GB" -f $d.Number, $d.FriendlyName, [math]::Round($d.Size/1GB,1))
if (-not $Yes) { $a = Read-Host "This ERASES that disk. Type FLASH to continue"; if ($a -ne 'FLASH') { throw "aborted" } }

# 2. write with Raspberry Pi Imager CLI
$imager = @("$env:ProgramFiles\Raspberry Pi Ltd\Imager\rpi-imager.exe",
            "$env:ProgramFiles\Raspberry Pi Imager\rpi-imager.exe",
            "${env:ProgramFiles(x86)}\Raspberry Pi Imager\rpi-imager.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $imager) { throw "rpi-imager not installed. Run: winget install RaspberryPiFoundation.RaspberryPiImager" }
& $imager --cli $image "\\.\PhysicalDrive$($d.Number)"
if ($LASTEXITCODE -ne 0) { throw "rpi-imager failed ($LASTEXITCODE)" }

# 3. inject firstrun hook onto the FAT32 boot partition
Start-Sleep 5
$boot = (Get-Partition -DiskNumber $d.Number | Get-Volume | Where-Object { $_.FileSystem -eq 'FAT32' } | Select-Object -First 1).DriveLetter
if (-not $boot) { # partition may need a letter
    $p = Get-Partition -DiskNumber $d.Number | Where-Object { $_.Type -match 'FAT|Basic' } | Select-Object -First 1
    $p | Add-PartitionAccessPath -AssignDriveLetter; Start-Sleep 2
    $boot = ($p | Get-Volume).DriveLetter
}
$bp = "${boot}:"
# unix line endings for firstrun.sh
$sh = (Get-Content $first -Raw) -replace "`r`n","`n"
[IO.File]::WriteAllText("$bp\firstrun.sh", $sh)
$cmd = (Get-Content "$bp\cmdline.txt" -Raw).TrimEnd()
if ($cmd -notmatch 'systemd\.run=') {
    $cmd += " systemd.run=/boot/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target"
    [IO.File]::WriteAllText("$bp\cmdline.txt", $cmd + "`n")
}
Write-Host "DONE. Eject the card, put it in the Pi, attach keyboard+HDMI+power."
Write-Host "First boot: provisions itself (needs ethernet or Wi-Fi filled into firstrun.sh),"
Write-Host "then the screen becomes a kiosk at http://localhost:8080 (also http://alma-pi.local:8080)."
