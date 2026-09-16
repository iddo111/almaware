@echo off
setlocal
rem ============================================================================
rem  ALMIDO gate hook -- shell wrapper.  2026-09-11, claude-cli-FABLE-almido.
rem
rem  THE SCAR THIS FIXES (measured 2026-09-11 07:09, qwen-code 0.21.4 debug log):
rem    ~/.qwen/settings.json used to invoke the gate directly as
rem        "C:\Program Files\Python312\python.exe" -X utf8 "D:\...\almido_gate_hook.py"
rem    qwen-code runs a hook command through a shell it picks from the ENVIRONMENT
rem    (getShellConfiguration): Git Bash when MSYSTEM/TERM say so, otherwise
rem    %ComSpec% with /d /s /c.  Node escapes the inner quotes as \" , which cmd.exe
rem    does not understand, so under cmd.exe the hook died with
rem        '"C:\Program Files\Python312\python.exe"' is not recognized ...
rem    and qwen-code treats a FAILED hook as "proceed" -- silently.  So the policy
rem    gate was open for every session started from PowerShell or cmd (which is
rem    every session started by ALMIDO-AGENT.ps1 / ALMIDO-headless.ps1), and only
rem    worked for sessions started from Git Bash.  8 headless runs -> 0 audit rows.
rem
rem  THE FIX: settings.json now names THIS FILE, by a path with forward slashes,
rem  no spaces and no quotes:  D:/CLAUDE/iddo-harness/almido-gate-hook.cmd
rem  Verified to execute identically under  cmd /d /s /c ,  bash -c , and
rem  powershell -Command .  All quoting lives inside this file, where cmd's own
rem  batch rules apply and nothing escapes it.
rem
rem  FAIL CLOSED: if the interpreter cannot be found, this does NOT fall through
rem  to "no opinion" -- it prints a deny decision.  A gate that cannot run has no
rem  opinion, and no opinion means no.
rem ============================================================================

set "ALMIDO_GATE_PY=C:\Program Files\Python312\python.exe"
set "ALMIDO_GATE_SCRIPT=D:\CLAUDE\iddo-harness\almido_gate_hook.py"
set "PYTHONIOENCODING=utf-8"

if not exist "%ALMIDO_GATE_SCRIPT%" goto :nogate

if exist "%ALMIDO_GATE_PY%" (
    "%ALMIDO_GATE_PY%" -X utf8 "%ALMIDO_GATE_SCRIPT%" %*
    exit /b %ERRORLEVEL%
)

rem Fallback: the Windows py launcher (C:\Windows\py.exe, no space in its path).
where py.exe >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 -X utf8 "%ALMIDO_GATE_SCRIPT%" %*
    exit /b %ERRORLEVEL%
)

:nogate
echo {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"ALMIDO gate wrapper failed closed: neither '%ALMIDO_GATE_PY%' nor 'py' could run '%ALMIDO_GATE_SCRIPT%'. A gate that cannot run has no opinion, and no opinion means no."}}
exit /b 0
