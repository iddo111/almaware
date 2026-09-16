# Check what's currently running for the bank backup.
$ErrorActionPreference = 'SilentlyContinue'
Write-Output '=== python procs ==='
Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, StartTime, WS, ProcessName | Format-Table -AutoSize
Write-Output '=== robocopy procs ==='
Get-Process robocopy -ErrorAction SilentlyContinue | Select-Object Id, StartTime, WS | Format-Table -AutoSize
Write-Output '=== pc-run-stdout tail ==='
if (Test-Path 'N:\_logs\pc-run-stdout.log') {
    Get-Content 'N:\_logs\pc-run-stdout.log' -Tail 30 -ErrorAction SilentlyContinue
}
Write-Output '=== pc-run-stderr tail ==='
if (Test-Path 'N:\_logs\pc-run-stderr.log') {
    Get-Content 'N:\_logs\pc-run-stderr.log' -Tail 10 -ErrorAction SilentlyContinue
}
Write-Output '=== PC state ==='
if (Test-Path 'N:\PC\_state.json') {
    Get-Content 'N:\PC\_state.json'
}
