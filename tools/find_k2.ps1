# find_k2.ps1 — never hardcode the K2 Plus IP again.
# The printer has no DHCP reservation, so its address moves (.222 -> .220 on 2026-08-15
# and that alone broke every saved link). This finds it by what it IS, not where it was.
#
#   . D:\CLAUDE\tools\find_k2.ps1            -> prints the IP
#   $ip = & D:\CLAUDE\tools\find_k2.ps1      -> use it in scripts
#
# Order: last-known cache -> hostname -> sweep the /24 for an open moonraker port.

param([switch]$Quiet)

$CacheFile = "$PSScriptRoot\.k2_last_ip"
$Port      = 7125            # moonraker
$Hostname  = "K2Plus-1708"

function Test-K2 {
    param([string]$ip)
    try {
        $r = Invoke-RestMethod "http://${ip}:${Port}/printer/info" -TimeoutSec 3 -ErrorAction Stop
        return ($r.result.hostname -like "K2*")
    } catch { return $false }
}

function Save-Ip { param([string]$ip) Set-Content -Path $CacheFile -Value $ip -Encoding ASCII }

# 1. last known good
if (Test-Path $CacheFile) {
    $cached = (Get-Content $CacheFile -Raw).Trim()
    if ($cached -and (Test-K2 $cached)) {
        if (-not $Quiet) { Write-Host "K2 at $cached (cached)" -ForegroundColor Green }
        return $cached
    }
}

# 2. by hostname
try {
    $resolved = [System.Net.Dns]::GetHostAddresses($Hostname) |
                Where-Object { $_.AddressFamily -eq 'InterNetwork' } |
                Select-Object -First 1 -ExpandProperty IPAddressToString
    if ($resolved -and (Test-K2 $resolved)) {
        Save-Ip $resolved
        if (-not $Quiet) { Write-Host "K2 at $resolved (hostname)" -ForegroundColor Green }
        return $resolved
    }
} catch { }

# 3. sweep the local /24 for an open moonraker port, then confirm it is the K2
$local = Get-NetIPAddress -AddressFamily IPv4 |
         Where-Object { $_.IPAddress -like "192.168.*" -and $_.PrefixOrigin -ne 'WellKnown' } |
         Select-Object -First 1 -ExpandProperty IPAddress
if ($local) {
    $prefix = ($local -split '\.')[0..2] -join '.'
    if (-not $Quiet) { Write-Host "sweeping $prefix.0/24 for moonraker..." -ForegroundColor DarkGray }
    $jobs = 2..254 | ForEach-Object {
        $ip = "$prefix.$_"
        Start-Job -ArgumentList $ip, $Port {
            param($ip, $port)
            if (Test-NetConnection -ComputerName $ip -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue) { $ip }
        }
    }
    $found = $jobs | Wait-Job -Timeout 40 | Receive-Job | Where-Object { $_ }
    $jobs | Remove-Job -Force -ErrorAction SilentlyContinue
    foreach ($cand in $found) {
        if (Test-K2 $cand) {
            Save-Ip $cand
            if (-not $Quiet) { Write-Host "K2 at $cand (swept)" -ForegroundColor Green }
            return $cand
        }
    }
}

if (-not $Quiet) { Write-Host "K2 NOT FOUND — printer off, or on another subnet." -ForegroundColor Red }
return $null
