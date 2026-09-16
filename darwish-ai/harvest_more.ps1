# harvest_more.ps1 — expand the Darwish corpus. Iddo, 2026-08-20 09:06:
# "יש בעיה להוסיף דאטה - חפש ביוטיוב".
#
# THE BLOCKER WAS YOUTUBE, NOT US: the last sweep died on
#   ERROR: Sign in to confirm you're not a bot
# yt-dlp 2026.07.04 was stale; 2026.08.19 walks past it. Nothing else changed —
# no cookies, no account, no credentials touched.
#
# WHY MORE DATA: the lean-MIDI model memorised the corpus — 2.66M tokens seen
# 130 times (train ce 0.14, heldout 6.05, best 2.41 reached early then 8 hours of
# decay). A 24.8M-parameter model needs roughly two orders of magnitude more
# tokens than that. Every extra real Darwish set is the honest fix.
#
# The impostor filter stays: "Darwish" is a common name and the corpus must hold
# THIS artist only (Mahmoud Darwish the poet, sermons, interviews are rejected).

$dest = 'D:\Darwish'
New-Item -ItemType Directory -Force $dest | Out-Null
Set-Location $dest

# The original 31 queries plus new angles: labels, venues, collaborators, years,
# and the Hebrew spelling — each one a different corner of YouTube's index.
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
  'darwish boom festival','darwish doof','darwish sunrise set',
  # --- added 2026-08-20 ---
  'דרוויש טראנס','דרוויש סט','darwish hommega','darwish phantasm records',
  'darwish tesseractstudio','darwish iboga','darwish blacklite',
  'darwish dacru','darwish spin twist','darwish trancentral',
  'darwish morning set psytrance','darwish closing set','darwish opening set',
  'darwish b2b','darwish vs','darwish liquid soul','darwish ace ventura',
  'darwish astrix','darwish vini vici','darwish burn in noise',
  'darwish 2019 set','darwish 2020 set','darwish 2021 set','darwish 2022 set',
  'darwish 2023 set','darwish 2024 set','darwish 2025 set','darwish 2026 set',
  'darwish live at','darwish full set movie','darwish dj set full',
  'darwish progressive psytrance','darwish forest psytrance','darwish night set'
)

$before = (Get-ChildItem $dest -Filter *.mp3 -File -ErrorAction SilentlyContinue).Count
Write-Output "start $(Get-Date -Format 'HH:mm:ss')  corpus before: $before mp3  queries: $($queries.Count)"

$searches = $queries | ForEach-Object { "ytsearch40:$_" }

# 2026-08-20 09:20 — TIGHTENED after the first run poisoned the corpus. The old
# reject-list only knew about Mahmoud Darwish the poet. It let in:
#   * BASSEL DARWISH — an Argentinian minimal/deep-tech house DJ, 12 sets;
#   * other artists' sets at HIS festivals (Sub6 & Xerox @ Desert Adventure,
#     "Desert Adventure 2019 - The Freak Show"), pulled by my own festival
#     queries. A memorial model must learn HIS hands, not his festival's lineup.
# Two rules now: the title must NAME him, and the known impostors are rejected
# outright. (The tokenizer's split.json had independently excluded 18 such
# tracks — the training data was clean; this keeps the AUDIO clean too, so the
# next rebuild does not have to rediscover it.)
& yt-dlp @searches `
  --js-runtimes node `
  --match-filter "duration > 120 & title ~= (?i)darwish" `
  --reject-title "(?i)(bassel|mahmoud|nonie|poem|poetry|sayed|quran|interview|lecture|sermon|ex.muslim|crobar|elrow|mixmag|flaix|patagonia|deep tech|minimal)" `
  -x --audio-format mp3 `
  --download-archive .downloaded.txt `
  -o "%(upload_date>%Y)s - %(title)s.%(ext)s" `
  --no-playlist --ignore-errors --no-warnings `
  *>> _harvest_more.log

$after = (Get-ChildItem $dest -Filter *.mp3 -File -ErrorAction SilentlyContinue).Count
Write-Output "done  $(Get-Date -Format 'HH:mm:ss')  corpus after: $after mp3  (+$($after - $before))"
