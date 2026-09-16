# download_darwish.ps1 - daily 05:30 sweep: find + download EVERY new Darwish item,
# TWO FIXES 2026-08-14 (Iddo: "train on the entire darwish corpus"):
#  1. --js-runtimes node. YouTube now requires solving a JS signature challenge;
#     without a runtime every media URL comes back unsigned and yt-dlp gets a
#     bare "HTTP Error 403: Forbidden" on EVERY item. Node v24 is installed.
#     Symptom to recognise: the run looks alive, downloads nothing, and the
#     real cause is a WARNING scrolling past, not the ERROR line.
#  2. the "duration > 3600" filter is GONE. A catalogue survey of 31 queries
#     found 338 unique Darwish items / 106.5 hours; the >1h rule kept 42 and
#     THREW AWAY 296 items and 42.2 hours - every single track and short mix.
#     Lower bound is now 120s, which only drops clips and teasers.
# quarantine files that do not name the artist. Feeds the 06:00 sync.
$ErrorActionPreference = 'Continue'
Set-Location D:\Darwish
yt-dlp "ytsearch40:darwish psytrance set" "ytsearch40:darwish desert adventure" `
  "ytsearch40:dj darwish goa trance" "ytsearch40:darwish live set trance" `
  "ytsearch40:darwish ozora" `
  --js-runtimes node `
  --match-filter "duration > 120" `
  --reject-title "(?i)(mahmoud|nonie|poem|poetry|sayed|quran|interview|lecture|sermon|ex.muslim|bassel)" `
  -x --audio-format mp3 --download-archive .downloaded.txt `
  -o "%(upload_date>%Y)s - %(title)s.%(ext)s" --no-playlist --ignore-errors *>> _download.log

New-Item -ItemType Directory -Force _not-darwish | Out-Null
# bassel = Bassel Darwish, a different artist entirely (found in the corpus 2026-08-17)
Get-ChildItem *.mp3 | Where-Object { $_.Name -notmatch 'darwish|deep dave' -or $_.Name -match 'bassel|logo scandal|rush darwish' } | ForEach-Object {
    try { Move-Item $_.FullName _not-darwish\ -ErrorAction Stop; Write-Host "QUARANTINED $($_.Name)" }
    catch { }
}
Write-Host ("clean corpus: " + (Get-ChildItem *.mp3).Count + " files")
