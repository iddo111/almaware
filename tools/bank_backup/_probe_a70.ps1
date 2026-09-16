# Probe Samsung A70 on the LAN: try known IPs, then arp-scan.
# Returns 0 with IP on stdout if found and reachable on port 8022 (Termux sshd).
# Returns 1 with "OFFLINE" on stdout if unreachable.
# ASCII only, no em-dashes.
$ErrorActionPreference = 'SilentlyContinue'

$candidates = @('<lan-ip>','<lan-ip>','<lan-ip>','<lan-ip>','<lan-ip>')

# First, try mDNS broadcast resolution
$mdns = 'android.local','samsung.local','a70.local'
foreach ($n in $mdns) {
    $r = Resolve-DnsName $n -ErrorAction SilentlyContinue | Where-Object { $_.IP4Address } | Select-Object -First 1
    if ($r) { $candidates = @($r.IP4Address) + $candidates }
}

foreach ($ip in $candidates) {
    $ping = Test-Connection -ComputerName $ip -Count 1 -Quiet -TimeoutSeconds 1
    if (-not $ping) { continue }
    # ping ok - try port 8022
    $tcp = Test-NetConnection -ComputerName $ip -Port 8022 -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($tcp) {
        Write-Output $ip
        exit 0
    }
}

# Last-ditch: ARP scan via ping sweep
$sweep = @()
1..254 | ForEach-Object {
    $ip = "192.168.1.$_"
    $sweep += Start-Job -ScriptBlock {
        param($i)
        if (Test-Connection -ComputerName $i -Count 1 -Quiet -TimeoutSeconds 1) {
            try {
                $t = Test-NetConnection -ComputerName $i -Port 8022 -InformationLevel Quiet -WarningAction SilentlyContinue
                if ($t) { return $i }
            } catch {}
        }
    } -ArgumentList $ip
}
$sweep | Wait-Job -Timeout 10 | Out-Null
foreach ($j in $sweep) {
    $r = Receive-Job $j -ErrorAction SilentlyContinue
    if ($r) {
        Write-Output $r
        Remove-Job $sweep -Force -ErrorAction SilentlyContinue | Out-Null
        exit 0
    }
}
Remove-Job $sweep -Force -ErrorAction SilentlyContinue | Out-Null

Write-Output 'OFFLINE'
exit 1
