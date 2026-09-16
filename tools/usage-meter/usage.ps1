# Claude Code + Grok Heavy usage meter
# Reads local CC transcripts via ccusage; prints reset windows + Grok ETA.
# Run: powershell -File D:\CLAUDE\tools\usage-meter\usage.ps1

$ErrorActionPreference = 'Continue'

function Get-ResetMonday {
  # CC weekly resets fire Monday 00:00 local. Find next Monday.
  $now = Get-Date
  $daysUntilMon = (1 - [int]$now.DayOfWeek + 7) % 7
  if ($daysUntilMon -eq 0 -and $now.Hour -ge 0) { $daysUntilMon = 7 }
  $reset = $now.Date.AddDays($daysUntilMon)
  return $reset
}

Write-Host "=== CLAUDE CODE USAGE ===" -ForegroundColor Cyan
$cc = Get-Command ccusage -ErrorAction SilentlyContinue
if ($cc) {
  & ccusage daily --since (Get-Date).AddDays(-7).ToString('yyyy-MM-dd') 2>&1 | Select-Object -Last 20
  Write-Host ""
  Write-Host "--- BLOCKS (5h windows) ---" -ForegroundColor DarkCyan
  & ccusage blocks --active 2>&1 | Select-Object -Last 15
} else {
  Write-Host "ccusage not installed. Install: npm i -g ccusage" -ForegroundColor Yellow
}

$nextMon = Get-ResetMonday
$daysLeft = ($nextMon - (Get-Date)).TotalDays
Write-Host ""
Write-Host "=== WEEKLY RESET ===" -ForegroundColor Cyan
Write-Host "Claude Code weekly reset: $($nextMon.ToString('yyyy-MM-dd ddd HH:mm')) (in $([math]::Round($daysLeft,1)) days)"
Write-Host "  Models share the weekly bucket: Opus 4.7, Sonnet 4.6, Haiku 4.5"
Write-Host "  Rolling 5h blocks also enforced (see 'ccusage blocks')"

Write-Host ""
Write-Host "=== GROK HEAVY ===" -ForegroundColor Cyan
Write-Host "  Grok Heavy quota model: per-day rolling, no fixed weekly reset."
Write-Host "  Check live: https://x.com/i/grok (sidebar shows remaining)"
Write-Host "  X/Grok API status: https://api.x.ai (requires auth)"

Write-Host ""
$tgt = 0.98
$daysGone = 7 - $daysLeft
$pctSpent = 24  # seed from Iddo's report 2026-05-26
$pctPerDay = if ($daysGone -gt 0) { $pctSpent / $daysGone } else { $pctSpent }
$projected = $pctPerDay * 7
Write-Host "=== PROJECTION (seeded 24% at day $([math]::Round($daysGone,1))) ===" -ForegroundColor Cyan
Write-Host ("  Current burn: {0:N1}%/day  →  week total {1:N0}%" -f $pctPerDay, $projected)
$capForTarget = ($tgt * 100 - $pctSpent) / $daysLeft
Write-Host ("  Cap to hit 98% target: {0:N1}%/day for {1:N1} more days" -f $capForTarget, $daysLeft)
