@echo off
rem ALMIDO AGENT -- thin wrapper. All logic lives in ALMIDO-AGENT.ps1 (Phase-2 rewrite,
rem claude-cli-ALMIDO2-launcher, 2026-09-06). Old body backed up as ALMIDO-AGENT.cmd.bak-p2-20260906.
rem Prefers PowerShell 7 (pwsh); ALMIDO-AGENT.ps1 avoids .NET-Core-only APIs so it also
rem runs under Windows PowerShell 5.1 if pwsh is ever missing, but pwsh is what this
rem machine has and is what was tested.
where pwsh.exe >nul 2>nul
if %ERRORLEVEL%==0 (
    pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ALMIDO-AGENT.ps1" %*
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ALMIDO-AGENT.ps1" %*
)
