# pull_songs.ps1 — scp the newest Chai songs from eran4 down to the PC.
# PINNED address per standing order: bare `ssh eran4` resolves ambiguously
# (LAN vs the eran2-jumped Tailscale alias) — this script always targets the
# plain-LAN address directly: <lan-ip>.
#
# Dedup by filename: an existing file on the PC is never re-copied.
# Sacred Audio law respected: this script never plays, opens, or touches any
# audio device — it only copies files to disk.

param(
    [string]$Eran4 = "<lan-ip>",
    [string]$User = "eran4",
    [string]$RemoteOutbox = "~/darwish-midi/songs/outbox",
    [string]$DestDir = "D:\Darwish\generated-midi-alive",
    [int]$Newest = 20
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $DestDir)) {
    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
}

$remote = "$User@$Eran4"

# List remote outbox, newest-first by name (song_id carries a sortable
# yyyymmdd-HHMMSS stamp), take the newest N triplets (.mid/.wav/.trace.json).
$listCmd = "ls -1t $RemoteOutbox 2>/dev/null | head -n $($Newest * 4)"
$remoteFiles = & ssh -o BatchMode=yes -o ConnectTimeout=10 $remote $listCmd
if ($LASTEXITCODE -ne 0) {
    Write-Error "ssh to $remote failed (exit $LASTEXITCODE) — is eran4 reachable at $Eran4?"
    exit 1
}

$remoteFiles = $remoteFiles | Where-Object { $_ -and $_.Trim() -ne "" }
if (-not $remoteFiles) {
    Write-Host "no songs found in $remote`:$RemoteOutbox"
    exit 0
}

$pulled = 0
$skipped = 0
foreach ($name in $remoteFiles) {
    $name = $name.Trim()
    $localPath = Join-Path $DestDir $name
    if (Test-Path $localPath) {
        $skipped++
        continue
    }
    $remotePath = "${remote}:$RemoteOutbox/$name"
    & scp -o BatchMode=yes -o ConnectTimeout=10 $remotePath $localPath 2>$null
    if ($LASTEXITCODE -eq 0 -and (Test-Path $localPath)) {
        $pulled++
        Write-Host "pulled: $name"
    } else {
        Write-Host "FAILED: $name (scp exit $LASTEXITCODE)"
    }
}

Write-Host ""
Write-Host "done: $pulled pulled, $skipped already present, dest = $DestDir"
Write-Host "(files wait for Iddo — no autoplay, nothing opened for him automatically)"
