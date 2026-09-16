# EMDR_Widget smoke test.
#
# What this proves that the old version did NOT:
#   * it targets a path that actually exists (the old one pointed at
#     D:\NEWCLAUDE\EMDR\dist\EMDR_Widget.exe, which is not there);
#   * it OPENS THE SETTINGS DIALOG, which is the thing that was crashing.
#     The old test only asserted "still alive after 5 seconds", which the
#     broken build passed every single time;
#   * it launches DETACHED, so sys.stderr is None exactly as it is when Iddo
#     double-clicks the shortcut. Run from a terminal, stderr is a real
#     stream and the whole class of bug is invisible;
#   * it runs offscreen, so nothing appears on his screen;
#   * it does NOT Stop-Process -Force the app. That kill is precisely what
#     can stranded a channel volume when System-audio mode is running.
#
# Usage:  .\_smoketest.ps1  [-Exe <path to EMDR_Widget.exe>]

param(
    [string]$Exe = (Join-Path $PSScriptRoot 'dist\EMDR_Widget.exe'),
    [string]$LogDir = 'D:\NEWCLAUDE\EMDR\logs'
)

if (-not (Test-Path $Exe)) {
    Write-Output "FAIL: exe not found: $Exe"
    exit 2
}

$log = Join-Path $LogDir ("{0}.log" -f (Get-Date -Format 'yyyyMMdd'))
$before = if (Test-Path $log) { (Get-Content $log).Count } else { 0 }

$env:QT_QPA_PLATFORM = 'offscreen'
$p = Start-Process -FilePath $Exe -ArgumentList '--selftest' -PassThru -WindowStyle Hidden
$exited = $p.WaitForExit(90000)

if (-not $exited) {
    Write-Output "FAIL: --selftest did not finish within 90 s (pid $($p.Id) left running)"
    exit 1
}

$new = if (Test-Path $log) { Get-Content $log | Select-Object -Skip $before } else { @() }
$new | ForEach-Object { Write-Output "    $_" }

$ok = ($p.ExitCode -eq 0) -and ($new -match 'SELFTEST OK')
$windowed = $new -match 'stderr_is_None=True'

if ($ok) {
    Write-Output "OK: Settings dialog opened in the frozen build. ExitCode=$($p.ExitCode)"
    if (-not $windowed) {
        Write-Output "WARNING: stderr was a real stream in this run, so the"
        Write-Output "         windowed crash condition was NOT exercised."
    }
    exit 0
}

Write-Output "FAIL: ExitCode=$($p.ExitCode); no 'SELFTEST OK' line in $log"
exit 1
