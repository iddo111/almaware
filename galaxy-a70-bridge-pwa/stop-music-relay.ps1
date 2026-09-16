$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$statePath = Join-Path $project '.runtime\music-relay-pids.json'

if (-not (Test-Path -LiteralPath $statePath)) {
    throw "No launcher state found at $statePath"
}
$state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
$targets = @(
    @{ Id = [int]$state.bridgePid; Marker = 'server.mjs'; Label = 'Node bridge'; Executable = [string]$state.bridgeExecutable },
    @{ Id = [int]$state.relayPid; Marker = 'music_relay.py'; Label = 'WASAPI relay'; Executable = $null }
)
if ($state.PSObject.Properties.Name -contains 'relayLauncherPid' -and [int]$state.relayLauncherPid -ne [int]$state.relayPid) {
    $targets += @{ Id = [int]$state.relayLauncherPid; Marker = 'music_relay.py'; Label = 'Python venv launcher'; Executable = [string]$state.relayExecutable }
}

foreach ($target in $targets) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($target.Id)" -ErrorAction SilentlyContinue
    if (-not $process) {
        Write-Output "$($target.Label) PID $($target.Id) is already stopped"
        continue
    }
    if ($process.CommandLine -notlike "*$($target.Marker)*") {
        throw "Refusing to stop PID $($target.Id): command line does not contain $($target.Marker)"
    }
    if ($target.Marker -eq 'music_relay.py' -and $process.CommandLine -notlike "*$project*") {
        throw "Refusing to stop PID $($target.Id): relay command line does not match this project"
    }
    if ($target.Executable -and $process.ExecutablePath -ne $target.Executable) {
        throw "Refusing to stop PID $($target.Id): executable does not match launcher state"
    }
    Stop-Process -Id $target.Id -Force
    Write-Output "Stopped $($target.Label) PID $($target.Id)"
}

Start-Sleep -Milliseconds 300
foreach ($port in @([int]$state.port, [int]$state.sidecarPort)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "A listener still owns launch port $port; state file retained for inspection"
    }
}
Remove-Item -LiteralPath $statePath
Write-Output 'Music relay stopped; logs remain in .runtime · הממסר נעצר והלוגים נשמרו'
