$ErrorActionPreference = 'Stop'

$ssh = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
$arguments = @(
    '-N',
    '-o', 'BatchMode=yes',
    '-o', 'ExitOnForwardFailure=yes',
    '-o', 'ServerAliveInterval=30',
    '-o', 'ServerAliveCountMax=3',
    '-L', '127.0.0.1:11436:127.0.0.1:11435',
    'eran1@<lan-ip>'
)

function Test-LocalPort([int]$Port) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync([Net.IPAddress]::Loopback, $Port)
        return $task.Wait(750) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

if (-not (Test-LocalPort 11436)) {
    Start-Process -FilePath $ssh -ArgumentList $arguments -WindowStyle Hidden
}
