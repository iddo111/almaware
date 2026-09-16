<#
ALMAWARE A70 Dispatch Watchdog
==============================
Self-healing health monitor for the PC <-> A70 (Samsung Galaxy A70) dispatch path.

Runs hourly via Scheduled Task 'ALMAWARE-A70-Dispatch-Watchdog' (see install-watchdog.ps1).

What it checks + auto-repairs (in dependency order):

  1. pc-listener.py  -> PC inbox HTTP on :18180. If port not listening OR /ping
                        does not return "pong", reap + respawn under pythonw
                        (same proven logic as keeper.py). REPAIRABLE by this PC.
  2. Tailscale (PC)  -> daemon up + logged in + has a 100.x IP. If the service is
                        stopped, start it. If it is logged OUT (NeedsLogin), that
                        is a HUMAN GATE -> log + surface, cannot self-fix.
  3. A70 reachable   -> tailscale ping <tailnet-ip>. If down, that usually means
                        the phone is off / off-tailnet / asleep -> HUMAN GATE.
                        Also try an ADB reconnect (LAN fallback) if adb is present.
  4. MQTT broker     -> TCP connect to the GLOCK broker (laptop 'lapclod'). If the
                        broker/laptop is offline -> HUMAN GATE (start the laptop +
                        run install-broker.sh). NOTE: broker config currently has
                        ONLY a LAN listener; the Tailscale listener is commented
                        out, so roaming MQTT will not work until that is enabled
                        (documented in README -> Human gates).

This watchdog NEVER fakes connectivity. Offline pieces are logged with a clear
reason and the exact human action required; the next hourly run retries.

Exit code: always 0 (a watchdog must not be seen as "failed" by the scheduler
just because a remote device is offline). Health is reported in the JSON state
file + the log. Use -Verbose or read the log to see detail.

Per Iddo's conventions: no emoji, ASCII output, python312 where Python is needed.

Usage:
  pwsh -NoProfile -ExecutionPolicy Bypass -File D:\CLAUDE\dispatch-fix\watchdog.ps1
  pwsh -File watchdog.ps1 -DryRun      # check only, do not repair
#>
[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'

# ---- Config ----------------------------------------------------------------
$Root        = 'D:\CLAUDE\dispatch-fix'
$Bin         = Join-Path $Root 'bin'
$StateDir    = Join-Path $Root 'state'
$Log         = Join-Path $Root 'watchdog.log'
$HealthJson  = Join-Path $StateDir 'watchdog-health.json'
$ListenerPy  = Join-Path $Bin 'pc-listener.py'
$ListenerPort = 18180

$PythonW     = 'C:\Users\<user>\AppData\Local\Programs\Python\Python312\pythonw.exe'
$Python      = 'C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe'
$Tailscale   = 'C:\Program Files\Tailscale\tailscale.exe'

# A70 + broker endpoints (A70 tailnet IP per handoff; broker = GLOCK MQTT on laptop)
$A70TailIp   = '<tailnet-ip>'
$BrokerHost  = '<tailnet-ip>'   # GLOCK broker over Tailscale (laptop 'lapclod')
$BrokerLanIp = '<lan-ip>'      # LAN listener (mosquitto-glock.conf)
$BrokerPort  = 1883

if (-not (Test-Path $StateDir)) { New-Item -ItemType Directory -Path $StateDir -Force | Out-Null }

# ---- Logging ---------------------------------------------------------------
function Write-Wlog {
    param([string]$Level, [string]$Msg)
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $line = "$stamp [$Level] $Msg"
    try { Add-Content -Path $Log -Value $line -Encoding utf8 } catch {}
    Write-Verbose $line
}

# Accumulates per-check results for the health JSON + summary log line.
$Health = [ordered]@{
    ts              = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    pc_listener     = 'unknown'
    pc_listener_act = 'none'
    tailscale_pc    = 'unknown'
    a70_reachable   = 'unknown'
    broker          = 'unknown'
    gates           = @()
    overall         = 'unknown'
}

# ---- adb resolver (adb is frequently NOT on PATH on this box) ---------------
$script:AdbExe = $null
function Resolve-Adb {
    if ($script:AdbExe) { return $script:AdbExe }
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) { $script:AdbExe = $cmd.Source; return $script:AdbExe }
    $cands = @(
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe",
        "$env:USERPROFILE\scoop\shims\adb.exe",
        "C:\ProgramData\chocolatey\bin\adb.exe",
        "C:\platform-tools\adb.exe",
        "D:\platform-tools\adb.exe"
    )
    foreach ($c in $cands) { if (Test-Path $c) { $script:AdbExe = $c; return $c } }
    return $null
}

