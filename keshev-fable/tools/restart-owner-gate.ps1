$ErrorActionPreference = "Continue"
Write-Host "=== KESHEV clean restart ==="
# 1. kill ALL app.main, LOOP until zero remain
for ($i=0; $i -lt 8; $i++) {
    $ps = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\.main' })
    if ($ps.Count -eq 0) { break }
    Write-Host "round $i : killing $($ps.Count) app.main process(es)"
    $ps | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}
$left = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\.main' }).Count
Write-Host "remaining after sweep: $left"
if ($left -gt 0) { Write-Host "ABORT: could not clear old mic"; Start-Sleep 5; exit 1 }
Start-Sleep -Seconds 2   # let the audio device fully release
# 2. start exactly ONE
Write-Host "starting ONE new build (owner-gate 0.60 + sensitivity)..."
$env:KESHEV_OWNER_FLOOR = "0.60"
$env:KESHEV_GATE = "0.020"
$env:KESHEV_LOGPROB_FLOOR = "-1.0"
$env:PYTHONIOENCODING = "utf-8"
Start-Process -FilePath "C:\Users\<user>\AppData\Local\Programs\Python\Python313\python.exe" -ArgumentList "-m","app.main" -WorkingDirectory "D:\CLAUDE\keshev-fable" -WindowStyle Minimized
Start-Sleep -Seconds 6
$now = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\.main' }).Count
Write-Host "now running: $now app.main process(es). Watch the KESHEV window for the meter."
Start-Sleep -Seconds 3
