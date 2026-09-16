# vnc-a70.ps1 — Open VNC tunnel to A70 and launch viewer
# Usage: powershell -ExecutionPolicy Bypass -File vnc-a70.ps1

param(
    [string]$Viewer = "C:\Program Files\TigerVNC\vncviewer.exe",
    [string]$A70TailscaleIP = "<tailnet-ip>",
    [int]$VNCDisplay = 1    # display :1 → port 5901
)

$vncPort = 5900 + $VNCDisplay
Write-Host "Opening SSH tunnel: localhost:$vncPort → A70:$vncPort ..."

$sshArgs = "-p 8022 -L ${vncPort}:localhost:${vncPort} -N -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -i $HOME\.ssh\id_ed25519 u0_a688@$A70TailscaleIP"
$tunnel = Start-Process -PassThru -NoNewWindow -FilePath "ssh" -ArgumentList $sshArgs

Start-Sleep -Seconds 2

if (-not (Test-Path $Viewer)) {
    Write-Warning "TigerVNC viewer not found at $Viewer"
    Write-Host "Download from: https://tigervnc.org/doc/vncviewer.html"
    Write-Host "Or install via: winget install TigerVNC.TigerVNC"
    Write-Host ""
    Write-Host "Tunnel is open on localhost:$vncPort — use any VNC client."
} else {
    Write-Host "Launching VNC viewer → localhost:$vncPort"
    Start-Process -FilePath $Viewer -ArgumentList "localhost:$vncPort"
}

Write-Host "Press Enter to close the SSH tunnel..."
Read-Host
if ($tunnel -and !$tunnel.HasExited) {
    Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "Tunnel closed."
