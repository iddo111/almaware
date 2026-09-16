# ALMAWARE — Reset / wipe the Hebrew mic learned state, then restart clean.
# Backs up the profile + history first (REVERSIBLE), then clears the accumulated
# data that fuels readback + personalization, and relaunches the mic fresh.
# לזכרה של עלמה ז"ל — iddoperez.ai
$ErrorActionPreference = 'Continue'
$VI   = 'D:\CLAUDE\voice-input'
$prof = Join-Path $VI 'profiles\iddo1'
$hist = Join-Path $VI 'history'
$PY   = 'C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe'
$ts   = Get-Date -Format 'yyyyMMdd_HHmmss'
$bk   = Join-Path $VI "_reset_backups\reset_$ts"

Write-Host "[reset-mic] stopping mic..."
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'voice_input' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue }
Start-Sleep 2

Write-Host "[reset-mic] backing up to $bk ..."
New-Item -ItemType Directory -Force -Path $bk | Out-Null
if (Test-Path $prof) { Copy-Item $prof (Join-Path $bk 'profile_iddo1') -Recurse -Force -EA SilentlyContinue }
if (Test-Path $hist) { Copy-Item $hist (Join-Path $bk 'history') -Recurse -Force -EA SilentlyContinue }

Write-Host "[reset-mic] wiping learned state (vocab / samples / corrections / history / recordings / cache)..."
Set-Content (Join-Path $prof 'vocab.json') '{}' -Encoding utf8 -EA SilentlyContinue
Clear-Content (Join-Path $prof 'samples.jsonl')     -EA SilentlyContinue
Clear-Content (Join-Path $prof 'corrections.jsonl') -EA SilentlyContinue
Get-ChildItem (Join-Path $prof 'samples') -File -EA SilentlyContinue | Remove-Item -Force -EA SilentlyContinue
Get-ChildItem $hist -Filter *.txt -EA SilentlyContinue | Remove-Item -Force -EA SilentlyContinue
Remove-Item (Join-Path $VI '__pycache__') -Recurse -Force -EA SilentlyContinue
# NOTE: config.json and rules.json are KEPT (intentional settings, not learned data).

Write-Host "[reset-mic] restarting clean..."
Start-Process -WindowStyle Hidden $PY -ArgumentList "$VI\voice_input.py", '--vad' -WorkingDirectory $VI
Start-Sleep 2
$n = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'voice_input' }
Write-Host ""
Write-Host "[reset-mic] DONE."
Write-Host "  backup saved : $bk"
Write-Host "  mic running  : $(@($n).Count) instance(s)"
Write-Host "(close this window)"
Start-Sleep 4
