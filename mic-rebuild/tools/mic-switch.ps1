<#
.SYNOPSIS
  KESHEV mic-switch — K5 (PHASE2-DESIGN.md section 7 "mic-switch", scar 56,
  criterion 23). The ONE-MIC coexistence protocol for the M3-M7 window.

    new    = stop alma-mic (running tasks stopped + enabled tasks disabled +
             processes killed + Startup persistence suspended, ALL journaled),
             VERIFY alma-mic is dead AND zero foreign capture handles remain,
             then start KESHEV.
    old    = exact reverse, one command.
    status = read-only liveness probes + capture-device-handle audit.

  REFUSAL (criterion 23): if at the verify step the other mic is still
  detectably alive — task Running, live process, or an ACTIVE capture
  session classified as the other mic — the switch REFUSES (exit 3) and
  starts NOTHING. Refusals are journaled.

.NOTES
  Exit codes: 0 = ok, 1 = error, 3 = refused (other mic alive at verify).

  -DryRun                 plan + probes + audit only; changes NOTHING.
  -SimulateAlmaMic / -SimulateKeshev  Alive|Dead|Auto  test hooks. Engaging
                          ANY simulation FORCES dry-run — a simulated world
                          may never mutate the real one (structural safety).

  SACRED AUDIO: the capture audit ENUMERATES WASAPI sessions on eCapture
  endpoints only — metadata via IAudioSessionManager2; it never opens,
  activates, or touches any audio stream and never looks at output devices.

  Machine-readable result: one line "SUMMARY:{json}" on stdout — always,
  including on refusal.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("new", "old", "status")][string]$Action,
    [switch]$DryRun,
    [ValidateSet("Auto", "Alive", "Dead")][string]$SimulateAlmaMic = "Auto",
    [ValidateSet("Auto", "Alive", "Dead")][string]$SimulateKeshev = "Auto",
    # $PSScriptRoot, NOT $MyInvocation.MyCommand.Path: inside a param default
    # under Windows PowerShell 5.1 $MyInvocation.MyCommand.Path is $null, which
    # made the default RepoRoot explode before the script even started (wave-2 debt).
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$JournalRoot = "",
    [string]$KeshevTaskName = "KESHEV"
)

$ErrorActionPreference = "Stop"
if (-not $JournalRoot) { $JournalRoot = Join-Path $RepoRoot "_genizah" }

# A simulated world may never mutate the real one (asserted by K5 tests).
$Simulated = ($SimulateAlmaMic -ne "Auto") -or ($SimulateKeshev -ne "Auto")
if ($Simulated -and -not $DryRun) {
    Write-Output "NOTE: simulation engaged - forcing -DryRun (a simulated world never mutates the real one)"
    $DryRun = $true
}

$stamp = Get-Date -Format "yyyyMMdd"
$archiveDir = Join-Path $JournalRoot "mic-switch-$stamp"
$journalPath = Join-Path $archiveDir "journal.jsonl"

function Write-Journal([hashtable]$entry) {
    if (-not (Test-Path $archiveDir)) { New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null }
    $entry["ts"] = (Get-Date -Format "o")
    Add-Content -Path $journalPath -Value (ConvertTo-Json $entry -Compress -Depth 6) -Encoding UTF8
}

# ---------------------------------------------------------------- READ-ONLY liveness probes
$AlmaTaskPattern   = "ALMA-MIC*"
$AlmaProcPattern   = "alma-mic|voice-input|heb-mic"
$KeshevProcPattern = 'mic-rebuild[\\/]client[\\/]app\.py|keshev_worker'
$StartupRivalPatterns = @("ALMA-MIC*", "START-MIC*", "*voice-input*", "*heb-mic*", "*alma-mic*")

function Test-AlmaMicAlive {
    if ($SimulateAlmaMic -eq "Alive") { return $true }
    if ($SimulateAlmaMic -eq "Dead")  { return $false }
    try {
        $t = Get-ScheduledTask -TaskName $AlmaTaskPattern -ErrorAction SilentlyContinue |
             Where-Object { $_.State -eq "Running" }
        if ($t) { return $true }
    } catch { Write-Verbose "alma task probe failed: $_" }
    try {
        $p = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
             Where-Object { $_.CommandLine -match $AlmaProcPattern }
        if ($p) { return $true }
    } catch { Write-Verbose "alma process probe failed: $_" }
    return $false
}

