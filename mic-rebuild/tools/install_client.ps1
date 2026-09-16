<#
.SYNOPSIS
  KESHEV client installer — K4 (PHASE2-DESIGN.md section 7, scars 2/56).

  THE one Scheduled Task "KESHEV": logon trigger, restart-on-failure
  3 times / 10 minutes (the ONLY respawn mechanism — no watchdog process
  exists, scars 3/4/5), IgnoreNew instance policy (defense in depth
  beside the kernel mutex).

  Rival mic persistence (Startup .lnk, scheduled tasks incl. ALMA-MIC-*,
  Run keys) is inventoried and archived to _genizah\mic-persistence-<date>\
  with a JSONL journal. Refuses to install beside a live alma-mic without
  -Coexist (scar 56 — the coexistence window is governed by mic-switch).

.NOTES
  Exit codes: 0 = ok, 1 = error, 3 = refused (alma-mic alive, no -Coexist).

  -DryRun        inventory + journal only; changes NOTHING.
  -Coexist       proceed beside live alma-mic; rival archiving becomes
                 journal-only (the crutch keeps its persistence until cutover).
  -Uninstall     remove the task (idempotent).
  -SimulateAlmaMic Alive|Dead|Auto   test hook: overrides liveness detection
                 so tests are deterministic and never touch the real alma-mic.
  -RunLevel      Highest (production default; needs elevation) or Limited.
                 On access-denied at Highest the script retries Limited and
                 records the achieved level honestly in the SUMMARY line.

  Machine-readable result: one line "SUMMARY:{json}" on stdout.
#>
[CmdletBinding()]
param(
    [switch]$Coexist,
    [switch]$DryRun,
    [switch]$Uninstall,
    [string]$TaskName = "KESHEV",
    [string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)),
    [string]$GenizahRoot = "",
    [ValidateSet("Auto", "Alive", "Dead")][string]$SimulateAlmaMic = "Auto",
    [ValidateSet("Highest", "Limited")][string]$RunLevel = "Highest",
    [string]$PythonExe = "C:\Program Files\Python312\python.exe"
)

$ErrorActionPreference = "Stop"
if (-not $GenizahRoot) { $GenizahRoot = Join-Path $RepoRoot "_genizah" }

$stamp = Get-Date -Format "yyyyMMdd"
$archiveDir = Join-Path $GenizahRoot "mic-persistence-$stamp"
$journalPath = Join-Path $archiveDir "journal.jsonl"

function Write-Journal([hashtable]$entry) {
    if (-not (Test-Path $archiveDir)) { New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null }
    $entry["ts"] = (Get-Date -Format "o")
    Add-Content -Path $journalPath -Value (ConvertTo-Json $entry -Compress -Depth 5) -Encoding UTF8
}

# ---------------------------------------------------------------- alma-mic liveness (scar 56)
function Test-AlmaMicAlive {
    if ($SimulateAlmaMic -eq "Alive") { return $true }
    if ($SimulateAlmaMic -eq "Dead")  { return $false }
    # Auto: READ-ONLY probes. Running ALMA-MIC task state or a live process.
    try {
        $t = Get-ScheduledTask -TaskName "ALMA-MIC*" -ErrorAction SilentlyContinue |
             Where-Object { $_.State -eq "Running" }
        if ($t) { return $true }
    } catch { Write-Verbose "task probe failed: $_" }
    try {
        $p = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
             Where-Object { $_.CommandLine -match "alma-mic|voice-input" }
        if ($p) { return $true }
    } catch { Write-Verbose "process probe failed: $_" }
    return $false
}

# ---------------------------------------------------------------- rival persistence scan (scar 2)
$RivalTaskPatterns = @("ALMA-MIC*", "*alma-mic*", "*voice-input*", "START-MIC*", "*heb-mic*", "HEB-MIC*", "*mic-supervisor*")
$RivalFilePatterns = @("ALMA-MIC*", "START-MIC*", "*voice-input*", "*heb-mic*", "*alma-mic*")

