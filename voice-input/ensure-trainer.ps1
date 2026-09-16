# ensure-trainer.ps1 — keep continuous_trainer.py alive (always-on voice trainer).
# Register as a scheduled task (e.g. every 5 min) so the trainer "always runs".
$py     = "C:\Users\<user>\AppData\Local\Programs\Python\Python312\pythonw.exe"
$script = "D:\CLAUDE\voice-input\continuous_trainer.py"

$running = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*continuous_trainer.py*" }

if (-not $running) {
    Start-Process -FilePath $py -ArgumentList @($script, "--user", "iddo1") -WindowStyle Hidden
    "[ensure-trainer] started continuous_trainer at $(Get-Date -Format o)"
} else {
    "[ensure-trainer] already running (pid $($running.ProcessId))"
}
