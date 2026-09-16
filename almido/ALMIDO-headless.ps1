<#
    ALMIDO-headless.ps1 -- scripted entry point for ALMIDO (defect #14).
    ALMIDO = AlmIdo = עלמה ז"ל + עידו.

    Phase-2, claude-cli-ALMIDO2-launcher, 2026-09-06.

    Why this exists and not just `qwen -p ... ; if ($LASTEXITCODE -eq 0)`:
    verified live 2026-09-06 that a headless qwen-code run's *process* can take
    far longer to exit than the answer takes to arrive (auto-memory/dream
    bookkeeping keeps calling the model after the reply). Waiting on PROCESS
    EXIT as the completion signal is therefore unreliable. This script instead
    reads the `--output-format stream-json` line stream and treats the single
    `{"type":"result", ...}` line as truth: the moment it appears, the caller
    gets its answer back, whether or not the underlying qwen-code process has
    finished its own bookkeeping yet. The child process is never killed by
    this script -- only detached from (see NOTES at the bottom).

    Usage:
        ALMIDO-headless.ps1 -Prompt "Reply with exactly: pong"
        ALMIDO-headless.ps1 -Prompt "..." -MaxWallTimeSec 300 -Model qwen-coder-dgx4:latest

    Returns a [pscustomobject] on the pipeline (Success, IsError, ResultText,
    DurationToInitMs, DurationToResultMs, McpAllowlistOk, ...) and sets the
    process exit code:
        0 = success (result event, is_error:false)
        1 = model/tool run reported is_error:true
        2 = timed out before a result event ever arrived (process left running)
        3 = brain door did not answer the health gate
        4 = settings.json missing/unparsable or has no model.name
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Prompt,

    [int]$MaxWallTimeSec = 600,

    # Overrides the model read from settings.json. Leave unset to use whatever
    # config-safety currently has configured -- never hardcode a model id here.
    [string]$Model,

    # The directory qwen-code runs in. Defaults to almido\workspace (the scratch dir kept
    # out of D:\CLAUDE so D:\CLAUDE\.mcp.json is never inherited). ALMIDO's own repo is
    # D:\ALMIDO, created 2026-09-11, and a session working in it must start there --
    # qwen-code reads QWEN.md/context and resolves relative paths from the cwd.
    [string]$WorkDir,

    [string]$LogDir = $(Join-Path 'D:\CLAUDE\almido\workspace' 'logs'),

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ALMIDO-Common.ps1')

function Get-AlmidoResultProp {
    <# Safe property read under Set-StrictMode -Version Latest (ALMIDO-Common.ps1).
       A "result" stream-json event only carries .result/.subtype/.num_turns/.usage
       on subtype "success" -- an "error_during_execution" event lacks some of
       these, and StrictMode turns a plain missing-property read into a
       terminating exception instead of returning $null (observed live
       2026-09-10: crashed here before any summary could be written). #>
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    if ($Object.PSObject.Properties.Match($Name).Count -gt 0) { return $Object.$Name }
    return $null
}

if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
if (-not (Test-Path -LiteralPath $Script:AlmidoWorkspace)) { New-Item -ItemType Directory -Path $Script:AlmidoWorkspace -Force | Out-Null }

$qwenExe = Get-AlmidoQwenExe
$qwenVersion = Get-AlmidoQwenVersion -ExePath $qwenExe

$cfg = Get-AlmidoConfig
if (-not $cfg) {
    Write-Host 'ALMIDO-headless: settings.json missing/unparsable -- refusing to guess. תיקון נדרש.'
    exit 4
}
$modelId = if ($Model) { $Model } else { Get-AlmidoModelId -Config $cfg }
if (-not $modelId) {
    Write-Host 'ALMIDO-headless: no model.name in settings.json and no -Model override -- refusing to launch.'
    exit 4
}
$approvalMode = Get-AlmidoApprovalMode -Config $cfg
$cuEnabled    = Get-AlmidoComputerUseEnabled -Config $cfg
$mcpInfo      = Get-AlmidoAllowedMcp -Config $cfg
$slotStatus   = Test-AlmidoEran4SlotFree
$doorUrls     = Get-AlmidoDoorUrls -Config $cfg -ModelId $modelId

# Checks the door the SELECTED model (-Model override or settings.json's model.name) actually
# lives behind, not a hardcoded default -- 2026-09-07 wiring the big models in found this
# script's health gate always probed the qwen3-coder-next eran4:8450 door regardless of
# -Model, so e.g. -Model glm-5.2 (a different box/port entirely) would gate on the WRONG
# door's health. See Get-AlmidoDoorUrls in ALMIDO-Common.ps1 for the fix.
# ---- the gate must actually be armed before an unsupervised session ------
# 2026-09-11: "yolo" means nothing asks before a tool runs. The ONLY thing standing
# in front of the hands in that mode is Iddo's PreToolUse gate -- so if the gate does
# not actually answer, yolo is not autonomy, it is an unlocked door. Measured, then
# refused. (The measurement itself leaves one harmless row in the audit chain.)
$gateArmed = Test-AlmidoGateArmed -Config $cfg
$doorUp = Test-AlmidoBrainDoorUp -TimeoutSec 10 -Url $doorUrls.ModelsUrl -ApiKey $doorUrls.ApiKey
Write-AlmidoBanner -QwenExe $qwenExe -QwenVersion $qwenVersion -ModelId $modelId `
    -ApprovalMode $approvalMode -ComputerUseEnabled $cuEnabled -DoorUp $doorUp `
    -GateFound $mcpInfo.GateFound -GateNames $mcpInfo.GateNames -AllowedMcp $mcpInfo.Names `
    -SlotStatus $slotStatus -DoorUrls $doorUrls -GateArmed $gateArmed
if (-not $slotStatus.Free) {
    Write-Host '  NOTE: eran4 slot looks busy per RAMCHAT. This script does not block on that (the caller decides whether to proceed) -- claim/release it yourself around this call.'
}

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
    Write-Host 'ALMIDO-headless: brain door DOWN -- not starting qwen-code.'
    exit 3
}

# A command line cannot carry a newline on Windows: it is cut there, and every argument
# after it is lost with it (measured 2026-09-11 07:27 -- the genesis prompt arrived as its
# first line and -o stream-json never reached the CLI). A multi-line prompt therefore goes
# down stdin, which qwen-code reads as the prompt when -p is absent and which still emits
# stream-json. Single-line prompts keep the -p path exactly as it was.
$promptViaStdin = $Prompt.Contains("`n") -or $Prompt.Contains("`r")

$argList = [System.Collections.Generic.List[string]]::new()
if (-not $promptViaStdin) { [void]$argList.Add('-p'); [void]$argList.Add($Prompt) }
[void]$argList.Add('-o'); [void]$argList.Add('stream-json')
[void]$argList.Add('-m'); [void]$argList.Add($modelId)
[void]$argList.Add('--allowed-mcp-server-names'); [void]$argList.Add(($mcpInfo.Names -join ','))
[void]$argList.Add('--max-wall-time'); [void]$argList.Add([string]$MaxWallTimeSec)
# Verified 2026-09-10: settings.json's tools.approvalMode is NOT honoured under
# -p/headless (it silently stays at the most restrictive "Ask Permissions" mode
# regardless of the config value -- confirmed live: every write_file/
# run_shell_command call was denied with "Matching deny rule" even with
# approvalMode:auto in settings.json) -- only an explicit --approval-mode CLI
# flag actually changes it. Passing it here closes that gap.
if ($approvalMode) { [void]$argList.Add('--approval-mode'); [void]$argList.Add($approvalMode) }
if ($ExtraArgs) { foreach ($a in $ExtraArgs) { [void]$argList.Add($a) } }

$childEnv = Set-AlmidoChildEnvironment

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $qwenExe
$psi.Arguments = ConvertTo-AlmidoArgumentString -Arguments $argList
$runDir = if ($WorkDir) { (Resolve-Path -LiteralPath $WorkDir).Path } else { $Script:AlmidoWorkspace }
$psi.WorkingDirectory = $runDir
Write-Host "  working directory / תיקיית עבודה : $runDir"
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardInput = $promptViaStdin
if ($promptViaStdin) {
    $psi.StandardInputEncoding = [System.Text.UTF8Encoding]::new($false)
}
$psi.EnvironmentVariables.Clear()
foreach ($k in $childEnv.Keys) { $psi.EnvironmentVariables[$k] = [string]$childEnv[$k] }

if ($promptViaStdin) {
    Write-Host "  prompt is $(($Prompt -split "`n").Count) lines -- sending it on STDIN, not on the command line."
}
Write-Host "  launching (max wall time ${MaxWallTimeSec}s)... awaiting the stream-json result event, not process exit."

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$proc = [System.Diagnostics.Process]::new()
$proc.StartInfo = $psi
[void]$proc.Start()
try { $proc.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal } catch { }
if ($promptViaStdin) {
    $proc.StandardInput.Write($Prompt)
    $proc.StandardInput.Close()
}

