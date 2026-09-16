# Desktop shortcut for the EMDR widget.
#
# The old version of this script was dead: it pointed at C:\Python314\pythonw.exe
# (no such interpreter on this machine) and D:\NEWCLAUDE\EMDR\emdr_widget.py
# (no such file - that folder holds only logs\). It would have produced a
# shortcut that silently did nothing.
#
# It now points at the built EXE, which is how the app is actually launched.
#
# Usage:  .\_make_shortcut.ps1  [-Exe <path to EMDR_Widget.exe>]

param(
    [string]$Exe = (Join-Path $PSScriptRoot 'dist\EMDR_Widget.exe')
)

if (-not (Test-Path $Exe)) {
    Write-Output "FAIL: exe not found: $Exe"
    Write-Output "      Build it first, or pass -Exe <path>."
    exit 2
}

$Exe = (Resolve-Path $Exe).Path
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'EMDR Widget.lnk'

$wsh = New-Object -ComObject WScript.Shell
$s = $wsh.CreateShortcut($lnk)
$s.TargetPath = $Exe
$s.WorkingDirectory = (Split-Path $Exe -Parent)
$s.IconLocation = $Exe
$s.Description = 'EMDR Widget - bilateral stimulation (equal-power stereo pan)'
$s.Save()

if (Test-Path $lnk) { Write-Output "OK: $lnk  ->  $Exe" } else { Write-Output "FAIL"; exit 1 }
