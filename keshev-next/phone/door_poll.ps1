$phone = "<tailnet-ip>"; $log = "D:\CLAUDE\keshev-next\phone\door_poll.log"
$bs = "http://<tailnet-ip>:8897/phone_bootstrap.sh"
$deadline = (Get-Date).AddMinutes(240)
Add-Content $log ("poll (re-armed by FABLE) started " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " pid=" + $PID + " until " + $deadline.ToString("HH:mm"))
while ((Get-Date) -lt $deadline) {
  $open = Test-NetConnection -ComputerName $phone -Port 8022 -WarningAction SilentlyContinue -InformationLevel Quiet
  Add-Content $log ((Get-Date -Format "HH:mm:ss") + " 8022=" + $open)
  if ($open) {
    Add-Content $log "DOOR OPEN -> running bootstrap over ssh"
    $cmd = "curl -fsSL $bs -o /tmp/bs.sh && sh /tmp/bs.sh"
    $out = & ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -p 8022 -i "$env:USERPROFILE\.ssh\id_ed25519" $phone $cmd 2>&1
    if ($LASTEXITCODE -ne 0) {
      Add-Content $log ("first login rc=$LASTEXITCODE; retry as u0_a415@")
      $out = & ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -p 8022 -i "$env:USERPROFILE\.ssh\id_ed25519" "u0_a415@$phone" $cmd 2>&1
    }
    Add-Content $log "===== bootstrap output ====="; Add-Content $log ($out -join "`n"); Add-Content $log ("===== rc=$LASTEXITCODE ====="); break
  }
  Start-Sleep -Seconds 30
}
Add-Content $log ("poll ended " + (Get-Date -Format "HH:mm:ss"))

