# NymoLabs offline controller = STM32 VCP USB\VID_0483&PID_5740. Logs arrive/leave with COM#. 3h, BelowNormal, touches nothing.
$log = "D:\CLAUDE\cnc\nymo_usb_watch.log"
$deadline = (Get-Date).AddHours(3)
function Snap {
  Get-CimInstance Win32_PnPEntity -Filter "DeviceID LIKE 'USB\\VID_0483&PID_5740%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.Present -or $_.Status -eq 'OK' } | ForEach-Object { "$($_.Name) [$($_.Status)] $($_.DeviceID)" } | Sort-Object
}
Add-Content $log ("watch started " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " pid=" + $PID + " until " + $deadline.ToString("HH:mm"))
$prev = @(Snap); Add-Content $log ("initial present: " + $(if($prev){$prev -join '; '}else{'(none)'}))
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 2
  $cur = @(Snap)
  foreach ($x in $cur)  { if ($prev -notcontains $x) { Add-Content $log ((Get-Date -Format "HH:mm:ss.fff") + " + ARRIVED  " + $x) } }
  foreach ($x in $prev) { if ($cur  -notcontains $x) { Add-Content $log ((Get-Date -Format "HH:mm:ss.fff") + " - REMOVED  " + $x) } }
  $prev = $cur
}
Add-Content $log ("watch ended " + (Get-Date -Format "HH:mm:ss"))
