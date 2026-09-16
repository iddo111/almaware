# Pulls every throat-search worker's best.wav (eran2/3/4) to eran1:~/eran-search-live/
# so the listen page (eran1:8807) plays ERAN's freshest own-mouth attempts.
# Runs from the PC (the only box with keys to all four). Scheduled every 5 min.
# NOTE: no binary through the PowerShell pipeline (it corrupts) - remote tar
# file + scp instead.
$ErrorActionPreference = "SilentlyContinue"
$tmp = Join-Path $env:TEMP "eran-search-live"
Remove-Item -Recurse -Force $tmp; New-Item -ItemType Directory -Force $tmp | Out-Null
$boxes = @(
    @{ h = "eran2"; n = "eran2" },
    @{ h = "eran3"; n = "eran3" },
    @{ h = "eran4@<lan-ip>"; n = "eran4" }
)
foreach ($b in $boxes) {
    $sub = Join-Path $tmp $b.n
    New-Item -ItemType Directory -Force $sub | Out-Null
    ssh $b.h "cd ~/throat-search/run 2>/dev/null && tar cf /tmp/best-sync.tar */best.wav 2>/dev/null; true"
    scp -q "$($b.h):/tmp/best-sync.tar" (Join-Path $sub "best.tar")
    if (Test-Path (Join-Path $sub "best.tar")) {
        tar xf (Join-Path $sub "best.tar") -C $sub
        Get-ChildItem $sub -Recurse -Filter best.wav | ForEach-Object {
            $worker = $_.Directory.Name
            Move-Item $_.FullName (Join-Path $tmp ("LIVE-" + $b.n + "-" + $worker + ".wav")) -Force
        }
    }
    Remove-Item -Recurse -Force $sub
}
$wavs = Get-ChildItem $tmp -Filter "LIVE-*.wav"
if ($wavs) {
    ssh eran1 "mkdir -p ~/eran-search-live"
    scp -q (Join-Path $tmp "LIVE-*.wav") "eran1:~/eran-search-live/" 2>$null
    "synced $($wavs.Count) best.wav files to eran1 at $(Get-Date -Format HH:mm:ss)"
} else {
    "no best.wav found on any box"
}
