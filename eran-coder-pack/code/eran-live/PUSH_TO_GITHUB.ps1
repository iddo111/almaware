# =====================================================================
#  PUSH_TO_GITHUB.ps1  --  publish ERAN to a PRIVATE GitHub repo
# ---------------------------------------------------------------------
#  Eran's data is derived from Iddo's VOICE. It is personal.
#  This repo MUST be PRIVATE. This script enforces that and refuses
#  to continue if anything looks public.
#
#  ONE-TIME prerequisite (Iddo runs this himself, it needs a browser):
#       gh auth login
#
#  Then just run:
#       powershell -ExecutionPolicy Bypass -File D:\CLAUDE\eran-live\PUSH_TO_GITHUB.ps1
# =====================================================================

$ErrorActionPreference = 'Stop'
$RepoDir  = 'D:\CLAUDE\eran-live'
$RepoName = 'almaware-eran'

function Fail($msg) {
    Write-Host ""
    Write-Host "  X  $msg" -ForegroundColor Red
    Write-Host ""
    exit 1
}
function Ok($msg)   { Write-Host "  OK $msg" -ForegroundColor Green }
function Info($msg) { Write-Host "  -> $msg" -ForegroundColor Cyan }

Write-Host ""
Write-Host "===== ERAN -> PRIVATE GitHub push =====" -ForegroundColor White
Write-Host ""

# --- 0. tools present ---
if (-not (Get-Command gh  -ErrorAction SilentlyContinue)) { Fail "GitHub CLI 'gh' not found. Install it, then run: gh auth login" }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail "git not found on PATH." }
if (-not (Test-Path $RepoDir)) { Fail "Repo dir not found: $RepoDir" }

# --- 1. gh must be authenticated ---
Info "Checking 'gh auth status'..."
gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail "gh is NOT authenticated. Run:  gh auth login   then re-run this script."
}
$ghUser = (gh api user --jq '.login' 2>$null)
if (-not $ghUser) { Fail "Could not read your GitHub username from gh. Run: gh auth login" }
Ok "Authenticated as GitHub user: $ghUser"

$fullName = "$ghUser/$RepoName"

# --- 2. create the repo PRIVATE (or reuse it, but only if already private) ---
Info "Checking whether $fullName already exists..."
$exists = $true
gh repo view $fullName 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { $exists = $false }

if (-not $exists) {
    Info "Creating PRIVATE repo $fullName ..."
    gh repo create $fullName --private --description "ERAN - a byte-level LM grown from zero, learning ONLY from Iddo's voice (PRIVATE: voice-derived data)" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "Failed to create repo $fullName." }
    Ok "Created PRIVATE repo $fullName"
} else {
    Ok "Repo $fullName already exists; will reuse it."
}

# --- 3. HARD SAFETY GATE: verify the repo is actually PRIVATE ---
Info "Verifying repo visibility is PRIVATE..."
$isPrivate = (gh repo view $fullName --json isPrivate --jq '.isPrivate' 2>$null)
if ($isPrivate -ne 'true') {
    Fail "REFUSING TO PUSH: $fullName is NOT private (isPrivate=$isPrivate). Voice data must never be public. Make it private in GitHub settings, then re-run."
}
Ok "Confirmed PRIVATE."

# --- 4. wire up the remote ---
$remoteUrl = "https://github.com/$fullName.git"
$haveOrigin = $true
git -C $RepoDir remote get-url origin 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { $haveOrigin = $false }

if ($haveOrigin) {
    Info "Updating existing 'origin' remote -> $remoteUrl"
    git -C $RepoDir remote set-url origin $remoteUrl
} else {
    Info "Adding 'origin' remote -> $remoteUrl"
    git -C $RepoDir remote add origin $remoteUrl
}

# --- 5. make sure we are on main and have a commit ---
$branch = (git -C $RepoDir rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'main') {
    Info "Current branch is '$branch'; switching/renaming to 'main'..."
    git -C $RepoDir branch -M main
}

# stage anything new (e.g. updated checkpoint) so the push is current
git -C $RepoDir add -A
$dirty = (git -C $RepoDir status --porcelain)
if ($dirty) {
    Info "Committing pending changes before push..."
    git -C $RepoDir commit -m "ERAN: sync before first push (README + push script + latest checkpoint)" | Out-Null
    Ok "Committed."
} else {
    Ok "Working tree clean; nothing extra to commit."
}

# --- 6. push ---
Info "Pushing 'main' to $fullName ..."
git -C $RepoDir push -u origin main
if ($LASTEXITCODE -ne 0) { Fail "git push failed. Check the output above." }

Write-Host ""
Ok "DONE. Eran is now on PRIVATE GitHub:"
Write-Host "     https://github.com/$fullName" -ForegroundColor White
Write-Host ""
Write-Host "  Reminder: keep this repo PRIVATE. It contains a model trained on your voice." -ForegroundColor Yellow
Write-Host ""