$reader = $proc.StandardOutput
$rawLines = [System.Collections.Generic.List[string]]::new()
$initEvent = $null; $tInitMs = $null
$resultEvent = $null; $tResultMs = $null
$maxWallMs = $MaxWallTimeSec * 1000
$timedOut = $false

while ($true) {
    $remaining = $maxWallMs - $sw.ElapsedMilliseconds
    if ($remaining -le 0) { $timedOut = $true; break }
    $readTask = $reader.ReadLineAsync()
    if (-not $readTask.Wait([int]$remaining)) { $timedOut = $true; break }
    $line = $readTask.Result
    if ($null -eq $line) { break }   # child closed stdout (EOF)
    if ($line.Trim() -eq '') { continue }
    $rawLines.Add($line)
    try {
        $obj = $line | ConvertFrom-Json -ErrorAction Stop
    } catch {
        continue   # non-JSON stray line (e.g. a stray print) -- kept in the raw log, not parsed
    }
    if (-not $initEvent -and $obj.PSObject.Properties['type'] -and $obj.type -eq 'system') {
        $initEvent = $obj
        $tInitMs = $sw.ElapsedMilliseconds
    }
    if ($obj.PSObject.Properties['type'] -and $obj.type -eq 'result') {
        $resultEvent = $obj
        $tResultMs = $sw.ElapsedMilliseconds
        break
    }
}

