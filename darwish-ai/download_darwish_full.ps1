# download_darwish_full.ps1 - the FULL sweep. Iddo, 2026-08-16 22:55:
#   "expand the corpus for big Darwish and small, to every set and every track,
#    big and small."
#
# THREE THINGS WERE BROKEN AND ARE FIXED HERE
#  1. The scheduled task Darwish-YT-Download has been FAILING, not running.
#     LastTaskResult 2147942402 = 0x80070002 ERROR_FILE_NOT_FOUND: it invokes bare
#     "pwsh.exe", which is a Store alias that does not resolve inside a task. The
#     sweep has therefore downloaded nothing at all. Fixed by using the resolved
#     absolute interpreter path when the task is re-registered.
#  2. The old runs still carried --match-filter "duration > 3600", visible in
#     _download.log as "does not pass filter (duration > 3600), skipping". The
#     2026-08-14 catalogue survey found 338 unique items / 106.5 h, of which only
#     42 items / 64.3 h are over an hour. That filter was throwing away 296 items
#     and 42.2 hours - every single individual TRACK. Lower bound is now 120 s,
#     which drops only clips and teasers.
#  3. No JavaScript runtime. YouTube now demands a JS signature challenge; without
#     one, extraction degrades and ends in "Sign in to confirm you're not a bot".
#     Verified by hand at 22:56 today: WITH --js-runtimes node and NO Google login,
#     search and extraction both succeed. So the corpus does NOT depend on fixing
#     his Google account first.
#
# All 31 queries from catalog_survey.json - the same sweep that found the 338.
$ErrorActionPreference = 'Continue'

$dest = 'D:\Darwish'
New-Item -ItemType Directory -Force $dest | Out-Null
Set-Location $dest

$queries = @(
  'darwish psytrance set','darwish desert adventure','dj darwish goa trance',
  'darwish live set trance','darwish ozora','darwish psytrance','dj darwish',
  'darwish deep dave','deep dave psytrance','darwish remix psytrance',
  'darwish original mix psytrance','darwish full album psytrance',
  'darwish ep psytrance','darwish live psytrance israel','darwish trance mix',
  'darwish psy trance track','darwish festival set','darwish stomping ground',
  'darwish purple valley','darwish exposed album','darwish pettra',
  'darwish rising dust','darwish twina','darwish azax','darwish shpongle',
  'darwish unite','darwish psy-fi','darwish indigo festival',
  'darwish boom festival','darwish doof','darwish sunrise set'
)

$before = (Get-ChildItem $dest -Filter *.mp3 -File -ErrorAction SilentlyContinue).Count
Write-Output "start $(Get-Date -Format 'HH:mm:ss')  corpus before: $before mp3"

$searches = $queries | ForEach-Object { "ytsearch40:$_" }

& yt-dlp @searches `
  --js-runtimes node `
  --match-filter "duration > 120" `
  --reject-title "(?i)(mahmoud|nonie|poem|poetry|sayed|quran|interview|lecture|sermon|ex.muslim)" `
  -x --audio-format mp3 `
  --download-archive .downloaded.txt `
  -o "%(upload_date>%Y)s - %(title)s.%(ext)s" `
  --no-playlist --ignore-errors --no-warnings `
  *>> _download_full.log

# Impostor filter: this artist's name is common. Anything that does not name
# Darwish or Deep Dave is moved aside rather than deleted - a wrong quarantine
# is recoverable, a wrong delete is not.
New-Item -ItemType Directory -Force _not-darwish | Out-Null
Get-ChildItem $dest -Filter *.mp3 -File | Where-Object { $_.Name -notmatch 'darwish|deep dave' } | ForEach-Object {
    try { Move-Item $_.FullName (Join-Path $dest '_not-darwish') -ErrorAction Stop
          Write-Output "QUARANTINED $($_.Name)" } catch { }
}

$after = (Get-ChildItem $dest -Filter *.mp3 -File -ErrorAction SilentlyContinue).Count
$gb = [math]::Round(((Get-ChildItem $dest -Filter *.mp3 -File | Measure-Object Length -Sum).Sum / 1GB), 2)
Write-Output "done $(Get-Date -Format 'HH:mm:ss')  corpus after: $after mp3 (+$($after - $before))  $gb GB"
Write-Output "SWEEP DONE"
