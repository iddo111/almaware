# Launch alma trainer fully detached, logs go to file, no terminal pop-up.
$logDir = 'D:\CLAUDE\alma-memorial\logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir ('trainer_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log')

$p = Start-Process -FilePath 'D:\CLAUDE\alma-memorial\.venv-train\Scripts\python.exe' `
  -ArgumentList 'tools\alma_trainer_loop.py' `
  -WorkingDirectory 'D:\CLAUDE\alma-memorial' `
  -WindowStyle Hidden `
  -RedirectStandardOutput $log `
  -RedirectStandardError ($log + '.err') `
  -PassThru

Start-Sleep -Seconds 4
if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) {
  Write-Output ("TRAINER ALIVE PID=" + $p.Id + " LOG=" + $log)
} else {
  Write-Output "TRAINER DIED"
  if (Test-Path ($log + '.err')) { Write-Output '--- stderr ---'; Get-Content ($log + '.err') -Tail 20 }
}
