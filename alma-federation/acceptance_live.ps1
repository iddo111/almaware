param(
    [ValidateSet('Start', 'Status', 'Probe', 'Stop')]
    [string]$Action = 'Start',
    [string]$RuntimeDir = 'D:\CLAUDE\_codex\fleet-supervision\federation-live-current',
    [int]$Port = 18900
)

$ErrorActionPreference = 'Stop'
$python = 'C:\Users\<user>\AppData\Local\Programs\Python\Python313\python.exe'
$source = Split-Path -Parent $MyInvocation.MyCommand.Path
$tokenPath = Join-Path $source '.alma_token'
$manifestPath = Join-Path $RuntimeDir 'runtime.json'

function Get-EnrollmentToken {
    $value = (Get-Content -Raw -LiteralPath $tokenPath).Trim()
    if ($value.Length -lt 24 -or $value.ToLowerInvariant() -eq 'alma') {
        throw 'Strong token validation failed'
    }
    return $value
}

function Get-Manifest {
    if (-not (Test-Path -LiteralPath $manifestPath)) { return $null }
    return Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
}

function Get-RuntimeStatus {
    $manifest = Get-Manifest
    if ($null -eq $manifest) {
        return [pscustomobject]@{ running = $false; reason = 'no manifest'; runtime_dir = $RuntimeDir }
    }
    $coordinator = Get-Process -Id $manifest.coordinator_pid -ErrorAction SilentlyContinue
    $worker = Get-Process -Id $manifest.worker_pid -ErrorAction SilentlyContinue
    $listening = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort $Port -ErrorAction SilentlyContinue
    return [pscustomobject]@{
        running = [bool]($coordinator -and $worker -and $listening)
        coordinator_pid = $manifest.coordinator_pid
        worker_pid = $manifest.worker_pid
        bind = '127.0.0.1'
        port = $Port
        runtime_dir = $RuntimeDir
    }
}

function Start-FederationProcess {
    param(
        [hashtable]$Environment,
        [string]$Script,
        [string]$StandardOutput,
        [string]$StandardError
    )

    # Windows PowerShell 5.1 has no Start-Process -Environment. Temporarily
    # populate the parent process environment so the child inherits it, then
    # restore every value immediately after process creation.
    $previous = @{}
    foreach ($entry in $Environment.GetEnumerator()) {
        $previous[$entry.Key] = [Environment]::GetEnvironmentVariable($entry.Key, 'Process')
    }
    try {
        foreach ($entry in $Environment.GetEnumerator()) {
            Set-Item -Path ("Env:" + $entry.Key) -Value $entry.Value
        }
        return Start-Process -FilePath $python -ArgumentList @('-B', $Script) `
            -WorkingDirectory $source -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $StandardOutput `
            -RedirectStandardError $StandardError
    } finally {
        foreach ($entry in $Environment.GetEnumerator()) {
            $value = $previous[$entry.Key]
            if ($null -eq $value) {
                Remove-Item -Path ("Env:" + $entry.Key) -ErrorAction SilentlyContinue
            } else {
                Set-Item -Path ("Env:" + $entry.Key) -Value $value
            }
        }
    }
}

if ($Action -eq 'Status') {
    Get-RuntimeStatus | ConvertTo-Json -Depth 5
    exit 0
}

if ($Action -eq 'Stop') {
    $manifest = Get-Manifest
    if ($null -ne $manifest) {
        foreach ($pidValue in @($manifest.worker_pid, $manifest.coordinator_pid)) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
            if ($process -and $process.ExecutablePath -eq $python -and
                $process.CommandLine -match '(worker|coordinator)\.py') {
                Stop-Process -Id $pidValue -ErrorAction SilentlyContinue
            }
        }
    }
    Get-RuntimeStatus | ConvertTo-Json -Depth 5
    exit 0
}

