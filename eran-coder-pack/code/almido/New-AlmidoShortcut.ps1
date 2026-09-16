<#
    New-AlmidoShortcut.ps1 -- (re)creates the Desktop\ALMIDO.lnk shortcut.
    ALMIDO = AlmIdo = עלמה ז"ל + עידו.

    Per CLAUDE.md's CLICKABLE-ACCESS LAW: a .lnk is a clickable way to reach
    ALMIDO for Iddo -- never a raw D:\ path pasted as prose. This shortcut
    opens Windows Terminal at NORMAL (non-elevated, medium) integrity, never
    "Run as administrator" -- verified after creation by reading the .lnk
    header's RunAsAdministrator flag bit (offset 21, bit 0x20) directly.

    claude-cli-ALMIDO2-launcher, 2026-09-06.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$wtPath = 'C:\Users\<user>\AppData\Local\Microsoft\WindowsApps\wt.exe'
if (-not (Test-Path -LiteralPath $wtPath)) {
    Write-Host "New-AlmidoShortcut: Windows Terminal not found at $wtPath -- falling back to cmd.exe directly (no tabs)."
    $wtPath = "$env:WINDIR\System32\cmd.exe"
    $wtArgs = '/k "D:\CLAUDE\almido\ALMIDO-AGENT.cmd"'
} else {
    $wtArgs = '-d "D:\CLAUDE\almido" cmd.exe /k ALMIDO-AGENT.cmd'
}

$lnkPath = Join-Path $env:USERPROFILE 'Desktop\ALMIDO.lnk'
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($lnkPath)
$shortcut.TargetPath = $wtPath
$shortcut.Arguments = $wtArgs
$shortcut.WorkingDirectory = 'D:\CLAUDE\almido'
$shortcut.Description = 'ALMIDO AGENT - Qwen3-Coder-Next on eran4, hands on the PC (non-elevated)'
$shortcut.Save()

$bytes = [System.IO.File]::ReadAllBytes($lnkPath)
$runAsAdmin = [bool]($bytes[21] -band 0x20)
if ($runAsAdmin) {
    Write-Host "New-AlmidoShortcut: WARNING -- the created shortcut has the RunAsAdministrator bit SET. This should never happen from this script; delete $lnkPath and investigate."
    exit 1
}
Write-Host "New-AlmidoShortcut: created $lnkPath (non-elevated, verified)."
