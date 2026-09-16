<#
    ALMIDO-Common.ps1
    Shared helpers for ALMIDO-AGENT.ps1 (interactive) and ALMIDO-headless.ps1 (scripted).
    ALMIDO = AlmIdo = עלמה ז"ל + עידו. The name is a memorial; never reword it.

    Phase-2 launcher owner: claude-cli-ALMIDO2-launcher, 2026-09-06 (Iddo's order 09-06 11:16).
    Everything here READS config at call time. Nothing here promises a state without checking it
    first -- per Iddo's standing law: "a health endpoint is not the real output."

    Backups: this file is new (no prior version to back up).
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---- fixed, verified locations (not guesses) -----------------------------
# Verified 2026-09-06: bare `qwen` on PATH resolves to this exact file (0.21.4).
# The npm copy at %APPDATA%\npm\qwen.cmd is 0.21.0 and is a DIFFERENT install --
# never used implicitly here; pinned explicitly so a PATH change elsewhere on
# this machine cannot silently switch which qwen-code build ALMIDO runs.
$Script:AlmidoQwenExePinned = 'C:\Users\<user>\AppData\Local\qwen-code\bin\qwen.cmd'
$Script:AlmidoRoot          = 'D:\CLAUDE\almido'
$Script:AlmidoWorkspace     = Join-Path $Script:AlmidoRoot 'workspace'
$Script:AlmidoSettingsPath  = Join-Path $env:USERPROFILE '.qwen\settings.json'
$Script:AlmidoRamlinkPy     = 'D:\CLAUDE\RAMCHAT\ramlink.py'
$Script:AlmidoQwenEnvPath   = Join-Path $env:USERPROFILE '.qwen\.env'
$Script:AlmidoDoorModelsUrl = 'https://<tailnet-host>:8450/v1/models'
$Script:AlmidoDoorChatUrl   = 'https://<tailnet-host>:8450/v1/chat/completions'
# The doors every ALMIDO session gets regardless of what else is registered
# in settings.json (SHARED CONTRACT, 2026-09-06). Until 2026-09-10 this was
# deliberately just the first three, with desktop-commander/almaware-connector
# excluded on purpose. Iddo 2026-09-10 18:22+18:28 overrode that: "קלוד בדיוק
# כמוך" + "הכל מהכל עם כל ה-MCP" (everything, with every MCP) -- so both are
# added now, by explicit instruction, not because the old exclusion was a bug.
$Script:AlmidoBaseAllowedMcp = @('almido', 'alma-recall', 'ramchat-qwen', 'desktop-commander', 'almaware-connector')

function Get-AlmidoQwenExe {
    <# Returns the pinned qwen-code path, or throws with a clear bilingual message
       if it has moved -- never silently fall back to a bare `qwen` on PATH. #>
    if (Test-Path -LiteralPath $Script:AlmidoQwenExePinned -PathType Leaf) {
        return $Script:AlmidoQwenExePinned
    }
    throw ("ALMIDO: pinned qwen-code not found at $Script:AlmidoQwenExePinned " +
           "(qwen-code הצמוד לא נמצא בנתיב). Re-verify the install before relying on PATH order.")
}

function Get-AlmidoQwenVersion {
    param([string]$ExePath)
    try {
        $v = & $ExePath --version 2>$null
        return ($v | Select-Object -First 1).ToString().Trim()
    } catch {
        return $null
    }
}

function Get-AlmidoConfig {
    <# Parses ~/.qwen/settings.json fresh every call. Returns $null (not a throw)
       if it is missing or malformed -- callers must treat $null as "unknown",
       never as "safe defaults". #>
    if (-not (Test-Path -LiteralPath $Script:AlmidoSettingsPath -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $Script:AlmidoSettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-AlmidoModelId {
    param($Config)
    if ($Config -and $Config.PSObject.Properties['model'] -and $Config.model.PSObject.Properties['name']) {
        return $Config.model.name
    }
    return $null
}

function Get-AlmidoApprovalMode {
    param($Config)
    if ($Config -and $Config.PSObject.Properties['tools'] -and $Config.tools.PSObject.Properties['approvalMode']) {
        return [string]$Config.tools.approvalMode
    }
    return $null
}

function Get-AlmidoComputerUseEnabled {
    <# Returns $true / $false when the config states it explicitly, $null when unknown.
       $null must be reported as "unknown", never assumed false. #>
    param($Config)
    if ($Config -and $Config.PSObject.Properties['tools'] -and
        $Config.tools.PSObject.Properties['computerUse'] -and
        $Config.tools.computerUse.PSObject.Properties['enabled']) {
        return [bool]$Config.tools.computerUse.enabled
    }
    return $null
}

function Get-AlmidoEnvValue {
    <# Reads one KEY=VALUE line from ~/.qwen/.env (plain dotenv, no quoting/expansion -- matches
       how OLLAMA_API_KEY / FLEET_API_KEY / COLI_API_KEY are already written there). Returns
       $null if the file or the key is missing. Callers use this ONLY to build an Authorization
       header for a health/warm probe -- never print or log the return value. #>
    param([string]$Key)
    if (-not (Test-Path -LiteralPath $Script:AlmidoQwenEnvPath -PathType Leaf)) { return $null }
    try {
        foreach ($line in Get-Content -LiteralPath $Script:AlmidoQwenEnvPath -Encoding UTF8) {
            $t = $line.Trim()
            if ($t -eq '' -or $t.StartsWith('#')) { continue }
            $idx = $t.IndexOf('=')
            if ($idx -lt 1) { continue }
            $k = $t.Substring(0, $idx).Trim()
            if ($k -eq $Key) { return $t.Substring($idx + 1).Trim() }
        }
    } catch { }
    return $null
}

function Get-AlmidoModelProviders {
    <# Returns the modelProviders.openai array from config (the SHARED CONTRACT list of
       selectable brains -- qwen-coder-dgx4:latest, gpt-oss-120b, glm-5.2 as of 2026-09-07),
       or an empty array if the config has none. #>
    param($Config)
    if ($Config -and $Config.PSObject.Properties['modelProviders'] -and
        $Config.modelProviders.PSObject.Properties['openai']) {
        return @($Config.modelProviders.openai)
    }
    return @()
}

function Get-AlmidoModelInfo {
    <#
        Looks up the modelProviders entry whose id matches $ModelId -- this is how a model
        becomes SELECTABLE: any id present in settings.json's modelProviders.openai array can
        be passed as -Model / -m without editing the file. Falls back to the top-level
        model.baseUrl when $ModelId matches $Config.model.name but no modelProviders entry
        carries that id (older configs). Returns $null when nothing resolves at all -- callers
        must treat that as "unknown door", never guess one.
    #>
    param($Config, [string]$ModelId)
    if (-not $ModelId) { return $null }
    foreach ($p in (Get-AlmidoModelProviders -Config $Config)) {
        if ($p.id -eq $ModelId) {
            return [pscustomobject]@{
                Id          = $p.id
                Name        = $p.name
                Description = $p.description
                BaseUrl     = $p.baseUrl
                EnvKey      = $(if ($p.PSObject.Properties['envKey']) { $p.envKey } else { $null })
            }
        }
    }
    if ($Config -and $Config.PSObject.Properties['model'] -and $Config.model.name -eq $ModelId -and
        $Config.model.PSObject.Properties['baseUrl']) {
        return [pscustomobject]@{ Id = $ModelId; Name = $ModelId; Description = $null; BaseUrl = $Config.model.baseUrl; EnvKey = $null }
    }
    return $null
}

function Get-AlmidoDoorUrls {
    <#
        Resolves the /models health-check URL and the /chat/completions cache-warm URL for
        whichever model is ACTUALLY about to be used. Wiring the big models in on 2026-09-07
        found the old code always health-checked the hardcoded eran4 qwen3-coder-next door
        (:8450) no matter which model.name/-Model was actually selected -- so choosing e.g.
        glm-5.2 (a completely different box/port, eran4:8800) would still gate on :8450's
        health, which proves nothing about the door the session will really use. This resolves
        the real door from modelProviders instead. Falls back to the historical hardcoded
        eran4 :8450 door only when the selected model id cannot be found in config at all
        (e.g. a typo'd -Model), so there is still SOME real check rather than none, and
        Resolved=$false tells the caller to say so out loud.
    #>
    param($Config, [string]$ModelId)
    $info = Get-AlmidoModelInfo -Config $Config -ModelId $ModelId
    if ($info -and $info.BaseUrl) {
        $base = $info.BaseUrl.TrimEnd('/')
        $apiKey = if ($info.EnvKey) { Get-AlmidoEnvValue -Key $info.EnvKey } else { $null }
        return [pscustomobject]@{
            ModelsUrl = "$base/models"
            ChatUrl   = "$base/chat/completions"
            Resolved  = $true
            BaseUrl   = $info.BaseUrl
            Warning   = $info.Description
            Label     = $(if ($info.Name) { $info.Name } else { $ModelId })
            EnvKey    = $info.EnvKey
            ApiKey    = $apiKey
        }
    }
    return [pscustomobject]@{
        ModelsUrl = $Script:AlmidoDoorModelsUrl
        ChatUrl   = $Script:AlmidoDoorChatUrl
        Resolved  = $false
        BaseUrl   = $null
        Warning   = $null
        Label     = $ModelId
        EnvKey    = $null
        ApiKey    = $null
    }
}

function Get-AlmidoAllowedMcp {
    <#
        Builds the --allowed-mcp-server-names list for THIS run:
          - the three SHARED CONTRACT doors, always
          - plus any mcpServers entry in settings.json whose name looks like a
            policy gate (gate|policy|harness), picked up automatically so a
            future gate registration needs no launcher edit.
        Returns @{ Names = [string[]]; GateFound = [bool]; GateNames = [string[]] }
    #>
    param($Config)
    $names = [System.Collections.Generic.List[string]]::new()
    foreach ($n in $Script:AlmidoBaseAllowedMcp) { [void]$names.Add($n) }
    $gateNames = [System.Collections.Generic.List[string]]::new()
    if ($Config -and $Config.PSObject.Properties['mcpServers']) {
        foreach ($prop in $Config.mcpServers.PSObject.Properties) {
            if ($prop.Name -match '(?i)gate|policy|harness') {
                if (-not $names.Contains($prop.Name)) { [void]$names.Add($prop.Name) }
                [void]$gateNames.Add($prop.Name)
            }
        }
    }
    return [pscustomobject]@{
        Names     = $names.ToArray()
        GateFound = ($gateNames.Count -gt 0)
        GateNames = $gateNames.ToArray()
    }
}

function Test-AlmidoBrainDoorUp {
    <# GET .../v1/models on the door for the model actually about to run (pass -Url from
       Get-AlmidoDoorUrls -- defaults to the historical hardcoded eran4 :8450 door only for
       backward compatibility with callers that have not been updated). 10s default timeout.
       Returns $true/$false -- never assumed, always checked fresh. #>
    param([int]$TimeoutSec = 10, [string]$Url = $Script:AlmidoDoorModelsUrl, [string]$ApiKey = $null)
    try {
        if ($ApiKey) {
            $null = Invoke-RestMethod -Uri $Url -TimeoutSec $TimeoutSec -Method Get -Headers @{ Authorization = "Bearer $ApiKey" }
        } else {
            $null = Invoke-RestMethod -Uri $Url -TimeoutSec $TimeoutSec -Method Get
        }
        return $true
    } catch {
        return $false
    }
}

function Test-AlmidoEran4SlotFree {
    <#
        Heuristic read of the RAMCHAT convention ("CLAIM eran4-slot <who>" /
        "RELEASE eran4-slot <who>") -- there is no atomic named-resource lock
        for the shared eran4 inference slot, only this posted-transcript
        convention. If the most recent eran4-slot line is a CLAIM with no
        later RELEASE, the slot is treated as busy. If RAMCHAT itself cannot
        be read, this returns $true (never BLOCK the whole launch on a
        best-effort courtesy check) but callers should say so out loud.
        Returns @{ Free = [bool]; Reason = [string] }
    #>
    param([int]$TailLines = 80)
    try {
        $python = (Get-Command python -ErrorAction SilentlyContinue)?.Source
        if (-not $python) { $python = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source }
        if (-not $python) {
            return [pscustomobject]@{ Free = $true; Reason = 'python not found on PATH - courtesy check skipped' }
        }
        $env:PYTHONIOENCODING = 'utf-8'
        # @(...) on BOTH collections is load-bearing, not defensive noise. This file sets
        # `Set-StrictMode -Version Latest` (top of file), under which reading .Count off a
        # scalar raises "The property 'Count' cannot be found on this object." A native
        # command's output and a Where-Object result are auto-unwrapped to a bare [string]
        # whenever they yield exactly ONE item, so `$slotLines.Count` threw on every tail
        # holding exactly one 'eran4-slot' line -- caught by this function's own catch and
        # turned into the fail-open default, i.e. a live unreleased CLAIM read back as FREE.
        # Zero matches short-circuited and two-plus gave a real array, so it looked
        # intermittent; it was really "did RAMCHAT traffic leave one slot line in the tail or
        # two". Observed live 2026-09-07 22:50 at the default -TailLines 80, still reproducing
        # 2026-09-08 00:0x at tails 10-13. @(...) also keeps [-1] an array index: on a bare
        # [string] it would have returned the last CHARACTER, not the last line.
        $out = @(& $python $Script:AlmidoRamlinkPy read --tail $TailLines 2>$null)
        if ($out.Count -eq 0 -or ($out -join '').Trim() -eq '') {
            return [pscustomobject]@{ Free = $true; Reason = 'RAMCHAT unreadable - courtesy check skipped' }
        }
        $slotLines = @($out | Where-Object { $_ -match 'eran4-slot' })
        if ($slotLines.Count -eq 0) {
            return [pscustomobject]@{ Free = $true; Reason = 'no eran4-slot claims in the visible tail' }
        }
        $last = [string]$slotLines[-1]
        # Match the literal convention ("CLAIM eran4-slot <who>" / "RELEASE eran4-slot <who>"),
        # not a bare substring "release" -- a claim message that itself mentions "no release
        # seen" would otherwise false-negative (observed live 2026-09-06).
        if ($last -match '(?i)\bCLAIM\s+eran4-slot\b' -and $last -notmatch '(?i)\bRELEASE\s+eran4-slot\b') {
            return [pscustomobject]@{ Free = $false; Reason = "last line: $last" }
        }
        return [pscustomobject]@{ Free = $true; Reason = "last line: $last" }
    } catch {
        return [pscustomobject]@{ Free = $true; Reason = "RAMCHAT check failed ($($_.Exception.Message)) - courtesy check skipped" }
    }
}

function Start-AlmidoCacheWarm {
    <# Fires a 1-token completion at the door in a background job, fire-and-forget.
       Never blocks the caller. Uses whatever model id the config names right now.
       -ChatUrl / -ApiKey let the caller point this at the door the SELECTED model actually
       lives behind (see Get-AlmidoDoorUrls) -- warming the wrong door's cache is worse than
       not warming anything, since it wastes the fire-and-forget request on a model nobody
       is about to talk to. Skipped entirely (returns $null) for a model whose measured speed
       makes a throwaway 1-token warm-up pointless (e.g. Colibri glm-5.2 at 0.6 tok/s still
       costs a full request round trip) -- caller decides that by simply not calling this for
       such a model. #>
    param([string]$ModelId, [string]$ChatUrl = $Script:AlmidoDoorChatUrl, [string]$ApiKey = $null)
    if (-not $ModelId) { return $null }
    return Start-Job -Name 'almido-cache-warm' -ScriptBlock {
        param($Url, $Model, $Key)
        $body = @{ model = $Model; messages = @(@{ role = 'user'; content = 'hi' }); max_tokens = 1; stream = $false } | ConvertTo-Json -Compress
        try {
            if ($Key) {
                Invoke-RestMethod -Uri $Url -Method Post -TimeoutSec 300 -ContentType 'application/json' -Body $body -Headers @{ Authorization = "Bearer $Key" } | Out-Null
            } else {
                Invoke-RestMethod -Uri $Url -Method Post -TimeoutSec 300 -ContentType 'application/json' -Body $body | Out-Null
            }
        } catch { }
    } -ArgumentList $ChatUrl, $ModelId, $ApiKey
}

function ConvertTo-AlmidoArgumentString {
    <#
        Joins an argument array into one Win32 command-line string using the
        standard CommandLineToArgvW quoting rules. Used instead of
        ProcessStartInfo.ArgumentList (.NET Core only -- absent on .NET
        Framework's Windows PowerShell 5.1) so this launcher does not
        silently break if it is ever run under `powershell.exe` instead of
        the intended `pwsh.exe`.
    #>
    param([string[]]$Arguments)
    $parts = foreach ($arg in $Arguments) {
        if ($arg -eq '') {
            '""'
        } elseif ($arg -notmatch '[\s"]') {
            $arg
        } else {
            # Double embedded quotes, then wrap the whole token in quotes.
            $escaped = $arg -replace '"', '""'
            '"' + $escaped + '"'
        }
    }
    return ($parts -join ' ')
}

function Set-AlmidoChildEnvironment {
    <#
        Returns a hashtable copy of the CURRENT process environment with every
        OPENAI_* key removed. Defect #8 (old launcher) set OPENAI_BASE_URL /
        OPENAI_API_KEY / OPENAI_MODEL; the model is now declared INSIDE
        settings.json's modelProviders (SHARED CONTRACT) so those env vars
        must never leak in from a stale shell and silently override it.
    #>
    $envTable = @{}
    foreach ($e in [System.Environment]::GetEnvironmentVariables().GetEnumerator()) {
        if ($e.Key -notmatch '^(?i)OPENAI_') { $envTable[$e.Key] = $e.Value }
    }
    return $envTable
}

function Test-AlmidoGateArmed {
    <#
        Does Iddo's PreToolUse policy gate ACTUALLY run? Measured, never assumed.

        WHY THIS EXISTS. Until 2026-09-11 07:09 the banner reported the gate by asking
        whether iddo-harness was registered as an MCP server -- which it never was and
        never needed to be, because the gate is a HOOK, not a door. Meanwhile the hook
        itself was dead: settings.json invoked it as
            "C:\Program Files\Python312\python.exe" -X utf8 "D:\...\almido_gate_hook.py"
        and qwen-code runs a hook command through a shell chosen from the ENVIRONMENT --
        Git Bash if MSYSTEM/TERM say so, otherwise %ComSpec% with /d /s /c. Node escapes
        the inner quotes as \" , which cmd.exe does not understand, so under cmd.exe (i.e.
        under THIS launcher) the hook died with
            '"C:\Program Files\Python312\python.exe"' is not recognized ...
        and qwen-code treats a FAILED hook as PROCEED. Silently. 8 headless runs produced
        0 audit rows while the banner said nothing was wrong.

        So this function does the only honest thing: it runs the configured hook command
        through the SAME shell qwen-code would pick, feeds it a real PreToolUse event for
        a harmless `whoami`, and requires a parseable permissionDecision back. The probe
        leaves one real row in the audit chain -- that row IS the evidence.
    #>
    param(
        $Config,
        [int]$TimeoutSec = 30
    )
    $result = [pscustomobject]@{
        Armed    = $false
        Command  = $null
        Decision = $null
        Reason   = 'not checked'
        Shell    = $null
    }
    if (-not $Config -or -not $Config.PSObject.Properties['hooks']) {
        $result.Reason = 'settings.json declares no hooks at all'
        return $result
    }
    $hooks = $Config.hooks
    if (-not $hooks.PSObject.Properties['PreToolUse']) {
        $result.Reason = 'settings.json declares no PreToolUse hook'
        return $result
    }
    $cmd = $null
    foreach ($def in @($hooks.PreToolUse)) {
        if ($def.PSObject.Properties['hooks']) {
            foreach ($h in @($def.hooks)) {
                if ($h.PSObject.Properties['command'] -and $h.command) { $cmd = [string]$h.command; break }
            }
        }
        if ($cmd) { break }
    }
    if (-not $cmd) {
        $result.Reason = 'the PreToolUse hook entry carries no command'
        return $result
    }
    $result.Command = $cmd

    # The same shell selection qwen-code's getShellConfiguration() makes, in the same
    # environment this launcher is about to hand to the child.
    $isGitBash = ($env:MSYSTEM -and ($env:MSYSTEM.StartsWith('MINGW') -or $env:MSYSTEM.StartsWith('MSYS'))) -or
                 ($env:TERM -and ($env:TERM -like '*msys*' -or $env:TERM -like '*cygwin*'))
    if ($isGitBash) {
        $exe = 'bash'; $prefix = @('-c'); $result.Shell = 'bash'
    } else {
        $comSpec = if ($env:ComSpec) { $env:ComSpec } else { 'cmd.exe' }
        $exe = $comSpec; $prefix = @('/d', '/s', '/c'); $result.Shell = 'cmd'
    }

    $event = [ordered]@{
        session_id      = 'launcher-gate-probe'
        cwd             = $Script:AlmidoWorkspace
        hook_event_name = 'PreToolUse'
        tool_name       = 'run_shell_command'
        tool_input      = @{ command = 'whoami' }
        tool_use_id     = 'launcher-probe'
        permission_mode = 'probe'
    } | ConvertTo-Json -Compress -Depth 5

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName  = $exe
    $psi.Arguments = ConvertTo-AlmidoArgumentString -Arguments (@($prefix) + @($cmd))
    $psi.WorkingDirectory = $Script:AlmidoRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    try {
        $p = [System.Diagnostics.Process]::new()
        $p.StartInfo = $psi
        [void]$p.Start()
        $p.StandardInput.Write($event)
        $p.StandardInput.Close()
        $outTask = $p.StandardOutput.ReadToEndAsync()
        if (-not $p.WaitForExit($TimeoutSec * 1000)) {
            try { $p.Kill($true) } catch { }
            $result.Reason = "the hook did not answer within ${TimeoutSec}s"
            return $result
        }
        $out = $outTask.Result
    } catch {
        $result.Reason = "could not run the hook command: $($_.Exception.Message)"
        return $result
    }

    if (-not $out -or -not $out.Trim()) {
        $result.Reason = 'the hook produced no output (a failed hook reads as PROCEED to qwen-code -- treat as NOT armed)'
        return $result
    }
    try {
        $parsed = $out | ConvertFrom-Json
    } catch {
        $result.Reason = "the hook answered something that is not JSON: $($out.Trim().Substring(0, [Math]::Min(160, $out.Trim().Length)))"
        return $result
    }
    if (-not $parsed.PSObject.Properties['hookSpecificOutput'] -or
        -not $parsed.hookSpecificOutput.PSObject.Properties['permissionDecision']) {
        $result.Reason = 'the hook answered JSON with no hookSpecificOutput.permissionDecision'
        return $result
    }
    $result.Decision = [string]$parsed.hookSpecificOutput.permissionDecision
    $result.Armed = $true
    $result.Reason = "answered '$($result.Decision)' through $($result.Shell) -- one probe row is now in the audit chain"
    return $result
}


function Write-AlmidoBanner {
    <# One shared, honest, bilingual startup banner. Every value here is read
       from config or measured live -- nothing is a promise. #>
    param(
        [string]$QwenExe,
        [string]$QwenVersion,
        [string]$ModelId,
        [string]$ApprovalMode,
        [Nullable[bool]]$ComputerUseEnabled,
        [bool]$DoorUp,
        [bool]$GateFound,
        [string[]]$GateNames,
        [string[]]$AllowedMcp,
        [pscustomobject]$SlotStatus,
        [pscustomobject]$DoorUrls = $null,
        [pscustomobject]$GateArmed = $null
    )
    Write-Host ''
    Write-Host '=== ALMIDO AGENT ===  (עלמה ז"ל + עידו)'
    Write-Host "  binary / קובץ הפעלה : $QwenExe  (v$QwenVersion)"
    Write-Host "  model / מודל        : $(if ($ModelId) { $ModelId } else { '<not set in settings.json!>' })"
    if ($DoorUrls -and $DoorUrls.Label -and $DoorUrls.Label -ne $ModelId) {
        Write-Host "                        $($DoorUrls.Label)"
    }
    Write-Host "  doors / דלתות MCP   : $($AllowedMcp -join ', ')"
    $doorTarget = if ($DoorUrls -and $DoorUrls.ModelsUrl) { $DoorUrls.ModelsUrl } else { $Script:AlmidoDoorModelsUrl }
    $doorSource = if ($DoorUrls -and -not $DoorUrls.Resolved) { " (id not found in modelProviders -- fell back to the default door, this check may not reflect the model you asked for)" } else { "" }
    if ($DoorUp) {
        Write-Host "  brain door / דלת המוח : UP - ready  [$doorTarget]$doorSource"
    } else {
        Write-Host "  brain door / דלת המוח : DOWN - did not answer in time  [$doorTarget]$doorSource"
    }
    if ($DoorUrls -and $DoorUrls.Warning) {
        $w = $DoorUrls.Warning
        if ($w.Length -gt 420) { $w = $w.Substring(0, 420) + '...' }
        Write-Host "  before you pay for it / לפני שאתה משלם על זה :"
        Write-Host "    $w"
    }
    $approvalDisplay = if ($ApprovalMode) { $ApprovalMode } else { 'NOT SET (qwen-code default: auto in interactive, default in headless -p)' }
    Write-Host "  approval mode / מצב אישור : $approvalDisplay   [read from $Script:AlmidoSettingsPath]"
    if ($ComputerUseEnabled -eq $false) {
        Write-Host '  screen hands / ידיים על המסך : disabled in config (computerUse.enabled=false)'
    } elseif ($null -eq $ComputerUseEnabled) {
        Write-Host '  screen hands / ידיים על המסך : UNKNOWN - tools.computerUse.enabled not present in settings.json'
    } else {
        Write-Host '  screen hands / ידיים על המסך : ENABLED IN CONFIG - the sacred no-type-into-windows rule is not enforced here; verify before trusting'
    }
    # THE line that matters. The MCP-registration line below it is kept only because
    # someone may still register the harness as a door one day; it never was the gate.
    if ($null -ne $GateArmed) {
        if ($GateArmed.Armed) {
            Write-Host "  policy gate / שער מדיניות : ARMED - MEASURED just now: the PreToolUse hook $($GateArmed.Reason)"
            Write-Host "                              $($GateArmed.Command)"
        } else {
            Write-Host "  policy gate / שער מדיניות : *** NOT ARMED *** $($GateArmed.Reason)"
            Write-Host '                              qwen-code treats a failed hook as PROCEED, so nothing would be gated or audited.'
        }
    } else {
        Write-Host '  policy gate / שער מדיניות : not measured in this run'
    }
    if ($GateFound) {
        Write-Host "  (iddo-harness is also registered as an MCP door: $($GateNames -join ', ') -- unrelated to the hook above)"
    }
    Write-Host "  eran4 slot / משבצת eran4 : $(if ($SlotStatus.Free) { 'appears free' } else { 'BUSY - another session holds it' })  ($($SlotStatus.Reason))"
    Write-Host ''
}
