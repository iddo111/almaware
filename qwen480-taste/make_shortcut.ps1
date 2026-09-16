# Desktop + Start Menu shortcut for ALMAWARE Coder (coder_desktop.py), the
# PyQt6 desktop app for Qwen3-Coder-480B. Mirrors the house convention in
# D:\CLAUDE\emdr\source-emdr-central\_make_shortcut.ps1: a plain pythonw.exe
# launch (acceptable minimum per Iddo's own bar -- "double-click an app", not
# "run a script"), icon set explicitly so it does not just show a blank
# Python icon in the taskbar/Start Menu. Points at Python 3.13 by default --
# that is the interpreter coder_desktop.py's own RUN-ALMAWARE-CODER.cmd
# targets (verified 2026-09-09: PyQt6 6.11.0 fully installed there, not just
# a stub) -- a direct pythonw.exe .lnk skips the brief console flash that
# RUN-ALMAWARE-CODER.cmd's `start` command would otherwise cause.
#
# Usage:  .\make_shortcut.ps1
#         .\make_shortcut.ps1 -PythonW "C:\Program Files\Python312\pythonw.exe"

param(
    [string]$PythonW = "$env:LOCALAPPDATA\Programs\Python\Python313\pythonw.exe",
    [string]$Script  = (Join-Path $PSScriptRoot 'coder_desktop.py'),
    [string]$Icon    = (Join-Path $PSScriptRoot 'almaware-coder.ico')
)

if (-not (Test-Path $PythonW)) { Write-Output "FAIL: pythonw not found: $PythonW"; exit 2 }
if (-not (Test-Path $Script))  { Write-Output "FAIL: script not found: $Script";  exit 2 }

$targets = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'ALMAWARE Coder.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'ALMAWARE Coder.lnk')
)

$wsh = New-Object -ComObject WScript.Shell
foreach ($lnk in $targets) {
    $s = $wsh.CreateShortcut($lnk)
    $s.TargetPath = $PythonW
    $s.Arguments = "`"$Script`""
    $s.WorkingDirectory = $PSScriptRoot
    if (Test-Path $Icon) { $s.IconLocation = $Icon }
    $s.Description = 'ALMAWARE Coder -- desktop app for Qwen3-Coder-480B (conversations, workspaces, RAG, full memory)'
    $s.Save()
    if (Test-Path $lnk) { Write-Output "OK: $lnk" } else { Write-Output "FAIL: $lnk" }
}
