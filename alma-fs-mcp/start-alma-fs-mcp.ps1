# start-alma-fs-mcp.ps1 -- restart ALMA FS MCP cleanly and prove it is up.
# Idempotent: kills any existing listener on the port BY PORT (pkill -f never
# matches a Windows python process), starts one fresh, then verifies.

param(
    [int]$Port = 8930,
    [string]$Root = "D:\CLAUDE\alma-fs-mcp"
)

$ErrorActionPreference = "Stop"
$script = Join-Path $Root "alma_fs_mcp.py"

if (-not (Test-Path $script)) { throw "not found: $script" }

Write-Host "[1/4] killing anything on port $Port ..."
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($c in $existing) {
    try { Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop; Write-Host "      killed PID $($c.OwningProcess)" }
    catch { Write-Host "      could not kill PID $($c.OwningProcess): $_" }
}
Start-Sleep -Seconds 1

Write-Host "[2/4] starting server ..."
Start-Process -FilePath "python" `
    -ArgumentList "`"$script`"" `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Root "server.log") `
    -RedirectStandardError  (Join-Path $Root "server.err")
Start-Sleep -Seconds 3

Write-Host "[3/4] confirming exactly one listener ..."
$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
Write-Host "      listener count: $($listeners.Count)"
if ($listeners.Count -eq 0) {
    Write-Host "      FAILED to start. server.err says:" -ForegroundColor Red
    Get-Content (Join-Path $Root "server.err") -Tail 20 -ErrorAction SilentlyContinue
    exit 1
}
if ($listeners.Count -gt 1) {
    # Two processes CAN bind the same port on Windows and both answer,
    # alternating. That produces baffling intermittent failures.
    Write-Host "      WARNING: $($listeners.Count) listeners on $Port -- responses will be nondeterministic." -ForegroundColor Yellow
}

Write-Host "[4/4] health check ..."
try {
    $h = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 10
    Write-Host "      HTTP $($h.StatusCode)" -ForegroundColor Green
    Write-Host "      $($h.Content)"
} catch {
    Write-Host "      health check FAILED: $_" -ForegroundColor Red
    exit 1
}

$ts = (tailscale ip -4 2>$null | Select-Object -First 1)
Write-Host ""
Write-Host "ALMA FS MCP is up. Give your chat UI one of these:" -ForegroundColor Green
Write-Host "  streamable HTTP : http://127.0.0.1:$Port/mcp"
Write-Host "  legacy SSE      : http://127.0.0.1:$Port/sse"
if ($ts) {
    Write-Host "  from your phone : http://${ts}:$Port/mcp   (or /sse)"
}