# ===========================================================================
# Check 1: pc-listener.py  (REPAIRABLE on this PC)
# ===========================================================================
function Test-PortListening([int]$Port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect('127.0.0.1', $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(2000, $false)
        if ($ok -and $c.Connected) { $c.EndConnect($iar); $c.Close(); return $true }
        $c.Close(); return $false
    } catch { return $false }
}

function Test-ListenerPing {
    # GET /ping over a raw socket; expect "pong" in the response body.
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect('127.0.0.1', $ListenerPort, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne(2000, $false)) { $c.Close(); return $false }
        $c.EndConnect($iar)
        $s = $c.GetStream(); $s.ReadTimeout = 3000
        $req = "GET /ping HTTP/1.1`r`nHost: localhost`r`nConnection: close`r`n`r`n"
        $b = [System.Text.Encoding]::ASCII.GetBytes($req)
        $s.Write($b, 0, $b.Length); $s.Flush()
        $buf = New-Object byte[] 4096
        $n = $s.Read($buf, 0, $buf.Length)
        $c.Close()
        $resp = [System.Text.Encoding]::ASCII.GetString($buf, 0, $n)
        return ($resp -match 'pong')
    } catch { return $false }
}

function Repair-Listener {
    # Reap any wedged listener that owns :18180, then respawn one clean copy
    # under pythonw (detached, no console). Mirrors keeper.py's strategy.
    Write-Wlog 'ACTION' 'repairing pc-listener: reap + respawn'
    if ($DryRun) { Write-Wlog 'DRYRUN' 'would reap + respawn pc-listener'; return }

    # (1) kill the port owner (instant, no CIM)
    try {
        $owner = (Get-NetTCPConnection -LocalPort $ListenerPort -State Listen -ErrorAction SilentlyContinue |
                  Select-Object -First 1 -ExpandProperty OwningProcess)
        if ($owner) { Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue; Write-Wlog 'ACTION' "killed port owner PID $owner" }
    } catch { Write-Wlog 'WARN' "port-owner kill failed: $($_.Exception.Message)" }

    # (2) sweep any stragglers running pc-listener.py
    try {
        Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like '*pc-listener.py*' } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Wlog 'ACTION' "killed straggler PID $($_.ProcessId)" }
    } catch { Write-Wlog 'WARN' "straggler sweep slow/failed: $($_.Exception.Message)" }

    # (3) wait for the LISTEN socket to free so the fresh bind doesn't race
    for ($i = 0; $i -lt 10; $i++) { if (-not (Test-PortListening $ListenerPort)) { break }; Start-Sleep -Milliseconds 500 }

    # (4) respawn detached under pythonw (falls back to python.exe)
    $exe = if (Test-Path $PythonW) { $PythonW } elseif (Test-Path $Python) { $Python } else { 'pythonw.exe' }
    try {
        Start-Process -FilePath $exe -ArgumentList @($ListenerPy) -WorkingDirectory $Root -WindowStyle Hidden | Out-Null
        Write-Wlog 'ACTION' "respawn submitted via $exe"
    } catch {
        Write-Wlog 'ERROR' "respawn failed: $($_.Exception.Message)"
    }
}

function Check-Listener {
    $listening = Test-PortListening $ListenerPort
    $pong = if ($listening) { Test-ListenerPing } else { $false }
    Write-Wlog 'CHECK' "pc-listener listening=$listening pong=$pong"
    if ($listening -and $pong) {
        $Health.pc_listener = 'up'
        return
    }
    $Health.pc_listener = 'down'
    Repair-Listener
    $Health.pc_listener_act = 'respawned'
    # Re-verify after a short settle.
    Start-Sleep -Seconds 3
    $listening2 = Test-PortListening $ListenerPort
    $pong2 = if ($listening2) { Test-ListenerPing } else { $false }
    if ($listening2 -and $pong2) {
        Write-Wlog 'OK' 'pc-listener recovered after respawn'
        $Health.pc_listener = 'recovered'
    } else {
        Write-Wlog 'WARN' "pc-listener still down after respawn (listening=$listening2 pong=$pong2)"
        $Health.pc_listener = 'down-after-repair'
        $Health.gates += 'pc-listener did not recover: check python312 + pc-listener.py manually'
    }
}

