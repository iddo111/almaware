# pull_samples.ps1 - daily: pull new generated samples from eran4 to D:\Darwish\generated
# 2026-08-17: retargeted eran3 -> eran4 (Darwish migrated 08-15).
$ErrorActionPreference = 'Continue'
$remote = 'eran4'
$dst = 'D:\Darwish\generated'
New-Item -ItemType Directory -Force $dst | Out-Null
$names = ssh -o BatchMode=yes $remote "ls ~/darwish-ai/generated/*.mp3 2>/dev/null | xargs -n1 basename" 2>$null
foreach ($n in $names) {
    if ($n -and -not (Test-Path (Join-Path $dst $n))) {
        Write-Host "PULL $n"
        scp -o BatchMode=yes -q "${remote}:~/darwish-ai/generated/$n" $dst
    }
}
Write-Host 'done.'
