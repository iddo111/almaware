# push.ps1 — PC -> eran1 sync for Perceptron Mark II.
# Pushes the code and the corpus. HELDOUT goes ONLY to the examiner's vault
# (proof/heldout-vault/) — never to food/ — and ears.py refuses to eat it.
# Pinned LAN host 'eran1' from ~/.ssh/config; BatchMode so it never hangs.
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot          # D:\CLAUDE\eran-brain
$Corpus = "D:\CLAUDE\voice-ant-farm\corpus-syllables"
$SshOpts = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=10")

Write-Host "[push] creating remote tree..."
ssh @SshOpts eran1 "mkdir -p ~/eran-brain/food/train ~/eran-brain/food/words ~/eran-brain/proof/heldout-vault ~/eran-brain/state ~/eran-brain/feedback/inbox ~/eran-brain/songs/outbox ~/eran-brain/results"

Write-Host "[push] code..."
scp @SshOpts -r `
    (Join-Path $RepoRoot "body") `
    (Join-Path $RepoRoot "proof") `
    (Join-Path $RepoRoot "serve") `
    (Join-Path $RepoRoot "voice") `
    (Join-Path $RepoRoot "deploy") `
    (Join-Path $RepoRoot "eran_life.py") `
    (Join-Path $RepoRoot "tournament.py") `
    (Join-Path $RepoRoot "ORGANISM.md") `
    "eran1:~/eran-brain/"

Write-Host "[push] corpus: train + words -> food/  (NEVER heldout)..."
scp @SshOpts -r "$Corpus\train\*.wav" "eran1:~/eran-brain/food/train/"
scp @SshOpts -r "$Corpus\words\*.wav" "eran1:~/eran-brain/food/words/"

Write-Host "[push] heldout -> the examiner's VAULT (exam-only; ears refuse it in life)..."
scp @SshOpts -r "$Corpus\heldout\*.wav" "eran1:~/eran-brain/proof/heldout-vault/"

Write-Host "[push] counts on the box:"
ssh @SshOpts eran1 "echo train: `$(ls ~/eran-brain/food/train | wc -l); echo words: `$(ls ~/eran-brain/food/words | wc -l); echo heldout-vault: `$(ls ~/eran-brain/proof/heldout-vault/*.wav | wc -l)"

Write-Host "[push] done. On the box: cd ~/eran-brain && python3 proof/test_organism.py && bash deploy/install.sh"
