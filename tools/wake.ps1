# wake.ps1 — Wake-on-LAN magic packet sender
# Usage:  pwsh D:\CLAUDE\tools\wake.ps1 PC
#         pwsh D:\CLAUDE\tools\wake.ps1 DGX
#         pwsh D:\CLAUDE\tools\wake.ps1 10-7B-44-1B-5B-85
#
# Known machines (edit MACs here as you add them):
$Known = @{
  'PC'  = '10-7B-44-1B-5B-85'   # This desktop, Intel I219-V, <lan-ip>
  'DGX' = 'FILL-IN-DGX-MAC'     # <-- run  ip link  on the DGX and paste its ether address
}

$target = $args[0]
if (-not $target) { Write-Host "Usage: wake.ps1 <PC|DGX|MAC>"; exit 1 }

$mac = if ($Known.ContainsKey($target)) { $Known[$target] } else { $target }
$hex = $mac -replace '[:\-\.]',''
if ($hex.Length -ne 12) { Write-Host "Bad MAC: $mac"; exit 1 }
$bytes = for ($i=0; $i -lt 12; $i+=2) { [Convert]::ToByte($hex.Substring($i,2),16) }

# Magic packet = 6x 0xFF  +  16x MAC
$packet = ([byte[]](,0xFF*6)) + ($bytes*16)

$udp = New-Object System.Net.Sockets.UdpClient
$udp.EnableBroadcast = $true
# send to the subnet broadcast on ports 9 and 7
foreach ($port in 9,7) {
  $udp.Connect(([System.Net.IPAddress]::Broadcast), $port)
  [void]$udp.Send($packet, $packet.Length)
}
$udp.Close()
Write-Host "Magic packet sent to $mac ($target) on ports 9 & 7."
