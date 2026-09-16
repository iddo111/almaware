<#
    KESHEV WATCHDOG — the thing that notices.

    Iddo, 2026-08-15, "rosh gadol": stop hand-restarting the mic and build the
    thing that catches it.

    THE HOLE THIS FILLS, measured twice in 24 hours:
      * 2026-08-15 04:06 — the running session sat DEAF for hours: 121 segments
        captured, 116 spilled with err=deaf, p50=0. A whole night of dictation
        was recorded to spool and never typed. Nothing noticed.
      * 2026-08-15 14:06 — the BRIO handle went bad; the app logged 343+
        RERESOLVE_ERROR / PortAudioError WdmSyncIoctl in a loop for 40 minutes
        while reporting itself alive. Nothing noticed. Iddo noticed, and had to
        type the word "mic".
      Both times the fix was the same four seconds of work: stop it, start it.

    WHAT IT DOES NOT DO, on purpose:
      * It never starts KESHEV when alma-mic is alive — the app enforces the
        ONE-MIC LAW itself and exits EXIT_ALMAMIC_ALIVE; the watchdog simply
        does not fight that.
      * It never touches audio OUTPUT devices, never opens a Bluetooth device,
        and never changes config. SACRED AUDIO LAW.
      * It never deletes anything.
      * It backs off: at most one restart per COOLDOWN_MIN, and after
        MAX_RESTARTS_PER_HOUR it stops restarting and only ALARMS. A watchdog
        that restarts a genuinely broken app forever is a fork bomb with
        patience.

    Run: powershell -NoProfile -ExecutionPolicy Bypass -File tools\keshev-watchdog.ps1
    Install as a task: tools\keshev-watchdog.ps1 -Install
#>
param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Once,
    # -Status: READ-ONLY. Print the verdict and exit (0 = fine, 1 = fault).
    # Never restarts, never writes the log, never shows the alarm. Safe to
    # run against the LIVE mic at any time — added 2026-08-17 so the verdict
    # logic is testable and a human can ask "what do you see?" without arming
    # anything.
    [switch]$Status,
    # -EventsPath: point the verdict at a different journal (tests use
    # fixture journals; default is the live one).
    [string]$EventsPath = '',
    # -JournalOnly: skip the process-liveness check and judge from the
    # journal alone (tests have no KESHEV process to find; the live DOWN
    # verdict is meaningless against a fixture).
    [switch]$JournalOnly,
    [int]$DeafMinutes = 10,
    [int]$CooldownMin = 10,
    [int]$MaxRestartsPerHour = 4,
    # Do not re-show the alarm window more often than this.
    [int]$AlarmCooldownMin = 30
)

$ErrorActionPreference = 'Stop'
$ROOT      = Split-Path -Parent $PSScriptRoot
$EVENTS    = if ($EventsPath) { $EventsPath } else { Join-Path $ROOT 'state\events.jsonl' }
$LOG       = Join-Path $ROOT 'state\watchdog.log'
$RUNNER    = Join-Path $ROOT 'RUN-KESHEV.cmd'
$STAMPFILE = Join-Path $ROOT 'state\watchdog-restarts.json'
$ALARMSCRIPT = Join-Path $PSScriptRoot 'keshev-alarm.ps1'
$ALARMSTATE  = Join-Path $ROOT 'state\alarm-state.json'
$TASKNAME  = 'KESHEV-Watchdog'

function Write-Log([string]$level, [string]$msg) {
    $line = "{0} [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $level, $msg
    Add-Content -Path $LOG -Value $line -Encoding UTF8
    Write-Output $line
}

# --------------------------------------------------------------- install --

