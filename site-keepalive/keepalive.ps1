# ALMA site keepalive — runs every 6h via Task Scheduler.
# Keeps the Eran live-bridge/funnel up and health-checks all iddoperez.ai sites.
$dir = "D:\CLAUDE\site-keepalive"
$log = Join-Path $dir "keepalive.log"
$ts  = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
function Log($m){ Add-Content -Path $log -Value "$ts  $m" }

Log "===== keepalive run ====="

# 1) Ensure the Eran live-bridge (feeds the front window) is up on eran1
try {
  $act = ssh -o BatchMode=yes -o ConnectTimeout=6 eran1 "systemctl --user is-active eran-live-bridge" 2>$null
  if ("$act".Trim() -ne "active") {
    ssh -o BatchMode=yes -o ConnectTimeout=6 eran1 "systemctl --user restart eran-live-bridge" 2>$null
    Log "bridge was '$($act)'.Trim() -> RESTARTED"
  } else { Log "bridge: active" }
} catch { Log "bridge check error: $($_.Exception.Message)" }

# 2) Health-check every site + the funnel
$sites = @(
  "https://eran-swarm.pages.dev/",
  "https://iddoperez.ai/",
  "https://alma.iddoperez.ai/",
  "https://pong.iddoperez.ai/",
  "https://cafe.iddoperez.ai/",
  "https://<tailnet-host>/",
  "https://eran.iddoperez.ai/"
)
foreach ($s in $sites) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 -Uri $s
    Log ("OK   {0}  {1}" -f $r.StatusCode, $s)
  } catch {
    Log ("DOWN {0}  ({1})" -f $s, $_.Exception.Message)
  }
}
Log "----- done -----"
