# Interactive launcher for haiku-wa. Prompts for ANTHROPIC_API_KEY (hidden),
# sets it in env only (never written to disk), then runs index.js with auto-restart.
# לזכרה של עלמה ז״ל — iddoperez.ai

$Host.UI.RawUI.WindowTitle = "Claude — Haiku-WA"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "Claude — Haiku-WA launcher" -ForegroundColor Cyan
Write-Host "  Paste ANTHROPIC_API_KEY when prompted (input is hidden)."
Write-Host "  First launch: scan the QR with WhatsApp -> Linked Devices."
Write-Host "  Auto-restart on crash. Ctrl+C twice to exit."
Write-Host ""

if (-not $env:ANTHROPIC_API_KEY) {
    $sec = Read-Host "ANTHROPIC_API_KEY (sk-ant-...)" -AsSecureString
    $env:ANTHROPIC_API_KEY = [System.Net.NetworkCredential]::new('', $sec).Password
    if (-not $env:ANTHROPIC_API_KEY -or $env:ANTHROPIC_API_KEY.Length -lt 20) {
        Write-Host "Key looks empty/short. Aborting." -ForegroundColor Red
        exit 1
    }
    Write-Host ("Key accepted ({0} chars). Starting bot..." -f $env:ANTHROPIC_API_KEY.Length) -ForegroundColor Green
} else {
    Write-Host "Using existing ANTHROPIC_API_KEY from shell env." -ForegroundColor Yellow
}

while ($true) {
    & node index.js
    Write-Host ""
    Write-Host "=== bot exited, restart in 5s (Ctrl+C twice to abort) ===" -ForegroundColor DarkGray
    Start-Sleep -Seconds 5
}