if ($Action -eq 'Probe') {
    $status = Get-RuntimeStatus
    if (-not $status.running) { throw 'Federation acceptance runtime is not running' }
    $token = Get-EnrollmentToken
    $headers = @{ 'X-Alma-Token' = $token }

    function Submit-And-Wait([hashtable]$Task) {
        $payload = @{ task = $Task } | ConvertTo-Json -Depth 8 -Compress
        $submitted = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/submit" -Method Post `
            -Headers $headers -ContentType 'application/json' -Body $payload -TimeoutSec 5
        $deadline = (Get-Date).AddSeconds(20)
        do {
            Start-Sleep -Milliseconds 250
            $result = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/result/$($submitted.job_id)" `
                -Headers $headers -TimeoutSec 5
        } until ($result.status -eq 'done' -or (Get-Date) -gt $deadline)
        if ($result.status -ne 'done') { throw "Job did not finish: $($submitted.job_id)" }
        return $result
    }

    function Rejected-Status([string]$Body, [bool]$Authorized) {
        $requestHeaders = @{}
        if ($Authorized) { $requestHeaders['X-Alma-Token'] = $token }
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/submit" -Method Post `
                -Headers $requestHeaders -ContentType 'application/json' -Body $Body -TimeoutSec 3 | Out-Null
            return 200
        } catch {
            return [int]$_.Exception.Response.StatusCode
        }
    }

    $echo = Submit-And-Wait @{ kind = 'diagnostic.echo'; message = 'FEDERATION_ECHO_OK_20260720' }
    $systemInfo = Submit-And-Wait @{ kind = 'system.info' }
    $pythonVersion = Submit-And-Wait @{ kind = 'python.version' }
    $unauthorized = 0
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/status" -TimeoutSec 3 | Out-Null
        $unauthorized = 200
    } catch {
        $unauthorized = [int]$_.Exception.Response.StatusCode
    }

    [pscustomobject]@{
        runtime = $status
        worker_online = ((Invoke-RestMethod -Uri "http://127.0.0.1:$Port/status" -Headers $headers -TimeoutSec 3).online -contains 'codex-acceptance-worker')
        token_length = $token.Length
        execution_mode = 'bounded-allowlist'
        shell = $false
        echo_status = $echo.status
        echo_rc = $echo.rc
        echo_output = $echo.output
        system_info_status = $systemInfo.status
        system_info_rc = $systemInfo.rc
        system_info_nonempty = [bool]$systemInfo.output
        python_version_status = $pythonVersion.status
        python_version_rc = $pythonVersion.rc
        python_version_output = $pythonVersion.output
        unauthorized_http = $unauthorized
        legacy_cmd_http = (Rejected-Status '{"cmd":"whoami"}' $true)
        unknown_task_http = (Rejected-Status '{"task":{"kind":"process","argv":["cmd.exe","/c","whoami"]}}' $true)
    } | ConvertTo-Json -Depth 8
    exit 0
}

$existing = Get-RuntimeStatus
if ($existing.running) {
    $existing | ConvertTo-Json -Depth 5
    exit 0
}

if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already occupied"
}

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
$token = Get-EnrollmentToken
$coordinatorEnvironment = @{
    ALMA_TOKEN = $token
    ALMA_BIND = '127.0.0.1'
    ALMA_PORT = [string]$Port
    ALMA_STATE = (Join-Path $RuntimeDir 'state.json')
    PYTHONUNBUFFERED = '1'
}
$coordinator = Start-FederationProcess -Environment $coordinatorEnvironment -Script 'coordinator.py' `
    -StandardOutput (Join-Path $RuntimeDir 'coordinator.stdout.log') `
    -StandardError (Join-Path $RuntimeDir 'coordinator.stderr.log')

$deadline = (Get-Date).AddSeconds(15)
do {
    Start-Sleep -Milliseconds 250
    $listening = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort $Port -ErrorAction SilentlyContinue
} until ($listening -or (Get-Date) -gt $deadline)
if (-not $listening) { throw "Coordinator did not listen on $Port" }

$workerEnvironment = @{
    ALMA_TOKEN = $token
    ALMA_COORD = "http://127.0.0.1:$Port"
    ALMA_WORKER = 'codex-acceptance-worker'
    ALMA_EXECUTE = '1'
    ALMA_POLL = '0.5'
    ALMA_JOB_TIMEOUT = '15'
    PYTHONUNBUFFERED = '1'
}
$worker = Start-FederationProcess -Environment $workerEnvironment -Script 'worker.py' `
    -StandardOutput (Join-Path $RuntimeDir 'worker.stdout.log') `
    -StandardError (Join-Path $RuntimeDir 'worker.stderr.log')

$manifest = [ordered]@{
    coordinator_pid = $coordinator.Id
    worker_pid = $worker.Id
    bind = '127.0.0.1'
    port = $Port
    state = (Join-Path $RuntimeDir 'state.json')
    coordinator_log = (Join-Path $RuntimeDir 'coordinator.stdout.log')
    worker_log = (Join-Path $RuntimeDir 'worker.stdout.log')
    started_utc = (Get-Date).ToUniversalTime().ToString('o')
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding utf8

$headers = @{ 'X-Alma-Token' = $token }
$deadline = (Get-Date).AddSeconds(15)
do {
    Start-Sleep -Milliseconds 250
    $apiStatus = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/status" -Headers $headers -TimeoutSec 3
} until (($apiStatus.online -contains 'codex-acceptance-worker') -or (Get-Date) -gt $deadline)
if (-not ($apiStatus.online -contains 'codex-acceptance-worker')) {
    throw 'Worker did not register'
}

Get-RuntimeStatus | ConvertTo-Json -Depth 5