# ===========================================================================
# Check 2: Tailscale on the PC
# ===========================================================================
function Check-Tailscale {
    if (-not (Test-Path $Tailscale)) {
        Write-Wlog 'WARN' 'tailscale.exe not found at standard path'
        $Health.tailscale_pc = 'absent'
        $Health.gates += 'Tailscale not installed on PC: install from tailscale.com and log in'
        return $false
    }
    # Ensure the service is running first (it may be stopped after a crash).
    $svc = Get-Service -Name 'Tailscale' -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -ne 'Running') {
        Write-Wlog 'ACTION' "Tailscale service is $($svc.Status); starting it"
        if (-not $DryRun) { try { Start-Service -Name 'Tailscale' -ErrorAction Stop; Start-Sleep -Seconds 3 } catch { Write-Wlog 'WARN' "Start-Service Tailscale failed: $($_.Exception.Message)" } }
    }
    # Query our own tailnet IP. Empty / NeedsLogin => logged out (human gate).
    $ip = ''
    try { $ip = (& $Tailscale ip -4 2>&1 | Select-Object -First 1) } catch { $ip = "$_" }
    $ip = "$ip".Trim()
    if ($ip -match '^100\.\d+\.\d+\.\d+$') {
        Write-Wlog 'CHECK' "tailscale PC up, ip=$ip"
        $Health.tailscale_pc = "up:$ip"
        return $true
    }
    # Not authed. We can attempt `tailscale up` ONLY if state allows non-interactive
    # bring-up (i.e. key still valid). If it says NeedsLogin, that is a human gate.
    Write-Wlog 'WARN' "tailscale PC not ready (ip='$ip'). Attempting non-interactive 'up'."
    if (-not $DryRun) {
        try { $upOut = (& $Tailscale up --timeout 20s 2>&1 | Out-String).Trim(); Write-Wlog 'INFO' "tailscale up -> $upOut" } catch { Write-Wlog 'WARN' "tailscale up failed: $($_.Exception.Message)" }
        Start-Sleep -Seconds 2
        try { $ip = (& $Tailscale ip -4 2>&1 | Select-Object -First 1).Trim() } catch { $ip = '' }
    }
    if ($ip -match '^100\.\d+\.\d+\.\d+$') {
        Write-Wlog 'OK' "tailscale PC recovered, ip=$ip"
        $Health.tailscale_pc = "recovered:$ip"
        return $true
    }
    Write-Wlog 'GATE' 'Tailscale PC is logged out (NeedsLogin). HUMAN: run "tailscale up" and log in via the browser URL.'
    $Health.tailscale_pc = 'logged-out'
    $Health.gates += 'Tailscale PC logged out: run `& "C:\Program Files\Tailscale\tailscale.exe" up` and complete the login URL in a browser'
    return $false
}