# --- write the raw capture regardless of outcome, for audit/debugging -----
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$rawPath = Join-Path $LogDir "headless-$stamp.jsonl"
$rawLines | Set-Content -LiteralPath $rawPath -Encoding UTF8

# --- MCP allowlist check against what the init event actually reported ----
$mcpAllowlistOk = $null
$mcpServersActual = @()
if ($initEvent -and $initEvent.PSObject.Properties['mcp_servers']) {
    $mcpServersActual = @($initEvent.mcp_servers | ForEach-Object { $_.name })
    $expected = $mcpInfo.Names | Sort-Object -Unique
    $actual   = $mcpServersActual | Sort-Object -Unique
    $mcpAllowlistOk = (@(Compare-Object $expected $actual).Count -eq 0)
    $notConnected = @($initEvent.mcp_servers | Where-Object { $_.status -ne 'connected' })
    if ($notConnected.Count -gt 0) { $mcpAllowlistOk = $false }
}
$computerUseTools = @()
if ($initEvent -and $initEvent.PSObject.Properties['tools']) {
    $computerUseTools = @($initEvent.tools | Where-Object { $_ -like 'computer_use__*' })
}

$summary = [pscustomobject]@{
    Success             = ($resultEvent -and -not (Get-AlmidoResultProp $resultEvent 'is_error'))
    IsError             = if ($resultEvent) { [bool](Get-AlmidoResultProp $resultEvent 'is_error') } else { $null }
    TimedOut            = $timedOut
    ResultText          = Get-AlmidoResultProp $resultEvent 'result'
    ResultSubtype       = Get-AlmidoResultProp $resultEvent 'subtype'
    NumTurns            = Get-AlmidoResultProp $resultEvent 'num_turns'
    Usage               = Get-AlmidoResultProp $resultEvent 'usage'
    DurationToInitMs    = $tInitMs
    DurationToResultMs  = $tResultMs
    DurationTotalMs     = $sw.ElapsedMilliseconds
    McpServersExpected  = $mcpInfo.Names
    McpServersActual    = $mcpServersActual
    McpAllowlistOk      = $mcpAllowlistOk
    ToolCount           = if ($initEvent -and $initEvent.PSObject.Properties['tools']) { $initEvent.tools.Count } else { $null }
    ComputerUseToolsSeen = $computerUseTools.Count
    PermissionMode      = if ($initEvent) { $initEvent.permission_mode } else { $null }
    QwenCodeVersion     = if ($initEvent) { $initEvent.qwen_code_version } else { $qwenVersion }
    ProcessId           = $proc.Id
    ProcessStillRunning = -not $proc.HasExited
    RawLogPath          = $rawPath
}

