$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sshExe = 'C:\Windows\System32\OpenSSH\ssh.exe'
$sshKey = 'C:\Users\<user>\.ssh\id_ed25519'

$listener = Get-NetTCPConnection -State Listen -LocalPort 11435 -ErrorAction SilentlyContinue
if (-not $listener) {
    $arguments = @(
        '-N', '-T',
        '-L', '127.0.0.1:11435:127.0.0.1:11434',
        '-i', $sshKey,
        '-o', 'BatchMode=yes',
        '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ServerAliveInterval=20',
        '-o', 'ServerAliveCountMax=3',
        'eran1@<lan-ip>'
    )
    Start-Process -FilePath $sshExe -ArgumentList $arguments -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

if (-not (Get-NetTCPConnection -State Listen -LocalPort 11435 -ErrorAction SilentlyContinue)) {
    throw 'GPT-OSS tunnel failed to listen on 127.0.0.1:11435'
}

# No environment flag can unlock training. server.py owns the fail-closed
# native-tensor acceptance gate.
Remove-Item Env:GPTOSS_ENABLE_TRAINING -ErrorAction SilentlyContinue
$env:GPTOSS_GUI_PORT = '8766'
Set-Location $projectRoot
python server.py