function Test-KeshevAlive {
    if ($SimulateKeshev -eq "Alive") { return $true }
    if ($SimulateKeshev -eq "Dead")  { return $false }
    try {
        $t = Get-ScheduledTask -TaskName $KeshevTaskName -ErrorAction SilentlyContinue |
             Where-Object { $_.State -eq "Running" }
        if ($t) { return $true }
    } catch { Write-Verbose "keshev task probe failed: $_" }
    try {
        $p = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
             Where-Object { $_.CommandLine -match $KeshevProcPattern }
        if ($p) { return $true }
    } catch { Write-Verbose "keshev process probe failed: $_" }
    return $false
}

# ---------------------------------------------------------------- capture-handle audit (criterion 23)
# WASAPI session ENUMERATION on eCapture endpoints only. Metadata only:
# never opens a stream, never activates an IAudioClient, never enumerates
# render/output endpoints (Sacred Audio, scar 22).
$AuditCSharp = @'
using System;
using System.Runtime.InteropServices;

namespace KeshevSwitch
{
    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    public class MMDeviceEnumeratorComObject { }

    [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDeviceEnumerator
    {
        [PreserveSig] int EnumAudioEndpoints(int dataFlow, int stateMask, out IMMDeviceCollection devices);
    }

    [ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDeviceCollection
    {
        [PreserveSig] int GetCount(out int count);
        [PreserveSig] int Item(int index, out IMMDevice device);
    }

    [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDevice
    {
        [PreserveSig] int Activate(ref Guid iid, int clsCtx, IntPtr activationParams,
                                   [MarshalAs(UnmanagedType.IUnknown)] out object iface);
        [PreserveSig] int OpenPropertyStore(int access, out IPropertyStore props);
        [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
        [PreserveSig] int GetState(out int state);
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PropertyKey { public Guid fmtid; public int pid; }

    [StructLayout(LayoutKind.Explicit)]
    public struct PropVariant
    {
        [FieldOffset(0)] public ushort vt;
        [FieldOffset(8)] public IntPtr pointerValue;
    }

    [ComImport, Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPropertyStore
    {
        [PreserveSig] int GetCount(out int count);
        [PreserveSig] int GetAt(int iProp, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out PropVariant value);
    }

    [ComImport, Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IAudioSessionManager2
    {
        [PreserveSig] int GetAudioSessionControl(IntPtr sessionId, int flags, out IntPtr sessionControl);
        [PreserveSig] int GetSimpleAudioVolume(IntPtr sessionId, int streamFlags, out IntPtr audioVolume);
        [PreserveSig] int GetSessionEnumerator(out IAudioSessionEnumerator enumerator);
    }

    [ComImport, Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IAudioSessionEnumerator
    {
        [PreserveSig] int GetCount(out int count);
        [PreserveSig] int GetSession(int index, out IAudioSessionControl2 session);
    }

    [ComImport, Guid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IAudioSessionControl2
    {
        // IAudioSessionControl (vtable order preserved)
        [PreserveSig] int GetState(out int state);
        [PreserveSig] int GetDisplayName([MarshalAs(UnmanagedType.LPWStr)] out string name);
        [PreserveSig] int SetDisplayName([MarshalAs(UnmanagedType.LPWStr)] string value, ref Guid eventContext);
        [PreserveSig] int GetIconPath([MarshalAs(UnmanagedType.LPWStr)] out string path);
        [PreserveSig] int SetIconPath([MarshalAs(UnmanagedType.LPWStr)] string value, ref Guid eventContext);
        [PreserveSig] int GetGroupingParam(out Guid param);
        [PreserveSig] int SetGroupingParam(ref Guid param, ref Guid eventContext);
        [PreserveSig] int RegisterAudioSessionNotification(IntPtr client);
        [PreserveSig] int UnregisterAudioSessionNotification(IntPtr client);
        // IAudioSessionControl2
        [PreserveSig] int GetSessionIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string id);
        [PreserveSig] int GetSessionInstanceIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string id);
        [PreserveSig] int GetProcessId(out int pid);
        [PreserveSig] int IsSystemSoundsSession();
    }

    public static class CaptureAudit
    {
        static readonly Guid IID_IAudioSessionManager2 = new Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F");

        // AUDCLNT_S_NO_SINGLE_PROCESS — a SUCCESS hresult (facility bit clear) meaning
        // "this session spans more than one process". Treating it as an error was the
        // K5 audit bug: the shared session every capture endpoint carries — the one a
        // DirectSound/MME recorder like the live alma-mic actually streams into — came
        // back as pid=-1 by accident instead of "owner unattributable" on purpose.
        const int AUDCLNT_S_NO_SINGLE_PROCESS = 0x0889000D;

        // rows of "deviceName<TAB>pid<TAB>state<TAB>multi"
        //   state: 0 inactive, 1 active, 2 expired, -1 unreadable
        //   multi: 1 when the session spans several processes (owner unattributable)
        public static string[] Enumerate()
        {
            var results = new System.Collections.Generic.List<string>();
            var deviceEnum = (IMMDeviceEnumerator)(object)new MMDeviceEnumeratorComObject();
            IMMDeviceCollection devices;
            int hr = deviceEnum.EnumAudioEndpoints(1 /*eCapture ONLY*/, 1 /*DEVICE_STATE_ACTIVE*/, out devices);
            if (hr != 0) throw new COMException("EnumAudioEndpoints(eCapture)", hr);
            int count; devices.GetCount(out count);
            for (int i = 0; i < count; i++)
            {
                IMMDevice device;
                if (devices.Item(i, out device) != 0) continue;
                string name = DeviceName(device);
                object mgrObj; Guid iid = IID_IAudioSessionManager2;
                if (device.Activate(ref iid, 23 /*CLSCTX_ALL*/, IntPtr.Zero, out mgrObj) != 0) continue;
                var mgr = (IAudioSessionManager2)mgrObj;
                IAudioSessionEnumerator sessions;
                if (mgr.GetSessionEnumerator(out sessions) != 0) continue;
                int n; sessions.GetCount(out n);
                for (int j = 0; j < n; j++)
                {
                    IAudioSessionControl2 s;
                    if (sessions.GetSession(j, out s) != 0) continue;
                    // hr < 0 is the only real failure; positive hresults are successes.
                    int state; if (s.GetState(out state) < 0) state = -1;
                    int procId; int phr = s.GetProcessId(out procId);
                    if (phr < 0) procId = -1;
                    bool multi = (phr == AUDCLNT_S_NO_SINGLE_PROCESS) || (phr < 0);
                    results.Add(name + "\t" + procId + "\t" + state + "\t" + (multi ? "1" : "0"));
                }
            }
            return results.ToArray();
        }

        static string DeviceName(IMMDevice device)
        {
            try
            {
                IPropertyStore store;
                if (device.OpenPropertyStore(0 /*STGM_READ*/, out store) != 0) return DeviceId(device);
                var key = new PropertyKey {
                    fmtid = new Guid("A45C254E-DF1C-4EFD-8020-67D146A850E0"), pid = 14 }; // FriendlyName
                PropVariant v;
                if (store.GetValue(ref key, out v) != 0) return DeviceId(device);
                if (v.vt == 31 && v.pointerValue != IntPtr.Zero)
                    return Marshal.PtrToStringUni(v.pointerValue);
                return DeviceId(device);
            }
            catch { return DeviceId(device); }
        }

        static string DeviceId(IMMDevice d)
        {
            string id;
            return d.GetId(out id) == 0 ? id : "unknown-device";
        }
    }
}
'@

function Get-CaptureAudit {
    # can_prove_free starts FALSE and is only ever earned: an audit that throws,
    # or that cannot account for every session it enumerated, leaves it false.
    $result = @{ ok = $false; error = ""; sessions = @(); mic_holders = @()
                 unattributable = @(); can_prove_free = $false }
    try {
        if (-not ("KeshevSwitch.CaptureAudit" -as [type])) {
            Add-Type -TypeDefinition $AuditCSharp -ErrorAction Stop | Out-Null
        }
        $rows = [KeshevSwitch.CaptureAudit]::Enumerate()
        $procs = @{}
        foreach ($p in (Get-CimInstance Win32_Process)) { $procs[[int]$p.ProcessId] = $p }
        $stateNames = @{ 0 = "inactive"; 1 = "active"; 2 = "expired"; -1 = "unknown" }
        foreach ($row in $rows) {
            $parts = $row -split "`t"
            $procId = [int]$parts[1]
            $multi = ($parts.Count -ge 4 -and $parts[3] -eq "1")
            # A multi-process session's pid is an "initial" id, not an owner (it comes
            # back as 0 here). Resolving it against Win32_Process would name the System
            # Idle Process as the mic holder — an invented answer, which is the one
            # thing this audit must never produce.
            $proc = if ($multi) { $null } else { $procs[$procId] }
            $exe = if ($proc) { $proc.Name } elseif ($multi) { "unattributable-shared-session" } else { "pid-$procId" }
            $cmd = if ($proc) { "$($proc.CommandLine)$($proc.ExecutablePath)" } else { "" }
            $stateVal = [int]$parts[2]
            $state = if ($stateNames.ContainsKey($stateVal)) { $stateNames[$stateVal] } else { "unknown" }
            # THE AUDIT MUST NOT LIE (criterion 23). Two things defeat identification
            # here, and BOTH are the live alma-mic:
            #   * it streams the BRIO through Windows DirectSound, so it owns no
            #     per-process session — it lives inside the endpoint's shared session,
            #     which reports itself as spanning several processes ($multi);
            #   * it runs ELEVATED, so Win32_Process gives a non-elevated probe a blank
            #     CommandLine/ExecutablePath.
            # Either way the owner is "unknown" — and unknown is recorded as such, never
            # quietly rounded down to "other" and dropped.
            $class = "other"
            if ("$exe $cmd" -match $AlmaProcPattern -or "$exe $cmd" -match "START-MIC") { $class = "alma-mic" }
            elseif ("$exe $cmd" -match $KeshevProcPattern) { $class = "keshev" }
            elseif ($multi -or $cmd -eq "") { $class = "unknown" }
            $sess = @{ device = $parts[0]; pid = $procId; exe = $exe; class = $class
                       state = $state; multi_process = $multi }
            $result.sessions += $sess
            # "Could not tell" is its own answer, and it is NOT "free": an unidentified
            # owner, or a state we could not read, cannot be proven not to be the other mic.
            #
            # REVERTED 2026-08-14, and the attempt is recorded because it is instructive.
            # Claude narrowed this to ignore sessions reporting state=inactive, so that
            # `new` would stop refusing (every endpoint here permanently carries an
            # inactive pid=0 shared session, which made can_prove_free unreachable).
            # The justification was "a rival that is actually capturing would report
            # active" — and that was NEVER MEASURED. It was an inference made to unblock
            # a gate that was in the way. But the whole reason this audit exists is that
            # alma-mic is invisible BY CONSTRUCTION (DirectSound -> no per-process
            # session, elevated -> blank CommandLine); reasoning about what an invisible
            # process would report is exactly the proxy this project forbids
            # (`health: ok` is not `working`). tests/test_mic_switch.py caught it.
            # If the permanent-inactive-session problem is to be solved, it must be
            # solved by MEASURING what a live DirectSound capture reports here, or by an
            # explicit journalled operator override — never by quietly widening what the
            # audit is willing to call free.
            if ($class -eq "unknown" -or $state -eq "unknown") { $result.unattributable += $sess }
            if ($class -ne "other" -and $state -eq "active") { $result.mic_holders += $sess }
        }
        $result.ok = $true
        $result.can_prove_free = (@($result.unattributable).Count -eq 0) -and
                                 (@($result.mic_holders).Count -eq 0)
    } catch { $result.error = "$_" }
    $result
}

# ---------------------------------------------------------------- actuators (journaled; DryRun => WOULD-*)
# NEVER invoked in the K5 wave: every K5 test path is -DryRun and/or simulated.
# First real execution happens at the K8+ live-test gate, with Iddo.

$steps = [System.Collections.Generic.List[hashtable]]::new()
function Add-Step([string]$step, [string]$action) {
    $steps.Add(@{ step = $step; action = $action })
    Write-Journal @{ kind = "step"; step = $step; action = $action }
}

function Stop-AlmaMicSide {
    if (-not (Test-AlmaMicAlive) -and $SimulateAlmaMic -eq "Auto") {
        Add-Step "stop-alma-mic" "SKIP-ALREADY-DEAD"; return
    }
    if ($DryRun) { Add-Step "stop-alma-mic" "WOULD-STOP"; return }
    # 1. running tasks stopped; enabled tasks disabled (XML exported first)
    foreach ($t in @(Get-ScheduledTask -TaskName $AlmaTaskPattern -ErrorAction SilentlyContinue)) {
        if ($t.State -eq "Running") { Stop-ScheduledTask -TaskName $t.TaskName }
        if ($t.State -ne "Disabled") {
            Export-ScheduledTask -TaskName $t.TaskName |
                Set-Content -Path (Join-Path $archiveDir "task-$($t.TaskName).xml") -Encoding UTF8
            Disable-ScheduledTask -TaskName $t.TaskName | Out-Null
            Write-Journal @{ kind = "suspend"; target = "alma-mic"; item = "task"; name = $t.TaskName }
        }
    }
    # 2. live processes killed (tree)
    $procs = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
             Where-Object { $_.CommandLine -match $AlmaProcPattern }
    foreach ($p in @($procs)) {
        Write-Journal @{ kind = "kill"; target = "alma-mic"; pid = [int]$p.ProcessId }
        & taskkill /pid $p.ProcessId /t /f | Out-Null
    }
    # 3. Startup persistence suspended (moved to the archive, journaled)
    foreach ($dir in @([Environment]::GetFolderPath("Startup"), [Environment]::GetFolderPath("CommonStartup"))) {
        if (-not (Test-Path $dir)) { continue }
        foreach ($pat in $StartupRivalPatterns) {
            foreach ($f in @(Get-ChildItem -Path $dir -Filter $pat -File -ErrorAction SilentlyContinue)) {
                Move-Item -Path $f.FullName -Destination (Join-Path $archiveDir $f.Name) -Force
                Write-Journal @{ kind = "suspend"; target = "alma-mic"; item = "startup"
                                 name = $f.Name; original_path = $f.FullName }
            }
        }
    }
    Add-Step "stop-alma-mic" "STOPPED"
}

function Start-AlmaMicSide {
    if ($DryRun) { Add-Step "start-alma-mic" "WOULD-START"; return }
    # reverse the newest journal's suspensions: restore startup files, re-enable tasks
    if (Test-Path $journalPath) {
        $entries = Get-Content $journalPath | ForEach-Object { $_ | ConvertFrom-Json }
        foreach ($e in $entries) {
            if ($e.kind -ne "suspend" -or $e.target -ne "alma-mic") { continue }
            if ($e.item -eq "startup" -and (Test-Path (Join-Path $archiveDir $e.name))) {
                Move-Item -Path (Join-Path $archiveDir $e.name) -Destination $e.original_path -Force
                Write-Journal @{ kind = "restore"; item = "startup"; name = $e.name }
            }
            if ($e.item -eq "task") {
                Enable-ScheduledTask -TaskName $e.name -ErrorAction SilentlyContinue | Out-Null
                Write-Journal @{ kind = "restore"; item = "task"; name = $e.name }
            }
        }
    } else {
        # no journal from a prior `new` — enable the known task directly
        Enable-ScheduledTask -TaskName "ALMA-MIC-Elevated" -ErrorAction SilentlyContinue | Out-Null
    }
    Start-ScheduledTask -TaskName "ALMA-MIC-Elevated"
    Add-Step "start-alma-mic" "STARTED"
}

function Stop-KeshevSide {
    if (-not (Test-KeshevAlive) -and $SimulateKeshev -eq "Auto") {
        Add-Step "stop-keshev" "SKIP-ALREADY-DEAD"; return
    }
    if ($DryRun) { Add-Step "stop-keshev" "WOULD-STOP"; return }
    $t = Get-ScheduledTask -TaskName $KeshevTaskName -ErrorAction SilentlyContinue
    if ($t -and $t.State -eq "Running") { Stop-ScheduledTask -TaskName $KeshevTaskName }
    if ($t -and $t.State -ne "Disabled") {
        Disable-ScheduledTask -TaskName $KeshevTaskName | Out-Null
        Write-Journal @{ kind = "suspend"; target = "keshev"; item = "task"; name = $KeshevTaskName }
    }
    $procs = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
             Where-Object { $_.CommandLine -match $KeshevProcPattern }
    foreach ($p in @($procs)) {
        Write-Journal @{ kind = "kill"; target = "keshev"; pid = [int]$p.ProcessId }
        & taskkill /pid $p.ProcessId /t /f | Out-Null
    }
    Add-Step "stop-keshev" "STOPPED"
}

function Start-KeshevSide {
    if ($DryRun) { Add-Step "start-keshev" "WOULD-START"; return }
    $t = Get-ScheduledTask -TaskName $KeshevTaskName -ErrorAction SilentlyContinue
    if (-not $t) { throw "KESHEV task '$KeshevTaskName' is not installed (run install_client.ps1 first)" }
    Enable-ScheduledTask -TaskName $KeshevTaskName -ErrorAction SilentlyContinue | Out-Null
    Start-ScheduledTask -TaskName $KeshevTaskName
    Add-Step "start-keshev" "STARTED"
}

# ---------------------------------------------------------------- verify (the criterion-23 refusal)
function Test-VerifyDead([string]$who, [hashtable]$audit) {
    # returns $null when verifiably dead, else a human refusal reason
    $probeAlive = if ($who -eq "alma-mic") { Test-AlmaMicAlive } else { Test-KeshevAlive }
    if ($probeAlive) { return "$who is still ALIVE (task/process probe)" }
    if (-not $Simulated) {
        if (-not $audit.ok) {
            return "capture audit unavailable ($($audit.error)) - refusing to switch blind (fail closed)"
        }
        # "unknown" holders block BOTH directions: if the owner of an active capture
        # session cannot be identified, it cannot be proven NOT to be the other mic.
        $foreign = @($audit.mic_holders | Where-Object { $_.class -eq $who -or $_.class -eq "unknown" })
        if ($foreign.Count -gt 0) {
            $held = ($foreign | ForEach-Object { "$($_.exe) pid=$($_.pid) class=$($_.class) on '$($_.device)'" }) -join "; "
            return "ACTIVE capture session attributable to $who (or unidentifiable): $held"
        }
        # The audit's verdict must reach the DECISION, not just the report. Silence
        # from a probe that cannot see is not evidence of an empty microphone.
        if (-not $audit.can_prove_free) {
            $blind = (@($audit.unattributable) | ForEach-Object {
                "$($_.exe) pid=$($_.pid) state=$($_.state) on '$($_.device)'" }) -join "; "
            return "capture audit cannot PROVE the mic is free - unattributable session(s): $blind (fail closed)"
        }
    }
    return $null
}

function Emit-Summary([hashtable]$s) {
    Write-Output ("SUMMARY:" + (ConvertTo-Json $s -Compress -Depth 8))
}

# ================================================================ main
try {
    Write-Journal @{ kind = "run"; action = $Action; dry_run = [bool]$DryRun
                     simulated = $Simulated; sim_alma = $SimulateAlmaMic; sim_keshev = $SimulateKeshev }

    $audit = Get-CaptureAudit
    $almaAlive = Test-AlmaMicAlive
    $keshevAlive = Test-KeshevAlive

    $base = @{ action = $Action; dry_run = [bool]$DryRun; simulated = $Simulated
               alma_mic_alive = $almaAlive; keshev_alive = $keshevAlive
               audit = $audit; journal = $journalPath; refused = $false; refusal_reason = "" }

    if ($Action -eq "status") {
        $micApps = @($audit.mic_holders).Count
        $blindCount = @($audit.unattributable).Count
        Write-Output "mic-switch status: alma-mic alive=$almaAlive keshev alive=$keshevAlive mic-apps-holding-capture=$micApps audit-ok=$($audit.ok) unattributable=$blindCount mic-provably-free=$($audit.can_prove_free)"
        $base.steps = @()
        Emit-Summary $base
        exit 0
    }

    # -------- the switch (new: alma-mic -> KESHEV | old: KESHEV -> alma-mic)
    $stopSide  = if ($Action -eq "new") { "alma-mic" } else { "keshev" }
    $verifyStep = "verify-$stopSide-dead"

    if ($Action -eq "new") { Stop-AlmaMicSide } else { Stop-KeshevSide }

    # non-dry-run: give killed processes a moment, then re-audit before verify
    if (-not $DryRun) {
        $deadline = (Get-Date).AddSeconds(10)
        do {
            Start-Sleep -Milliseconds 500
            $audit = Get-CaptureAudit
            $reason = Test-VerifyDead $stopSide $audit
        } while ($reason -and (Get-Date) -lt $deadline)
    } else {
        $reason = Test-VerifyDead $stopSide $audit
    }

    if ($reason) {
        Add-Step $verifyStep "FAIL"
        Write-Journal @{ kind = "refusal"; action = $Action; reason = $reason }
        Write-Output "REFUSED: $reason"
        Write-Output "  Nothing was started (criterion 23 / scar 56). Fix the other mic first."
        $base.refused = $true; $base.refusal_reason = $reason
        $base.audit = $audit; $base.steps = @($steps)
        Emit-Summary $base
        exit 3
    }
    Add-Step $verifyStep "PASS"

    if ($Action -eq "new") { Start-KeshevSide } else { Start-AlmaMicSide }

    if (-not $DryRun) { $audit = Get-CaptureAudit }
    $base.audit = $audit; $base.steps = @($steps)
    $base.alma_mic_alive = Test-AlmaMicAlive
    $base.keshev_alive = Test-KeshevAlive
    $doneWord = if ($DryRun) { "PLANNED (dry-run - nothing executed)" } else { "DONE" }
    Write-Output "mic-switch ${Action}: $doneWord"
    Emit-Summary $base
    exit 0
} catch {
    Write-Error "mic-switch FAILED: $_"
    exit 1
}
