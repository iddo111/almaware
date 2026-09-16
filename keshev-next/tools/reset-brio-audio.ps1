# Reset ONLY the BRIO's audio interface (MI_03) -- the software equivalent of
# unplugging and replugging the mic. Touches no playback device.
# Written 2026-08-29, the deaf-mic morning: BRIO video captured fine while its
# microphone returned exact digital silence on every host API and via ffmpeg,
# unmuted, level 73%, PnP code 0. That is a wedged USB audio function.
$ErrorActionPreference = 'Stop'
$id = 'USB\VID_046D&PID_085E&MI_03\A&23A274D7&0&0003'

Write-Host "BRIO audio interface: $id"
$d = Get-PnpDevice -InstanceId $id
Write-Host ("before: " + $d.Status)

Disable-PnpDevice -InstanceId $id -Confirm:$false
Start-Sleep -Seconds 3
Enable-PnpDevice  -InstanceId $id -Confirm:$false
Start-Sleep -Seconds 5

$d = Get-PnpDevice -InstanceId $id
Write-Host ("after:  " + $d.Status)
Write-Host ""
Write-Host "Done. Now say something -- KESHEV should type it." -ForegroundColor Green
Start-Sleep -Seconds 4
