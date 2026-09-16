# Darwish daily review — pull the newest generated sample, log a PENDING rating row,
# keep the clickable player alive. Does NOT auto-play (Sacred Audio Law: never touch his audio).
$ErrorActionPreference = 'Continue'
$base   = 'D:\CLAUDE\darwish-ai'
$gen    = 'D:\Darwish\generated'
$ledger = 'D:\CLAUDE\darwish-ai\darwish_ratings.csv'

# 1. pull newest samples from eran3
try { & powershell -NoProfile -File "$base\pull_samples.ps1" 2>$null } catch {}

# 2. find newest real generated sample (skip the _ear_smoke codec test)
$newest = Get-ChildItem "$gen\*.mp3" -ErrorAction SilentlyContinue |
          Where-Object { $_.Name -notlike '_ear*' } |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($newest) {
    $step = if ($newest.BaseName -match 'step(\d+)') { $matches[1] } else { '?' }
    $date = Get-Date -Format 'yyyy-MM-dd'
    if (-not (Test-Path $ledger)) { 'date,step,file,iddo_pct,note' | Out-File $ledger -Encoding utf8 }
    $seen = Select-String -Path $ledger -Pattern ([regex]::Escape($newest.Name)) -Quiet -ErrorAction SilentlyContinue
    if (-not $seen) { "$date,$step,$($newest.Name),,PENDING" | Out-File $ledger -Append -Encoding utf8 }
}

# 3. keep the clickable player (http://127.0.0.1:8831) alive — no audio played, just served
$up = Test-NetConnection -ComputerName 127.0.0.1 -Port 8831 -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $up) {
    Start-Process -WindowStyle Hidden 'C:\Program Files\Python312\python.exe' `
        -ArgumentList "$base\serve_samples.py" -WorkingDirectory $base
}
