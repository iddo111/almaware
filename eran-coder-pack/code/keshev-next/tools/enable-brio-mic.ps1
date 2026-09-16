# The BRIO's MICROPHONE interface (MI_03) is DISABLED -- PnP problem code 22,
# ConfigFlags=1. Its camera (MI_00) and HID (MI_05) are fine, which is why video
# worked while the mic returned digital silence on every host API.
# Code 22 is a persistent registry flag: it survives replug, device reset and an
# audio-service restart. Only an explicit Enable clears it.
$ErrorActionPreference = 'Stop'
$id = 'USB\VID_046D&PID_085E&MI_03\A&23A274D7&0&0003'

$d = Get-PnpDevice -InstanceId $id
$code = (Get-PnpDeviceProperty -InstanceId $id -KeyName 'DEVPKEY_Device_ProblemCode').Data
Write-Host ("before: status=" + $d.Status + "  problem code=" + $code)

Enable-PnpDevice -InstanceId $id -Confirm:$false
Start-Sleep -Seconds 6

$d = Get-PnpDevice -InstanceId $id
$code = (Get-PnpDeviceProperty -InstanceId $id -KeyName 'DEVPKEY_Device_ProblemCode').Data
$flags = (Get-PnpDeviceProperty -InstanceId $id -KeyName 'DEVPKEY_Device_ConfigFlags').Data
Write-Host ("after:  status=" + $d.Status + "  problem code=" + $code + "  ConfigFlags=" + $flags)
Write-Host ""
if ($d.Status -eq 'OK' -and $code -eq 0) {
  Write-Host "BRIO microphone ENABLED. Say something -- KESHEV should type it." -ForegroundColor Green
} else {
  Write-Host "Still not enabled. Open Device Manager > Audio inputs and outputs / Sound," -ForegroundColor Yellow
  Write-Host "find Logitech BRIO, right-click > Enable device." -ForegroundColor Yellow
}
Start-Sleep -Seconds 6
