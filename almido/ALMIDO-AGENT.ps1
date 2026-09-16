<#
    ALMIDO-AGENT.ps1 -- interactive launcher for the ALMIDO harness.
    ALMIDO = AlmIdo = עלמה ז"ל + עידו.

    Phase-2 rewrite (defect #8), claude-cli-ALMIDO2-launcher, 2026-09-06, modelled on
    D:\CLAUDE\RAMCHAT\start-remote-claude.ps1's health-gate / fail-closed shape.

    What changed from the old ALMIDO-AGENT.cmd (backed up next to this file as
    ALMIDO-AGENT.cmd.bak-p2-20260906) and why:
      - no OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL env vars. The model is
        declared INSIDE ~/.qwen/settings.json's modelProviders (SHARED CONTRACT),
        which carries the tuned timeout/context/temperature; setting OPENAI_MODEL
        to an id outside modelProviders (the old bug) silently drops all of that.
      - qwen-code binary is pinned to the exact verified path, not a bare `qwen`
        that depends on PATH order between the 0.21.4 and 0.21.0 installs.
      - --allowed-mcp-server-names is passed explicitly. Verified 2026-09-06 by
        reading the CLI source: settings.json's own "mcp.allowed" key is ONLY
        honoured when NOT running under `-p` (bareMode) -- i.e. it silently does
        nothing for headless/scripted runs. The explicit flag works in both
        modes and is checked first, so it is passed here unconditionally.
      - a real health gate: the brain door is polled before qwen ever starts,
        and the banner states the approval mode / gate-registration / screen-
        hands state exactly as read from settings.json at this moment -- never
        as a promise from a comment in this file.
      - BELOW_NORMAL priority (Iddo's PC-wide law: nothing above BELOW_NORMAL).
        Start-Process has no -PriorityClass parameter in PowerShell 7.6.5 on
        this box (verified with Get-Command) despite the design brief's text
        assuming one exists; priority is set on the live process object instead.
      - cwd = almido\workspace, so D:\CLAUDE\.mcp.json (wa-mcp, broken; ramchat
        posting as "deskclod") is never inherited.
      - no `pause` at exit.

    Undo: delete this file and ALMIDO-Common.ps1, restore
    D:\CLAUDE\almido\ALMIDO-AGENT.cmd from ALMIDO-AGENT.cmd.bak-p2-20260906.
#>

[CmdletBinding()]
param(
    # Runs the health gate + banner and exits (0 if the door is up and a model
    # is configured, 1 otherwise) without ever starting qwen-code. For smoke
    # tests and for checking config state from a non-interactive shell.
    [switch]$TestOnly,

    # Overrides the model read from settings.json's model.name -- e.g. -Model glm-5.2 for
    # Colibri, -Model gpt-oss-120b for the eran2 120B. Any id present in settings.json's
    # modelProviders.openai array is selectable this way (2026-09-07, wiring the big models
    # in: mirrors the -Model switch ALMIDO-headless.ps1 already had -- same mechanism, now
    # available interactively too, per Iddo's "prefer the harness's own existing mechanism"
    # order). Leave unset to use whatever settings.json currently configures; this never
    # rewrites the file, so the override lasts only for this one run.
    [string]$Model,

    # The directory qwen-code runs in. Defaults to almido\workspace (the scratch dir kept
    # out of D:\CLAUDE so D:\CLAUDE\.mcp.json is never inherited). ALMIDO's own repo is
    # D:\ALMIDO, created 2026-09-11, and a session working in it must start there --
    # qwen-code reads QWEN.md/context and resolves relative paths from the cwd.
    [string]$WorkDir,

    # Extra args passed straight through to qwen-code (e.g. -i "some prompt").
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ALMIDO-Common.ps1')

if (-not (Test-Path -LiteralPath $Script:AlmidoWorkspace)) {
    New-Item -ItemType Directory -Path $Script:AlmidoWorkspace -Force | Out-Null
}

$qwenExe = Get-AlmidoQwenExe
$qwenVersion = Get-AlmidoQwenVersion -ExePath $qwenExe

$cfg = Get-AlmidoConfig
if (-not $cfg) {
    Write-Host "ALMIDO: $Script:AlmidoSettingsPath is missing or unparsable -- refusing to guess a model or MCP allowlist. תיקון הקובץ נדרש לפני הפעלה."
    exit 1
}

$modelId      = if ($Model) { $Model } else { Get-AlmidoModelId -Config $cfg }
$approvalMode = Get-AlmidoApprovalMode -Config $cfg
$cuEnabled    = Get-AlmidoComputerUseEnabled -Config $cfg
$mcpInfo      = Get-AlmidoAllowedMcp -Config $cfg
$doorUrls     = Get-AlmidoDoorUrls -Config $cfg -ModelId $modelId

# ---- health gate: fail closed if the brain door does not answer ----------
# Checks the door the SELECTED model actually lives behind (Get-AlmidoDoorUrls), not a
# hardcoded default -- see that function's comment for the bug this replaced.
# ---- the gate must actually be armed before an unsupervised session ------
# 2026-09-11: "yolo" means nothing asks before a tool runs. The ONLY thing standing
# in front of the hands in that mode is Iddo's PreToolUse gate -- so if the gate does
# not actually answer, yolo is not autonomy, it is an unlocked door. Measured, then
# refused. (The measurement itself leaves one harmless row in the audit chain.)
$gateArmed = Test-AlmidoGateArmed -Config $cfg
$doorUp = Test-AlmidoBrainDoorUp -TimeoutSec 10 -Url $doorUrls.ModelsUrl -ApiKey $doorUrls.ApiKey
$slotStatus = Test-AlmidoEran4SlotFree

Write-AlmidoBanner -QwenExe $qwenExe -QwenVersion $qwenVersion -ModelId $modelId `
    -ApprovalMode $approvalMode -ComputerUseEnabled $cuEnabled -DoorUp $doorUp `
    -GateFound $mcpInfo.GateFound -GateNames $mcpInfo.GateNames -AllowedMcp $mcpInfo.Names `
    -SlotStatus $slotStatus -DoorUrls $doorUrls -GateArmed $gateArmed

if (-not $gateArmed.Armed -and $approvalMode -eq 'yolo') {
    Write-Host ''
    Write-Host 'ALMIDO: REFUSING to start. approvalMode is "yolo" (nothing asks before a tool runs)'
    Write-Host "        and Iddo's policy gate is NOT ARMED: $($gateArmed.Reason)"
    Write-Host '        qwen-code treats a failed hook as PROCEED, so this session would be'
    Write-Host '        completely ungated and completely unaudited.'
    Write-Host '        השער לא עונה -- לא מפעיל סשן ללא שער במצב yolo.'
    Write-Host '        Fix: check the hook command in ~/.qwen/settings.json runs under cmd.exe,'
    Write-Host '        or lower tools.approvalMode below yolo so a human is asked instead.'
    exit 5
}
if (-not $gateArmed.Armed) {
    Write-Host ''
    Write-Host "ALMIDO WARNING: the policy gate is NOT ARMED ($($gateArmed.Reason))."
    Write-Host "        approvalMode is '$approvalMode', so qwen-code will still ask before acting --"
    Write-Host '        but nothing will be written to the audit chain. / השער לא פעיל.'
}

if (-not $doorUp) {
    Write-Host 'ALMIDO: brain door is DOWN. Refusing to launch a session with no brain. / דלת המוח לא עונה - לא מפעיל.'
    exit 1
}
if (-not $modelId) {
    Write-Host 'ALMIDO: no model.name in settings.json -- refusing to launch with an undefined model.'
    exit 1
}

if ($TestOnly) {
    Write-Host 'ALMIDO: -TestOnly given -- health gate passed, stopping before starting qwen-code.'
    exit 0
}

if ($slotStatus.Free) {
    Write-Host '  warming the prompt cache in the background (fire-and-forget, will not block this session)...'
    Start-AlmidoCacheWarm -ModelId $modelId -ChatUrl $doorUrls.ChatUrl -ApiKey $doorUrls.ApiKey | Out-Null
} else {
    Write-Host '  eran4 slot is busy -- skipping the cache warm so this session does not compete for the single slot.'
}

$childEnv = Set-AlmidoChildEnvironment

$argList = [System.Collections.Generic.List[string]]::new()
[void]$argList.Add('-m'); [void]$argList.Add($modelId)
[void]$argList.Add('--allowed-mcp-server-names'); [void]$argList.Add(($mcpInfo.Names -join ','))
# Verified 2026-09-10: settings.json's tools.approvalMode is NOT honoured under
# qwen-code's -p/headless path (it silently stays at the most restrictive "Ask
# Permissions" mode regardless of the config value) -- only an explicit
# --approval-mode CLI flag actually changes it. Passing it here closes that gap
# so the config file is the single source of truth again, same as every other
# setting this launcher already reads and forwards explicitly.
if ($approvalMode) { [void]$argList.Add('--approval-mode'); [void]$argList.Add($approvalMode) }
if ($ExtraArgs) { foreach ($a in $ExtraArgs) { [void]$argList.Add($a) } }

Write-Host 'Ctrl+C twice to leave. Tools ask before they act only to the extent the approval mode above says so -- that line is read from config, not promised here.'
Write-Host ''

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $qwenExe
$psi.Arguments = ConvertTo-AlmidoArgumentString -Arguments $argList
$runDir = if ($WorkDir) { (Resolve-Path -LiteralPath $WorkDir).Path } else { $Script:AlmidoWorkspace }
$psi.WorkingDirectory = $runDir
Write-Host "  working directory / תיקיית עבודה : $runDir"
$psi.UseShellExecute = $false
$psi.EnvironmentVariables.Clear()
foreach ($k in $childEnv.Keys) { $psi.EnvironmentVariables[$k] = [string]$childEnv[$k] }

$proc = [System.Diagnostics.Process]::new()
$proc.StartInfo = $psi
[void]$proc.Start()
try {
    $proc.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
} catch {
    Write-Host "  (could not set BELOW_NORMAL priority: $($_.Exception.Message))"
}
$proc.WaitForExit()
exit $proc.ExitCode