Write-Host ''
if ($timedOut -and -not $resultEvent) {
    Write-Host "ALMIDO-headless: TIMED OUT after ${MaxWallTimeSec}s with no result event. / פג הזמן ללא תשובה."
    Write-Host "  process $($proc.Id) left running (not killed) -- it may still finish; check $rawPath."
} elseif ($resultEvent) {
    Write-Host "ALMIDO-headless: result received. is_error=$(Get-AlmidoResultProp $resultEvent 'is_error')  time-to-init=${tInitMs}ms  time-to-result=${tResultMs}ms (total run so far $($sw.ElapsedMilliseconds)ms)"
    Write-Host "  subtype: $(Get-AlmidoResultProp $resultEvent 'subtype')"
    Write-Host "  result: $(Get-AlmidoResultProp $resultEvent 'result')"
    if ($null -ne $mcpAllowlistOk) {
        Write-Host "  MCP allowlist: expected [$($mcpInfo.Names -join ', ')] actual [$($mcpServersActual -join ', ')] -> $(if ($mcpAllowlistOk) {'MATCH'} else {'MISMATCH'})"
    }
    Write-Host "  computer_use__* tools present in init event: $($computerUseTools.Count)"
    Write-Host "  process $($proc.Id) still running: $(-not $proc.HasExited)  (left detached -- not killed; its own bookkeeping, if any, may continue)"
}
Write-Host "  raw stream-json capture: $rawPath"

$summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $LogDir "headless-$stamp-summary.json") -Encoding UTF8

Write-Output $summary

if ($timedOut -and -not $resultEvent) { exit 2 }
elseif ($resultEvent -and (Get-AlmidoResultProp $resultEvent 'is_error')) { exit 1 }
else { exit 0 }

<#
NOTES:
  - This script never calls $proc.Kill(). Once a result event is seen, control
    returns to the caller; the qwen-code process may still be running its own
    post-answer bookkeeping (config-safety's memory.enableManagedAutoMemory /
    enableManagedAutoDream settings determine whether that happens at all --
    both are currently set to false in settings.json, verified 2026-09-06, so
    in the common case the process should exit on its own shortly after the
    result line). If a caller needs the process gone, it owns that decision:
    Stop-Process -Id $summary.ProcessId -Force.
  - --max-wall-time is passed to qwen-code itself as a second, independent
    backstop budget inside the CLI (verified present in 0.21.4's yargs
    options); this script's own $MaxWallTimeSec loop is the one that actually
    matters for the CALLER, since it does not wait on the child at all beyond
    that budget.
  - RAMCHAT's eran4-slot convention is read and reported, never enforced here
    -- claiming/releasing the slot is the calling agent's responsibility
    (see CLAUDE.md's swarm rule), exactly as for the interactive launcher.
#>
