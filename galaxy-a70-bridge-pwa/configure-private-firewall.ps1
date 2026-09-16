param(
    [Parameter(Mandatory)][string]$ListenAddress,
    [ValidateRange(1024, 65535)][int]$Port = 4173,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$node = (Get-Command node -ErrorAction Stop).Source
$venvPython = Join-Path $project '.venv\Scripts\python.exe'
$parsedAddress = $null

if (-not [Net.IPAddress]::TryParse($ListenAddress, [ref]$parsedAddress) -or $parsedAddress.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
    throw 'ListenAddress must be one explicit IPv4 address'
}
if ($ListenAddress -eq '0.0.0.0' -or $ListenAddress -like '127.*') {
    throw 'Wildcard and loopback addresses are not valid phone-facing firewall scopes'
}
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Run setup-music-relay.ps1 first' }
$python = (& $venvPython -c "import sys; print(sys._base_executable)").Trim()
if (-not (Test-Path -LiteralPath $python)) { throw "Resolved Python runtime does not exist: $python" }

$tcpName = 'ALMA A70 Music Relay TCP Private LAN'
$udpName = 'ALMA A70 Music Relay WebRTC UDP Private LAN'
Write-Host 'Proposed scope only · תחום מוצע בלבד:'
Write-Host "  TCP $Port; program=$node; local=$ListenAddress; remote=LocalSubnet; profile=Private"
Write-Host "  UDP dynamic; program=$python; local=$ListenAddress; remote=LocalSubnet; profile=Private"

if (-not $Apply) {
    Write-Host 'DRY RUN: no firewall state changed. Add -Apply from an elevated PowerShell to create these two rules.' -ForegroundColor Yellow
    exit 0
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run elevated only after reviewing the dry-run scope'
}

if (-not (Get-NetFirewallRule -DisplayName $tcpName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $tcpName -Direction Inbound -Action Allow -Enabled True `
        -Profile Private -Program $node -Protocol TCP -LocalPort $Port `
        -LocalAddress $ListenAddress -RemoteAddress LocalSubnet | Out-Null
}
if (-not (Get-NetFirewallRule -DisplayName $udpName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $udpName -Direction Inbound -Action Allow -Enabled True `
        -Profile Private -Program $python -Protocol UDP -LocalPort Any `
        -LocalAddress $ListenAddress -RemoteAddress LocalSubnet | Out-Null
}

Write-Host 'Narrow Private/LocalSubnet rules created. Roll back with:' -ForegroundColor Green
Write-Host "Remove-NetFirewallRule -DisplayName '$tcpName','$udpName'"