function Get-RivalPersistence {
    $rivals = @()
    # scheduled tasks
    foreach ($pat in $RivalTaskPatterns) {
        $tasks = Get-ScheduledTask -TaskName $pat -ErrorAction SilentlyContinue
        foreach ($t in @($tasks)) {
            if ($t.TaskName -eq $TaskName) { continue }
            $rivals += [pscustomobject]@{
                kind = "task"; name = $t.TaskName
                path = "$($t.TaskPath)$($t.TaskName)"; state = "$($t.State)"
            }
        }
    }
    # Startup folder .lnk / .bat / .cmd / .vbs
    $startupDirs = @(
        [Environment]::GetFolderPath("Startup"),
        [Environment]::GetFolderPath("CommonStartup")
    )
    foreach ($dir in $startupDirs) {
        if (-not (Test-Path $dir)) { continue }
        foreach ($pat in $RivalFilePatterns) {
            foreach ($f in @(Get-ChildItem -Path $dir -Filter $pat -File -ErrorAction SilentlyContinue)) {
                $rivals += [pscustomobject]@{
                    kind = "startup"; name = $f.Name; path = $f.FullName; state = "present"
                }
            }
        }
    }
    # Run keys (HKCU + HKLM)
    foreach ($hive in @("HKCU:\Software\Microsoft\Windows\CurrentVersion\Run",
                        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run")) {
        if (-not (Test-Path $hive)) { continue }
        $props = Get-ItemProperty -Path $hive
        foreach ($p in $props.PSObject.Properties) {
            if ($p.Name -in @("PSPath", "PSParentPath", "PSChildName", "PSDrive", "PSProvider")) { continue }
            $hay = "$($p.Name) $($p.Value)"
            if ($hay -match "alma-mic|voice-input|heb-mic|START-MIC") {
                $rivals += [pscustomobject]@{
                    kind = "runkey"; name = $p.Name; path = "$hive\$($p.Name)"; state = "$($p.Value)"
                }
            }
        }
    }
    # de-duplicate (patterns can overlap)
    $rivals | Sort-Object kind, path -Unique
}

function Invoke-ArchiveRival($rival) {
    # Decide the action; only "ARCHIVED" mutates anything.
    if ($DryRun)  { return "WOULD-ARCHIVE" }
    if ($Coexist) { return "LEFT-ALIVE-COEXIST" }   # the crutch keeps its persistence until cutover
    switch ($rival.kind) {
        "task" {
            Export-ScheduledTask -TaskName $rival.name |
                Set-Content -Path (Join-Path $archiveDir "task-$($rival.name).xml") -Encoding UTF8
            Disable-ScheduledTask -TaskName $rival.name | Out-Null
        }
        "startup" {
            Move-Item -Path $rival.path -Destination (Join-Path $archiveDir $rival.name) -Force
        }
        "runkey" {
            $hive = Split-Path $rival.path -Parent
            Set-Content -Path (Join-Path $archiveDir "runkey-$($rival.name).txt") -Value $rival.state -Encoding UTF8
            Remove-ItemProperty -Path $hive -Name $rival.name
        }
    }
    return "ARCHIVED"
}

# ---------------------------------------------------------------- the ONE task (scar 2, section 7)
function Register-KeshevTask {
    $action = New-ScheduledTaskAction -Execute $PythonExe `
        -Argument "`"$RepoRoot\client\app.py`"" -WorkingDirectory $RepoRoot
    $user = "$env:USERDOMAIN\$env:USERNAME"
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $settings = New-ScheduledTaskSettingsSet `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10) `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $levels = @($RunLevel)
    if ($RunLevel -eq "Highest") { $levels += "Limited" }  # honest fallback in non-elevated sessions
    foreach ($lvl in $levels) {
        try {
            Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
                -Settings $settings -User $user -RunLevel $lvl -Force | Out-Null
            return $lvl
        } catch {
            if ($lvl -eq $levels[-1]) { throw }
            Write-Warning "RunLevel $lvl refused ($($_.Exception.Message.Trim())) - retrying Limited"
        }
    }
}

function Emit-Summary([hashtable]$s) {
    Write-Output ("SUMMARY:" + (ConvertTo-Json $s -Compress -Depth 6))
}

# ================================================================ main
try {
    if ($Uninstall) {
        $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($existing) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Output "KESHEV installer: task '$TaskName' unregistered"
        } else {
            Write-Output "KESHEV installer: task '$TaskName' not present (uninstall is idempotent)"
        }
        Emit-Summary @{ mode = "uninstall"; task_name = $TaskName; task_registered = $false
                        refused = $false; dry_run = $false; coexist = $false
                        rivals = @(); journal = ""; run_level = "" }
        exit 0
    }

    $alive = Test-AlmaMicAlive
    if ($alive -and -not $Coexist) {
        Write-Output "REFUSED: alma-mic is ALIVE and -Coexist was not given (scar 56)."
        Write-Output "  The coexistence window is governed by mic-switch; stop alma-mic"
        Write-Output "  via 'mic-switch new' or re-run with -Coexist."
        exit 3
    }

    Write-Journal @{ kind = "run"; dry_run = [bool]$DryRun; coexist = [bool]$Coexist
                     alma_mic_alive = $alive; simulate = $SimulateAlmaMic; task_name = $TaskName }

    $rivals = @(Get-RivalPersistence)
    $rivalOut = @()
    foreach ($r in $rivals) {
        $act = Invoke-ArchiveRival $r
        $entry = @{ kind = $r.kind; name = $r.name; path = $r.path; action = $act }
        Write-Journal $entry
        $rivalOut += $entry
    }

    $achievedLevel = ""
    $registered = $false
    if (-not $DryRun) {
        $achievedLevel = Register-KeshevTask
        $registered = $true
        Write-Journal @{ kind = "task-registered"; name = $TaskName; run_level = $achievedLevel }
    }

    Emit-Summary @{ mode = "install"; task_name = $TaskName; task_registered = $registered
                    refused = $false; dry_run = [bool]$DryRun; coexist = [bool]$Coexist
                    alma_mic_alive = $alive; rivals = $rivalOut; journal = $journalPath
                    run_level = $achievedLevel }
    exit 0
} catch {
    Write-Error "KESHEV installer FAILED: $_"
    exit 1
}
