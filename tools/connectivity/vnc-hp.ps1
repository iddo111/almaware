# vnc-hp.ps1 — Open VNC tunnel to HP Pavilion Linux and launch viewer
# Usage: powershell -ExecutionPolicy Bypass -File vnc-hp.ps1
#        powershell -ExecutionPolicy Bypass -File vnc-hp.ps1 -HPTailscaleIP 100.x.x.x

param(
    [string]$HPTailscaleIP = "REPLACE_WITH_HP_TAILSCALE_IP",
    [string]$Viewer = "C:\Program Files\TigerVNC\vncviewer.exe",
    [int]$RemoteVNCPort = 5900,    # 5900 for x11vnc, 5902 for TigerVNC display :2
    [int]$LocalPort = 5910         # local port (different from A70's 5901 to avoid conflict)
)

if ($HPTailscaleIP -eq "REPLACE_WITH_HP_TAILSCALE_IP") {
    Write-Error "Set -HPTailscaleIP to your HP Pavilion's Tailscale IP (run 'tailscale ip' on HP Pavilion)"
    exit 1
}

Write-Host "Opening SSH tunnel: localhost:$LocalPort → HP Pavilion:$RemoteVNCPort ..."

$sshArgs = "-L ${LocalPort}:localhost:${RemoteVNCPort} -N -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -i $HOME\.ssh\id_ed25519 iddo@$HPTailscaleIP"
$tunnel = Start-Process -PassThru -NoNewWindow -FilePath "ssh" -ArgumentList $sshArgs

Start-Sleep -Seconds 2

if (-not (Test-Path $Viewer)) {
    Write-Warning "TigerVNC viewer not found at $Viewer"
    Write-Host "Download from: https://tigervnc.org/doc/vncviewer.html"
    Write-Host "Or install via: winget install TigerVNC.TigerVNC"
    Write-Host ""
    Write-Host "Tunnel is open on localhost:$LocalPort — use any VNC client."
} else {
    Write-Host "Launching VNC viewer → localhost:$LocalPort"
    Start-Process -FilePath $Viewer -ArgumentList "localhost:$LocalPort"
}

Write-Host "Press Enter to close the SSH tunnel..."
Read-Host
if ($tunnel -and !$tunnel.HasExited) {
    Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "Tunnel closed."
