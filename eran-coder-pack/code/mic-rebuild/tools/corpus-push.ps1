<#
    KESHEV corpus push — the PC half of "make the mic always train".

    Every night at 03:00 this moves the day's captured utterances (audio +
    the text that was actually accepted into Iddo's window) to eran4, where
    keshev-lora.timer picks them up at 03:30, trains a LoRA on them, and
    promotes it ONLY if it beats the deployed model on the reserved eval.

    WHAT IT MOVES: state/corpus/ — written by client/corpus.py, and only from
    utterances that were TYPED, meaning they already passed the USB-mic law,
    the energy gate, VAD, the hallucination guard, the language guard, the
    PRESENCE guard and the focus guard. Room audio is never typed, so room
    audio can never be trained on.

    IT NEVER DELETES. Pushed files are MOVED into state/corpus-sent/<date>/
    on this machine, not removed — his voice is not something a scheduled
    task gets to erase at 3am. Pruning that archive is a human decision.

    Privacy: his audio goes to his own fleet and nowhere else. No cloud, no
    third party, no telemetry. One command wipes it: Remove-Item on
    state/corpus and state/corpus-sent.
#>
param([switch]$Install, [switch]$Uninstall, [switch]$Once)

$ErrorActionPreference = 'Stop'
$ROOT     = Split-Path -Parent $PSScriptRoot
$CORPUS   = Join-Path $ROOT 'state\corpus'
$SENT     = Join-Path $ROOT 'state\corpus-sent'
$LOG      = Join-Path $ROOT 'state\corpus-push.log'
$TASKNAME = 'KESHEV-Corpus-Push'
$REMOTE   = 'eran4@<lan-ip>'
$REMDIR   = 'lora-iddo/data/keshev_corpus'

function Write-Log([string]$level, [string]$msg) {
    $line = "{0} [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $level, $msg
    Add-Content -Path $LOG -Value $line -Encoding UTF8
    Write-Output $line
}

if ($Install) {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -Once' -f $PSCommandPath)
    $trigger  = New-ScheduledTaskTrigger -Daily -At 3:00am
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 25) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $TASKNAME -Action $action -Trigger $trigger `
        -Settings $settings -Force `
        -Description 'Pushes the day of KESHEV voice corpus to eran4 for the nightly LoRA. Never deletes: sent files are archived locally.' | Out-Null
    Write-Log 'INFO' "installed scheduled task '$TASKNAME' (daily 03:00)"
    return
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TASKNAME -Confirm:$false -ErrorAction SilentlyContinue
    Write-Log 'INFO' "removed scheduled task '$TASKNAME'"
    return
}

# ------------------------------------------------------------------ push --

if (-not (Test-Path $CORPUS)) {
    Write-Log 'OK' 'no corpus directory yet — nothing to push'
    return
}
$wavs = @(Get-ChildItem $CORPUS -Recurse -Filter *.wav -ErrorAction SilentlyContinue)
if ($wavs.Count -eq 0) {
    Write-Log 'OK' 'corpus is empty — nothing to push (healthy, not a failure)'
    return
}

$manifest = Join-Path $CORPUS 'manifest.jsonl'
$bytes = ($wavs | Measure-Object Length -Sum).Sum
Write-Log 'INFO' ("pushing {0} utterances, {1:N1} MB" -f $wavs.Count, ($bytes / 1MB))

# tar through ssh: one stream, no rsync on Windows, binary-safe under bash.
# 2026-08-18 (claude-cli-FABLE): `bash -lc` resolved to WSL's bash, and WSL is
# broken on this PC (HCS_E_HYPERV_NOT_INSTALLED — the hypervisor is off; the
# boot log says so every boot). The push FAILED EVERY NIGHT since install,
# eran4's inbox stayed empty, and keshev-lora trained on NOTHING — the mic
# captured 135 MB of Iddo's voice and never learned from a byte of it.
# Fix: no bash at all. Windows ships native tar.exe and ssh.exe; cmd.exe
# pipes binary between them just fine.
$corpusFwd = $CORPUS -replace '\\', '/'
$push = "tar cf - -C `"$corpusFwd`" . | ssh -o BatchMode=yes -o ConnectTimeout=20 $REMOTE `"mkdir -p $REMDIR && tar xf - -C $REMDIR`""
try {
    cmd /c $push 2>&1 | ForEach-Object { if ($_) { Write-Log 'SSH' $_ } }
    if ($LASTEXITCODE -ne 0) { throw "push exited $LASTEXITCODE" }
} catch {
    Write-Log 'FAULT' "push failed: $($_.Exception.Message) — nothing was moved locally"
    return
}
# GATEKEEPER (Iddo 06:09: "watchdog + gatekeeper on the training"): a push
# that leaves the remote inbox EMPTY is a failure even if every command
# exited 0 — never archive local files on an empty remote.
$remoteWavs = [int](ssh -o BatchMode=yes -o ConnectTimeout=20 $REMOTE "find $REMDIR -name '*.wav' | wc -l" 2>$null)
if ($remoteWavs -lt $wavs.Count) {
    Write-Log 'FAULT' "gatekeeper: eran4 holds $remoteWavs wavs but we pushed $($wavs.Count) — NOT archiving local copies"
    return
}

# Verify on the far side BEFORE touching anything here.
$remoteCount = (ssh -o BatchMode=yes -o ConnectTimeout=20 $REMOTE "find $REMDIR -name '*.wav' | wc -l" 2>$null)
Write-Log 'INFO' "eran4 now holds $remoteCount wav files in $REMDIR"

# MOVE, never delete (see the header).
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$dest = Join-Path $SENT $stamp
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Get-ChildItem $CORPUS -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Move-Item $_.FullName (Join-Path $dest $_.Name) -Force }
if (Test-Path $manifest) { Move-Item $manifest (Join-Path $dest 'manifest.jsonl') -Force }
Write-Log 'OK' "archived locally to state\corpus-sent\$stamp (moved, not deleted)"
