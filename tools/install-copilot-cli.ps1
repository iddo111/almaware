# install-copilot-cli.ps1 — מתקין את GitHub Copilot CLI על הפיסי / installs GitHub Copilot CLI on the PC
# הרצה / run:  pwsh -File D:\CLAUDE\tools\install-copilot-cli.ps1
# מה הוא עושה / what it does:
#   1. בודק Node.js 22+ (Copilot CLI רץ על node)      / checks Node.js 22+
#   2. npm install -g @github/copilot  (או winget)     / installs (winget fallback)
#   3. מוודא שהפקודה copilot עובדת                     / verifies `copilot --version`
#   4. מפעיל copilot — אתה מקליד /login ומאשר בדפדפן  / launches copilot — YOU type /login
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

Write-Host "`n=== GitHub Copilot CLI installer ===`n"

# 1. Node.js 22+ ?
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Host "❌ אין Node.js / Node.js missing — installing via winget..."
    winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
}
$major = [int]((node --version).TrimStart("v").Split(".")[0])
if ($major -lt 22) { throw "Node.js $major is too old — need 22+. Run: winget upgrade OpenJS.NodeJS.LTS" }
Write-Host "✅ Node.js $(node --version)"

# 2. install / upgrade Copilot CLI
$have = Get-Command copilot -ErrorAction SilentlyContinue
if ($have) {
    Write-Host "ℹ️  copilot כבר מותקן / already installed — upgrading..."
}
npm install -g @github/copilot 2>&1 | Select-Object -Last 3
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️ npm failed — trying winget..."
    winget install --id GitHub.Copilot -e --accept-source-agreements --accept-package-agreements
}

# 3. verify
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
$ver = (& copilot --version) 2>&1
if ($LASTEXITCODE -ne 0) { throw "copilot did not start: $ver" }
Write-Host "✅ Copilot CLI $ver"

# 4. login is YOURS — device flow in the browser
Write-Host @"

הצעד האחרון שלך / your last step:
  copilot נפתח עכשיו. הקלד בפנים:   /login
  copilot opens now. Inside it type:  /login
  ואשר את הקוד בדפדפן (חשבון GitHub שלך, Copilot Free מספיק).
  approve the code in the browser (your GitHub account; Copilot Free is enough).
  יציאה / exit:  /exit
"@
if ($args -notcontains "-NoLaunch") { & copilot }
