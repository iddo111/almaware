$ErrorActionPreference = "Continue"
$log = "$env:TEMP\kill-rgb-$(Get-Date -Format yyyyMMdd_HHmmss).log"
function L($m) { $m | Tee-Object -FilePath $log -Append }
L "=== Kill RGB started $(Get-Date) ==="

$svcs = @(
  "AsusCertService","ArmouryCrateService","ArmouryCrateControlInterface",
  "Razer Synapse Service","Razer Game Manager Service","RzActionSvc",
  "CorsairService","iCUEService",
  "LightingService",
  "GHUBKBService","LGHUBUpdaterService",
  "GLCKIO2","GLCKIO",
  "ASRPolychromeRGBService",
  "NZXT CAM Service"
)
foreach ($s in $svcs) {
  $svc = Get-Service -Name $s -ErrorAction SilentlyContinue
  if ($svc) {
    if ($svc.Status -eq "Running") { Stop-Service -Name $s -Force -ErrorAction SilentlyContinue; L "stopped: $s" }
    Set-Service -Name $s -StartupType Disabled -ErrorAction SilentlyContinue
    L "disabled: $s"
  }
}

$procs = @(
  "ArmouryCrate","ArmouryCrate.UserSessionHelper","AsusCertService",
  "Aura","LightingService","RGBFusion","MysticLight",
  "iCUE","iCUELauncher","CorsairUtility","CorsairLighting",
  "RzSynapse","Razer Synapse 3","RazerCentralService",
  "LGHUB","LCore","LCoreUpdater",
  "OpenRGB","SignalRgbLauncher"
)
foreach ($p in $procs) {
  Get-Process -Name $p -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; L "killed: $($_.Name) pid=$($_.Id)" }
}

Get-ScheduledTask -ErrorAction SilentlyContinue |
  Where-Object { $_.TaskPath -match "ASUS|Armoury|Razer|MSI|Corsair|Logitech" -and $_.State -ne "Disabled" } |
  ForEach-Object {
    Disable-ScheduledTask -TaskPath $_.TaskPath -TaskName $_.TaskName -ErrorAction SilentlyContinue | Out-Null
    L "disabled task: $($_.TaskPath)$($_.TaskName)"
  }

$openrgb = Get-Command openrgb -ErrorAction SilentlyContinue
if ($openrgb) {
  & $openrgb.Source --noautoconnect --device 0 --mode static --color 000000 2>&1 | Out-Null
  L "openrgb: forced black"
}

L "=== Kill RGB done. Log: $log ==="
Write-Host "Done. Log: $log" -ForegroundColor Green