# ===========================================================================
# Check 3: A70 reachability
# ===========================================================================
function Check-A70([bool]$TsUp) {
    $reachable = $false
    if ($TsUp) {
        try {
            $out = (& $Tailscale ping --c 2 --timeout 3s $A70TailIp 2>&1 | Out-String)
            if ($out -match 'pong from|via DERP|via \d') { $reachable = $true }
            Write-Wlog 'CHECK' "tailscale ping A70 ($A70TailIp): $(if($reachable){'reachable'}else{'no response'})"
        } catch { Write-Wlog 'WARN' "tailscale ping A70 failed: $($_.Exception.Message)" }
    } else {
        Write-Wlog 'INFO' 'skipping tailscale ping A70 (PC tailscale not up)'
    }

    # LAN fallback: try ADB if present (only useful when A70 + PC are on same WiFi).
    if (-not $reachable) {
        $adb = Resolve-Adb
        if ($adb) {
            $endpointFile = Join-Path $StateDir 'a70-adb-endpoint.txt'
            $endpoint = if (Test-Path $endpointFile) { (Get-Content $endpointFile -Raw).Trim() } else { '' }
            if ($endpoint -and $endpoint -like '*_adb-tls-connect*' -and -not $DryRun) {
                Write-Wlog 'ACTION' "attempting adb connect to mDNS endpoint $endpoint"
                try { & $adb connect $endpoint 2>&1 | Out-Null } catch {}
            }
            try {
                $devs = (& $adb devices 2>&1 | Out-String)
                if ($devs -match "(\S+)\s+device(\r|\n|$)") {
                    Write-Wlog 'CHECK' 'A70 reachable via ADB (LAN fallback)'
                    $reachable = $true
                }
            } catch {}
        } else {
            Write-Wlog 'INFO' 'adb not installed; cannot use LAN fallback for A70'
        }
    }

    if ($reachable) {
        $Health.a70_reachable = 'up'
    } else {
        $Health.a70_reachable = 'down'
        Write-Wlog 'GATE' 'A70 not reachable. HUMAN: power on the A70, ensure Tailscale (Always-on VPN) is connected, and the phone is unlocked + paired.'
        $Health.gates += 'A70 offline: power on the phone + connect Tailscale (Always-on VPN) + unlock; then it rejoins the tailnet'
    }
    return $reachable
}

# ===========================================================================
# Check 4: MQTT broker (GLOCK, on the Linux laptop 'lapclod')
# ===========================================================================
function Test-Tcp([string]$TargetHost, [int]$Port, [int]$TimeoutMs = 2500) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect($TargetHost, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if ($ok -and $c.Connected) { $c.EndConnect($iar); $c.Close(); return $true }
        $c.Close(); return $false
    } catch { return $false }
}

function Check-Broker([bool]$TsUp) {
    $up = $false
    $via = ''
    if ($TsUp -and (Test-Tcp $BrokerHost $BrokerPort)) { $up = $true; $via = "tailscale ${BrokerHost}:${BrokerPort}" }
    elseif (Test-Tcp $BrokerLanIp $BrokerPort) { $up = $true; $via = "lan ${BrokerLanIp}:${BrokerPort}" }

    if ($up) {
        Write-Wlog 'CHECK' "MQTT broker reachable ($via)"
        $Health.broker = "up:$via"
    } else {
        Write-Wlog 'GATE' 'MQTT broker not reachable. HUMAN: start the Linux laptop (lapclod) + ensure mosquitto is running (sudo systemctl status mosquitto / re-run install-broker.sh).'
        $Health.broker = 'down'
        $Health.gates += 'MQTT broker offline: start the Linux laptop (lapclod) + `sudo systemctl restart mosquitto`; if config has only a LAN listener, the A70 cannot reach it while roaming (enable the Tailscale listener in mosquitto-glock.conf)'
    }
    return $up
}

# ===========================================================================
# Main
# ===========================================================================
Write-Wlog 'RUN' "watchdog start (DryRun=$DryRun)"

Check-Listener
$tsUp     = Check-Tailscale
$a70Up    = Check-A70 $tsUp
$brokerUp = Check-Broker $tsUp

# Overall: the PC-side path (listener) is what THIS machine owns. Remote pieces
# are gated on human action and reported, not counted as a PC failure.
$pcOk = ($Health.pc_listener -in @('up', 'recovered'))
if ($pcOk -and $a70Up -and $brokerUp -and $tsUp) {
    $Health.overall = 'healthy'
} elseif ($pcOk) {
    $Health.overall = 'pc-ok-remote-gated'
} else {
    $Health.overall = 'degraded'
}

# Persist health JSON for dashboards / later inspection.
try {
    $Health.gates = @($Health.gates)
    ($Health | ConvertTo-Json -Depth 4) | Out-File -FilePath $HealthJson -Encoding utf8
} catch { Write-Wlog 'WARN' "could not write health json: $($_.Exception.Message)" }

$gatecount = @($Health.gates).Count
Write-Wlog 'DONE' "overall=$($Health.overall) listener=$($Health.pc_listener) ts=$($Health.tailscale_pc) a70=$($Health.a70_reachable) broker=$($Health.broker) gates=$gatecount"

# A watchdog must not look "failed" to the scheduler just because a remote device
# is off. Always exit 0; health is in the JSON + log.
exit 0
