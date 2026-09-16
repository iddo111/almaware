# sync_corpus.ps1 — hash D:\Darwish\*.mp3, build manifest, scp only missing files to eran4.
# Broken Windows law: acceptance is du -sh on eran4, not this script exiting 0.
# 2026-08-17: retargeted eran3 -> eran4 (Darwish migrated 08-15; this script was
# still pointing at eran3, which also has no internet, and the task sat disabled -
# 40+ swept files were stranded on the PC while the trainer starved).
$ErrorActionPreference = 'Stop'
$remote = 'eran4'
$srcDir = 'D:\Darwish'
$manifest = @()

$remoteHashes = ssh -o BatchMode=yes $remote "cd ~/darwish-ai/corpus 2>/dev/null && sha256sum *.mp3 2>/dev/null" | ForEach-Object { ($_ -split '\s+',2)[0] }
$remoteSet = @{}; $remoteHashes | ForEach-Object { if ($_) { $remoteSet[$_] = $true } }

Get-ChildItem "$srcDir\*.mp3" | ForEach-Object {
    # Corpus purity: the searches also catch OTHER artists playing his festivals.
    # Only files naming the artist himself may feed the brain. 'Bassel Darwish'
    # is a DIFFERENT artist (Barcelona minimal/deep tech) that passes the name
    # test - 8 of his sets reached the corpus before 2026-08-17. Blocked by name.
    if ($_.Name -notmatch 'darwish|deep dave' -or $_.Name -match 'bassel|logo scandal|rush darwish') {
        Write-Host "IMPOSTOR  $($_.Name) (not synced - quarantine candidate)"; return
    }
    # yt-dlp may still be writing this file - skip locked files, next run picks them up
    try { $h = (Get-FileHash $_.FullName -Algorithm SHA256 -ErrorAction Stop).Hash.ToLower() }
    catch { Write-Host "BUSY  $($_.Name) (still downloading - skipped)"; return }
    $manifest += [pscustomobject]@{ name = $_.Name; bytes = $_.Length; sha256 = $h }
    if (-not $remoteSet.ContainsKey($h)) {
        Write-Host "SYNC  $($_.Name)  ($([math]::Round($_.Length/1MB)) MB)"
        scp -o BatchMode=yes -q "$($_.FullName)" "${remote}:~/darwish-ai/corpus/"
    } else {
        Write-Host "SKIP  $($_.Name) (already on eran4)"
    }
}

$manifest | ConvertTo-Json | Out-File "$srcDir\corpus_manifest.json" -Encoding utf8
scp -o BatchMode=yes -q "$srcDir\corpus_manifest.json" "${remote}:~/darwish-ai/corpus/"
Write-Host '--- remote state:'
ssh -o BatchMode=yes $remote "ls ~/darwish-ai/corpus | wc -l; du -sh ~/darwish-ai/corpus"
