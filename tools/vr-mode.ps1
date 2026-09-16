<#
.SYNOPSIS
  VR MODE -- free the graphics card, then start SteamVR. And put it all back after.

.DESCRIPTION
  Iddo, 2026-08-29: "סדר לי את התלת מימד שלא יהיה לאג".

  MEASURED THAT DAY, and the cause is not what we assumed:

    * power limit  290 W of a 290 W maximum -- NOT capped. The "80% cap" in memory
                   is not applied. GPU 43 C. The card is healthy.
    * SteamVR      512 DLLs, ZERO zero-byte files. The 2026-08-22 zeroed-update
                   scar is repaired. The install is not corrupt.
    * VRAM         6,546 of 8,192 MiB already in use AT IDLE -- 80% -- with
                   21 separate processes holding the GPU.

  That last line is the lag. A 3070 Ti has 8 GB. SteamVR's compositor plus a scene
  wants 2-4 GB of it. There is nothing left to give, so the driver starts evicting
  textures across PCIe every frame, and an evicted frame in VR is not a slow frame,
  it is a dropped one -- which is what a person feels as lag and, after a while, as
  nausea.

  So this does not "optimise" anything. It empties the card.

.NOTES
  SACRED AUDIO LAW: this touches no playback device, ever. It stops a MICROPHONE
  and a decoder, which is a different thing.
  ONE-MIC LAW: stopping KESHEV here is a clean handover, not a second client.
  Chrome is NOT killed by default -- his tabs are his work. -IncludeChrome opts in.
#>
[CmdletBinding()]
param(
    [switch]$Restore,
    [switch]$IncludeChrome,
    [switch]$NoLaunch,
    [switch]$WhatIfOnly
)

$ErrorActionPreference = 'Stop'

function Get-VramMiB {
    try {
        $o = & nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>$null
        $p = ($o -split ',').Trim()
        return @{ used = [int]$p[0]; total = [int]$p[1] }
    } catch { return $null }
}

function Show-Vram([string]$when) {
    $v = Get-VramMiB
    if ($v) {
        $pct = [math]::Round(100.0 * $v.used / $v.total)
        Write-Host ("  VRAM {0,-8} {1,5} / {2} MiB  ({3}%)" -f $when, $v.used, $v.total, $pct)
        return $v.used
    }
    Write-Host "  VRAM $when : nvidia-smi unavailable"
    return -1
}

# The GPU tenants worth evicting, heaviest first. Each is restartable and none of
# them is doing anything a person is watching while a headset is on their face.
$Tenants = @(
    @{ Name = 'KESHEV mic (client.app)'; Match = 'client\.app';            Restart = 'D:\CLAUDE\mic-rebuild\RUN-KESHEV.cmd' },
    @{ Name = 'KESHEV STT server';       Match = 'server\.stt_server';     Restart = 'D:\CLAUDE\mic-rebuild\RUN-STT-PC.cmd' },
    @{ Name = 'KESHEV 5000';             Match = 'keshev-next.app.(gui|main)\.py'; Restart = $null },
    @{ Name = 'Godot / ALMA VR editor';  Match = 'Godot';                  Restart = $null },
    @{ Name = 'ALMA Draughtsman';        Match = 'alma-draughtsman';       Restart = $null }
)

if ($Restore) {
    Write-Host ''
    Write-Host 'VR MODE -- RESTORE' -ForegroundColor Cyan
    Show-Vram 'now' | Out-Null
    foreach ($t in $Tenants) {
        if ($t.Restart -and (Test-Path $t.Restart)) {
            Write-Host ("  starting back: " + $t.Name)
            if (-not $WhatIfOnly) {
                Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', $t.Restart `
                    -WorkingDirectory (Split-Path -Parent $t.Restart) | Out-Null
                Start-Sleep -Seconds 3
            }
        }
    }
    Write-Host ''
    Write-Host 'The mic comes back warm in about a minute.' -ForegroundColor Green
    return
}

Write-Host ''
Write-Host 'VR MODE -- clearing the graphics card' -ForegroundColor Cyan
Write-Host ''
$before = Show-Vram 'before'

$stopped = 0
foreach ($t in $Tenants) {
    $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
               Where-Object { $_.CommandLine -and $_.CommandLine -match $t.Match })
    foreach ($p in $procs) {
        Write-Host ("  stopping {0}  (pid {1})" -f $t.Name, $p.ProcessId)
        if (-not $WhatIfOnly) {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            $stopped++
        }
    }
}

if ($IncludeChrome) {
    $c = @(Get-Process chrome -ErrorAction SilentlyContinue)
    if ($c.Count) {
        Write-Host ("  stopping Chrome ({0} processes) -- you asked for it with -IncludeChrome" -f $c.Count)
        if (-not $WhatIfOnly) { $c | Stop-Process -Force -ErrorAction SilentlyContinue; $stopped += $c.Count }
    }
} else {
    $c = @(Get-Process chrome -ErrorAction SilentlyContinue)
    if ($c.Count) {
        Write-Host ("  NOT touching Chrome ({0} processes, a GPU tenant). Close its heavy tabs," -f $c.Count) -ForegroundColor Yellow
        Write-Host "  or re-run with -IncludeChrome, if VRAM is still tight." -ForegroundColor Yellow
    }
}

if (-not $WhatIfOnly) { Start-Sleep -Seconds 6 }
Write-Host ''
$after = Show-Vram 'after'
if ($before -ge 0 -and $after -ge 0) {
    Write-Host ''
    Write-Host ("  FREED {0} MiB by stopping {1} process(es)." -f ($before - $after), $stopped) -ForegroundColor Green
    $head = 8192 - $after
    if ($head -lt 3000) {
        Write-Host ("  WARNING: only {0} MiB left for SteamVR. It wants 2000-4000." -f $head) -ForegroundColor Red
        Write-Host "  Close Chrome tabs, or re-run with -IncludeChrome." -ForegroundColor Red
    } else {
        Write-Host ("  {0} MiB free for SteamVR. That is enough." -f $head) -ForegroundColor Green
    }
}

if (-not $NoLaunch -and -not $WhatIfOnly) {
    Write-Host ''
    Write-Host 'Starting SteamVR...' -ForegroundColor Cyan
    Start-Process 'steam://run/250820'
}

Write-Host ''
Write-Host 'When you are done, put everything back with:' -ForegroundColor Cyan
Write-Host '  powershell -ExecutionPolicy Bypass -File D:\CLAUDE\tools\vr-mode.ps1 -Restore'
Write-Host ''
