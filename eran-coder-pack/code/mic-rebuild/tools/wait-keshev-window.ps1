# Launcher helper (2026-08-25): keeps RUN-KESHEV.cmd's console alive until
# the real KESHEV window exists, so a double-click gives instant, honest
# feedback instead of ~70 blind seconds while the engine warms.
# UI-only - polls process window titles; never touches the app or audio.
# (FindWindowW with the Hebrew title proved unreliable from PowerShell;
# Get-Process MainWindowTitle is codepage-safe and scoped to pythonw only.)
$deadline = (Get-Date).AddSeconds(180)
while ((Get-Date) -lt $deadline) {
    $w = Get-Process pythonw -ErrorAction SilentlyContinue |
         Where-Object { $_.MainWindowTitle -like "*KESHEV*" }
    if ($w) { exit 0 }
    Start-Sleep -Milliseconds 1500
}
# 3 minutes with no window: leave a visible trace instead of vanishing.
Write-Host ""
Write-Host "  KESHEV window did not appear within 3 minutes."
Write-Host "  Check state\events.jsonl in D:\CLAUDE\mic-rebuild."
Start-Sleep -Seconds 20
exit 1