if ($Install) {
    $action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -Once' -f $PSCommandPath)
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes 2)
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $TASKNAME -Action $action -Trigger $trigger `
        -Settings $settings -Description 'Notices when the KESHEV mic goes deaf or loses its device, and restarts it. Never starts it while alma-mic is alive.' -Force | Out-Null
    Write-Log 'INFO' "installed scheduled task '$TASKNAME' (every 2 min)"
    return
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TASKNAME -Confirm:$false -ErrorAction SilentlyContinue
    Write-Log 'INFO' "removed scheduled task '$TASKNAME'"
    return
}

# ----------------------------------------------------------- inspection --

function Get-KeshevProcs {
    Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'client\.app|keshev_worker' }
}

function Test-AlmaMicAlive {
    $p = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'alma-mic' -and $_.CommandLine -notmatch 'watchdog' }
    return [bool]$p
}

function Get-UsbMicPresent {
    # Authorized USB capture devices only. A Bluetooth headset is NEVER a mic.
    $ok = Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Status -eq 'OK' -and
            $_.FriendlyName -match 'BRIO|Scarlett|USBAudio' -and
            $_.FriendlyName -notmatch 'WH-1000|Hands-Free|Headset|Bluetooth'
        }
    return [bool]$ok
}

function Get-MicHolders {
    # Read-only: who does Windows think is capturing right now.
    $roots = @(
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone'
    )
    $out = @()
    foreach ($r in $roots) {
        foreach ($k in (Get-ChildItem $r -Recurse -ErrorAction SilentlyContinue)) {
            $p = Get-ItemProperty $k.PSPath -ErrorAction SilentlyContinue
            if ($null -eq $p) { continue }
            if ($p.PSObject.Properties.Name -notcontains 'LastUsedTimeStop') { continue }
            if ([int64]$p.LastUsedTimeStop -eq 0) { $out += $k.PSChildName }
        }
    }
    return $out
}

function Get-Verdict {
    <# Returns: HEALTHY | STARTING | DOWN | STUCK_DEVICE | DEAF | MUTE | NO_MIC | UNKNOWN #>
    if (-not $JournalOnly) {
        $procs = @(Get-KeshevProcs)
        if ($procs.Count -eq 0) { return @{ verdict = 'DOWN'; detail = 'no app or worker process' } }
    }
    if (-not (Test-Path $EVENTS)) { return @{ verdict = 'UNKNOWN'; detail = 'no journal yet' } }

    # @() matters: a ONE-line journal makes Get-Content return a bare string,
    # and $tail[$i] on a string indexes CHARACTERS — the SESSION_BEGIN scan
    # then never matches and a 2-minute-old session reads as DEAF. Found by
    # the -Status tests, 2026-08-17.
    $tail = @(Get-Content $EVENTS -Tail 800 -ErrorAction SilentlyContinue)
    if (-not $tail) { return @{ verdict = 'UNKNOWN'; detail = 'empty journal' } }

    # SESSION SCOPING — found by the watchdog's own first live run, 14:51.
    # It counted 30 RERESOLVE_ERROR "in the last 10 minutes" and restarted a
    # process that had already been restarted two minutes earlier: the errors
    # were real, but they belonged to the DEAD session. Judging a live process
    # by a dead one's journal is a restart loop with extra steps. Only events
    # after the newest SESSION_BEGIN describe the process that is running now.
    $sessionStart = $null
    for ($i = $tail.Count - 1; $i -ge 0; $i--) {
        if ($tail[$i] -match '"SESSION_BEGIN"') {
            try { $sessionStart = [datetime](($tail[$i] | ConvertFrom-Json).ts) } catch { }
            break
        }
    }

    $now = Get-Date
    $recent = @()
    foreach ($line in $tail) {
        try { $j = $line | ConvertFrom-Json } catch { continue }
        $ts = $null
        try { $ts = [datetime]$j.ts } catch { continue }
        if ($sessionStart -and $ts -lt $sessionStart) { continue }   # dead session
        if (($now - $ts).TotalMinutes -le $DeafMinutes) {
            $recent += [pscustomobject]@{ ts = $ts; evt = $j.evt; state = $j.state }
        }
    }

    # A session younger than the deaf window has not had time to prove itself
    # healthy; calling it DEAF would restart every fresh start (the worker takes
    # ~95 s to load and the journal is quiet the whole time).
    $sessionAgeMin = if ($sessionStart) { ($now - $sessionStart).TotalMinutes } else { 999 }

    # A device handle that will not reopen: the 14:06 failure mode.
    $reresolve = @($recent | Where-Object { $_.state -eq 'RERESOLVE_ERROR' })
    if ($reresolve.Count -ge 3) {
        return @{ verdict = 'STUCK_DEVICE'; detail = "$($reresolve.Count) RERESOLVE_ERROR in $DeafMinutes min" }
    }

    # Idle-no-mic while an authorized USB mic is actually present and OK.
    # 2026-08-18 05:5x (claude-cli-FABLE, Iddo's goal "a mic that NEVER breaks"):
    # every start passes through TRAY_IDLE_NO_MIC for ~1 s (DEVICE_OPEN ->
    # CAPTURING -> TRAY_IDLE_NO_MIC -> HOTKEY_BOUND -> WINDOW_OPEN -> READY);
    # a watchdog tick landing inside that second would restart a mic that was
    # one second from healthy. The state must PERSIST before it is a fault.
    $lastStateEvt = ($recent | Where-Object { $_.state } | Select-Object -Last 1)
    $lastState = $lastStateEvt.state
    if ($lastState -eq 'TRAY_IDLE_NO_MIC' -or $lastState -eq 'IDLE_NO_MIC') {
        $idleAgeMin = if ($lastStateEvt.ts) { ($now - $lastStateEvt.ts).TotalMinutes } else { 999 }
        if ($idleAgeMin -lt 3) {
            return @{ verdict = 'STARTING'; detail = "IDLE_NO_MIC for only $([int]($idleAgeMin * 60)) s — the app is still opening the device; not a fault yet" }
        }
        if (Get-UsbMicPresent) {
            return @{ verdict = 'STUCK_DEVICE'; detail = "IDLE_NO_MIC for $([int]$idleAgeMin) min while a USB mic is present and OK" }
        }
        return @{ verdict = 'NO_MIC'; detail = 'IDLE_NO_MIC and no authorized USB mic present — correct, not a fault' }
    }

    # Alive but hearing nothing at all: the 04:06 failure mode.
    $segs    = @($recent | Where-Object { $_.evt -eq 'SEG' })
    $decodes = @($recent | Where-Object { $_.evt -eq 'DECODE' })
    $typed   = @($recent | Where-Object { $_.evt -eq 'TYPED' })
    $spilled = @($recent | Where-Object { $_.evt -eq 'SPILLED' })
    $heard = @($recent | Where-Object { $_.evt -in @('SEG', 'GATED', 'DECODE', 'TYPED') })
    if ($heard.Count -eq 0) {
        if ($sessionAgeMin -lt $DeafMinutes) {
            return @{ verdict = 'STARTING'; detail = "session is $([int]$sessionAgeMin) min old; the worker takes ~95 s to load and journals nothing meanwhile" }
        }
        # 2026-08-18 04:2x — THE SILENT-ROOM BUG, found by Iddo asking "why does
        # it fall asleep". A sleeping house produces ZERO segments, and this
        # branch read that silence as DEAF and restarted the mic every 12
        # minutes, all night — 15 duplicate SESSION_BEGINs in one journal.
        # Silence is not a fault. The app self-reports via HEARTBEAT every
        # ~60 s even when nothing is heard: a live heartbeat with an empty room
        # is QUIET, not DEAF. No heartbeat either — THEN the process is wedged.
        $beats = @($recent | Where-Object { $_.evt -eq 'HEARTBEAT' })
        if ($beats.Count -ge 1) {
            return @{ verdict = 'HEALTHY'; detail = "QUIET room: $($beats.Count) heartbeats, zero audio in $DeafMinutes min — silence is not a fault" }
        }
        return @{ verdict = 'DEAF'; detail = "no SEG/GATED/DECODE/TYPED and NO HEARTBEAT in $DeafMinutes min while running" }
    }

    # ------------------------------------------------------------------ MUTE
    # 2026-08-16 12:21, and this is the whole reason the check above was not
    # enough. A change to the router stopped decoding completely. Capture went
    # on perfectly: SEG after SEG, the spool filled to 50 and began to SPILL,
    # and for an hour and fifty minutes not one word reached his screen.
    #
    # This watchdog wrote "OK healthy — 52 segments in 10 min" every two
    # minutes for the whole of it, because ONE SEG was enough to satisfy the
    # line above. It was measuring that the mic could HEAR. Nobody was
    # measuring that anything came OUT.
    #
    # That is the workspace's own law — `health: ok` is not working — enforced
    # against this file. Hearing is not the product. TEXT IN HIS WINDOW is the
    # product, and the verdict now says so.
    if ($segs.Count -ge 3 -and $decodes.Count -eq 0 -and $sessionAgeMin -ge 3) {
        return @{ verdict = 'MUTE'; detail = "$($segs.Count) segments captured and ZERO decodes in $DeafMinutes min — it hears and does not understand" }
    }

    # The spool is the queue between capture and decode. It overflowing means
    # the consumer stalled, whatever the reason.
    if ($spilled.Count -ge 5 -and $decodes.Count -eq 0) {
        return @{ verdict = 'MUTE'; detail = "$($spilled.Count) SPILLED with zero decodes — the spool is overflowing, nothing is draining it" }
    }

    # Understands but never types. Guard drops are legitimate (noise, a video
    # in the room), so this needs a lot of decodes and no typing at all before
    # it calls a fault.
    #
    # 2026-08-18 (claude-cli-FABLE, "a mic that NEVER breaks"): a decode that
    # ended in GUARD_DROP (noise / not-a-command) or GATED (presence guard:
    # Iddo is away, the typer REFUSES on purpose) is the mic WORKING, not a
    # fault. Iddo away with a TV on = 8+ decodes, 0 typed, all GATED — the old
    # rule restarted a healthy mic for that. Only decodes that vanish with NO
    # recorded reason are suspicious, and even then a restart is itself a
    # 60-second break, so this verdict now ALARMS (visible window) instead of
    # restarting: MUTE_SOFT.
    if ($decodes.Count -ge 8 -and $typed.Count -eq 0) {
        $explained = @($recent | Where-Object { $_.evt -in @('GUARD_DROP', 'GATED') })
        if ($explained.Count -eq 0) {
            return @{ verdict = 'MUTE_SOFT'; detail = "$($decodes.Count) decodes, NOTHING typed and no GUARD_DROP/GATED reason in $DeafMinutes min — it understands and does not speak (alarm only, no restart)" }
        }
    }

    # The detail line now carries all three numbers, so a human skimming the
    # log can never again read "healthy" and miss that the middle is dead.
    return @{ verdict = 'HEALTHY'; detail = "seg=$($segs.Count) decode=$($decodes.Count) typed=$($typed.Count) in $DeafMinutes min" }
}

# ---------------------------------------------------------------- alarm --
# The visible half of the watchdog (2026-08-17). The old behaviour wrote
# ALARM into a log nobody reads while the mic sat deaf — the 08-15 04:06
# night all over again, one file to the left. Now: any FAULT verdict that
# did NOT end in a restart pops a bright topmost window (tools\
# keshev-alarm.ps1). VISUAL ONLY — Sacred Audio Law: never a sound.
# Deduped: at most one window per $AlarmCooldownMin, and never a second
# while the first is still on screen.

function Show-Alarm([string]$verdict, [string]$detail) {
    if (-not (Test-Path $ALARMSCRIPT)) {
        Write-Log 'ERROR' "alarm wanted ($verdict) but $ALARMSCRIPT is missing"
        return
    }
    if (Test-Path $ALARMSTATE) {
        try {
            $st = Get-Content $ALARMSTATE -Raw | ConvertFrom-Json
            $shown = [datetime]$st.shown
            $alive = $st.pid -and (Get-Process -Id $st.pid -ErrorAction SilentlyContinue)
            if ($alive) { return }                                   # one window at a time
            if (((Get-Date) - $shown).TotalMinutes -lt $AlarmCooldownMin) { return }
        } catch { }                                                  # unreadable state: show
    }
    $p = Start-Process -FilePath 'powershell.exe' -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ALARMSCRIPT,
        '-Verdict', $verdict, '-Detail', $detail)
    @{ shown = (Get-Date).ToString('o'); pid = $p.Id } |
        ConvertTo-Json | Set-Content $ALARMSTATE -Encoding UTF8
    Write-Log 'ALARM' "alarm window shown for $verdict — $detail"
}

# -------------------------------------------------------------- backoff --

function Get-RestartHistory {
    if (Test-Path $STAMPFILE) {
        try { return @((Get-Content $STAMPFILE -Raw | ConvertFrom-Json) | ForEach-Object { [datetime]$_ }) } catch { return @() }
    }
    return @()
}

function Add-RestartStamp {
    $hist = @(Get-RestartHistory) + (Get-Date)
    $keep = $hist | Where-Object { ((Get-Date) - $_).TotalHours -le 2 }
    ($keep | ForEach-Object { $_.ToString('o') }) | ConvertTo-Json | Set-Content $STAMPFILE -Encoding UTF8
}

function Restart-Keshev([string]$why, [string]$detail = '') {
    $hist = @(Get-RestartHistory)
    $lastHour = @($hist | Where-Object { ((Get-Date) - $_).TotalMinutes -le 60 })
    $last = $hist | Sort-Object -Descending | Select-Object -First 1

    # Every refusal below leaves the mic broken with nothing done about it —
    # that is exactly when a HUMAN must see a window, not a log line.
    if ($last -and ((Get-Date) - $last).TotalMinutes -lt $CooldownMin) {
        Write-Log 'HOLD' "$why — but last restart was $([int]((Get-Date) - $last).TotalMinutes) min ago (cooldown $CooldownMin). Not restarting."
        Show-Alarm $why "restart held (cooldown): $detail"
        return
    }
    if ($lastHour.Count -ge $MaxRestartsPerHour) {
        Write-Log 'ALARM' "$why — $($lastHour.Count) restarts in the last hour already. REFUSING to restart again; this needs a human. KESHEV is probably broken, not stuck."
        Show-Alarm $why "restarting stopped helping ($($lastHour.Count) in the last hour): $detail"
        return
    }
    if (Test-AlmaMicAlive) {
        Write-Log 'HOLD' "$why — alma-mic is alive. ONE-MIC LAW: not starting KESHEV."
        Show-Alarm $why "alma-mic holds the mic (ONE-MIC LAW): $detail"
        return
    }

    $holders = @(Get-MicHolders)
    if ($holders.Count) { Write-Log 'INFO' "mic currently held by: $($holders -join ', ')" }

    foreach ($p in @(Get-KeshevProcs)) {
        Write-Log 'INFO' "stopping pid $($p.ProcessId)"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 4
    Start-Process -FilePath $RUNNER -WorkingDirectory $ROOT
    Add-RestartStamp
    Write-Log 'RESTART' "$why — KESHEV restarted"
}

# ----------------------------------------------------------------- main --

$v = Get-Verdict

if ($Status) {
    # READ-ONLY: one line, one exit code, zero side effects. No log write,
    # no restart, no alarm — the question "what do you see?" must never be
    # the thing that acts.
    Write-Output ("VERDICT: {0} — {1}" -f $v.verdict, $v.detail)
    if ($v.verdict -in @('DOWN', 'STUCK_DEVICE', 'DEAF', 'MUTE', 'MUTE_SOFT')) { exit 1 }
    exit 0
}

switch ($v.verdict) {
    'HEALTHY'      { Write-Log 'OK'    "healthy — $($v.detail)" }
    'STARTING'     { Write-Log 'OK'    "starting — $($v.detail)" }
    'NO_MIC'       { Write-Log 'OK'    "idle, no authorized USB mic — $($v.detail)" }
    'UNKNOWN'      { Write-Log 'INFO'  "cannot tell — $($v.detail)" }
    'DOWN'         { Write-Log 'FAULT' "DOWN — $($v.detail)"; Restart-Keshev 'DOWN' $v.detail }
    'STUCK_DEVICE' { Write-Log 'FAULT' "STUCK — $($v.detail)"; Restart-Keshev 'STUCK_DEVICE' $v.detail }
    'DEAF'         { Write-Log 'FAULT' "DEAF — $($v.detail)"; Restart-Keshev 'DEAF' $v.detail }
    'MUTE'         { Write-Log 'FAULT' "MUTE — $($v.detail)"; Restart-Keshev 'MUTE' $v.detail }
    # Alarm only — a restart is itself a 60 s break, and this shape has benign
    # causes a restart cannot fix. A human sees a window; the mic keeps running.
    'MUTE_SOFT'    { Write-Log 'FAULT' "MUTE_SOFT — $($v.detail)"; Show-Alarm 'MUTE_SOFT' $v.detail }
}
