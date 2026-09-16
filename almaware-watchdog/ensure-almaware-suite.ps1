# ============================================================
#  ALMAWARE Watchdog  ·  ensure-almaware-suite.ps1
#  Keeps the always-on suite alive: mic · Quorum · Shiri (+ dashboards).
#  SAFE by design: it only *starts* services that are down. It NEVER kills,
#  deletes, or edits anything. Idempotent — safe to run every 2 minutes.
#
#  Usage:
#    pwsh -File ensure-almaware-suite.ps1 -Once            # one health pass (for a scheduled task)
#    pwsh -File ensure-almaware-suite.ps1 -Once -DryRun    # check only, start nothing (safe test)
#    pwsh -File ensure-almaware-suite.ps1                  # loop forever, every -IntervalSec
#
#  לזכרה של עלמה ז"ל · ALMAWARE
# ============================================================
param([switch]$Once, [switch]$DryRun, [int]$IntervalSec = 120)
$ErrorActionPreference = 'SilentlyContinue'

$LogDir = 'D:\CLAUDE\almaware-watchdog'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
$Log = Join-Path $LogDir 'watchdog.log'
function Log($m){ $ts=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); Add-Content -Path $Log -Value "[$ts] $m"; Write-Host "[$ts] $m" }

function PortUp([int]$p){ [bool](Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue) }
function ProcMatch([string]$pat){
  [bool](Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe' OR Name='pwsh.exe' OR Name='powershell.exe'" -ErrorAction SilentlyContinue |
         Where-Object { $_.CommandLine -match $pat })
}

# --- service registry: name · health test · start action --------------------
# PORT-BASED ONLY, on purpose: every check is a listening-port test and every
# start is a fresh, idempotent process launch — so a health pass can NEVER
# disrupt a healthy service. The mic is deliberately NOT managed here (it has
# its own Startup auto-start, and its launcher does kill-and-relaunch which
# must not run on a timer). Shiri is excluded too (it opens the live mic and
# needs the brain up first) — start it manually when you want it.
$Services = @(
  @{ name = 'quorum'
     healthy = { PortUp 8099 }
     start   = { Start-Process pwsh -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','D:\grok\quorum\start-quorum.ps1' -WindowStyle Hidden } },
  @{ name = 'eran-dashboard'
     healthy = { PortUp 8788 }
     start   = { Start-Process pythonw -ArgumentList 'D:\CLAUDE\eran-dashboard\eran_dashboard.py' -WorkingDirectory 'D:\CLAUDE\eran-dashboard' -WindowStyle Hidden } },
  @{ name = 'gist-dash'
     healthy = { PortUp 8092 }
     start   = { Start-Process pythonw -ArgumentList 'D:\CLAUDE\gist-dash\gist_dash.py' -WorkingDirectory 'D:\CLAUDE\gist-dash' -WindowStyle Hidden } },
  @{ name = 'eran-local-dashboard'
     healthy = { PortUp 8790 }
     start   = { Start-Process pythonw -ArgumentList 'D:\CLAUDE\eran-local-dashboard\server.py' -WorkingDirectory 'D:\CLAUDE\eran-local-dashboard' -WindowStyle Hidden } }
)

function Tick {
  $up=0; $started=0
  foreach ($s in $Services) {
    $ok = [bool](& $s.healthy)
    if ($ok) { Log ("{0,-16} OK" -f $s.name); $up++ }
    else {
      if ($DryRun) { Log ("{0,-16} DOWN  (dry-run: would start)" -f $s.name) }
      else {
        Log ("{0,-16} DOWN  -> starting" -f $s.name)
        try { & $s.start; $started++ } catch { Log ("{0,-16} start FAILED: {1}" -f $s.name,$_) }
      }
    }
  }
  Log ("pass complete: {0}/{1} up, {2} (re)started" -f $up,$Services.Count,$started)
}

Log ("=== watchdog start (Once={0} DryRun={1} interval={2}s) ===" -f $Once,$DryRun,$IntervalSec)
if ($Once) { Tick }
else { while ($true) { Tick; Start-Sleep -Seconds $IntervalSec } }
