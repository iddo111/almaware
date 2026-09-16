<#
    BODY-TUNNEL-SETUP.ps1 -- finish the outer wall, after Iddo has done his two clicks.

    BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    This script does NOT create anything in Iddo's Cloudflare account and does not log in
    anywhere. It only wires up what he created in the dashboard:

        1. he creates the tunnel  alma-body  in the Zero Trust dashboard and copies its
           connector token into  D:\CLAUDE\iddo-harness\state\body_tunnel_token.txt
        2. he adds the public hostname  body.iddoperez.ai -> http://127.0.0.1:8898
        3. he creates the Access application over that hostname

    ...and then this script ACLs the token, registers the hidden BELOW_NORMAL logon task
    ALMA-Body-Tunnel, starts it, and MEASURES whether the hostname really answers.

    Run:   powershell -ExecutionPolicy Bypass -File D:\CLAUDE\almido\BODY-TUNNEL-SETUP.ps1
    Undo:  Unregister-ScheduledTask -TaskName ALMA-Body-Tunnel -Confirm:$false
#>
[CmdletBinding()]
param(
    [string]$Hostname  = "body.iddoperez.ai",
    [string]$TokenFile = "D:\CLAUDE\iddo-harness\state\body_tunnel_token.txt",
    [int]   $LocalPort = 8898,
    [switch]$SkipStart
)

$ErrorActionPreference = "Stop"
function Say($msg)  { Write-Host $msg }
function Bad($msg)  { Write-Host "FAILED: $msg" -ForegroundColor Red }
function Good($msg) { Write-Host "OK:     $msg" -ForegroundColor Green }

# ---------------------------------------------------------------- 1. cloudflared
$cfd = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $cfd)) {
    $found = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
    if ($found) { $cfd = $found } else { Bad "cloudflared is not installed. Iddo installs it: winget install Cloudflare.cloudflared"; exit 2 }
}
Good ("cloudflared " + (& $cfd --version))

# ---------------------------------------------------------------- 2. the body itself
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$LocalPort/health" -TimeoutSec 5
    if ($health.stopped) { Bad "the body is STOPPED (a STOP file exists). Clear it first."; exit 3 }
    Good "the body answers on 127.0.0.1:$LocalPort ($($health.server) $($health.version))"
} catch {
    Bad "nothing answers http://127.0.0.1:$LocalPort/health -- start it: Start-ScheduledTask -TaskName ALMA-Body-HTTP"
    exit 3
}

# ---------------------------------------------------------------- 3. the tunnel token
if (-not (Test-Path $TokenFile)) {
    Bad "no tunnel token at $TokenFile"
    Say ""
    Say "IDDO DOES THIS ONCE, in the dashboard (one.dash.cloudflare.com):"
    Say "  Networks > Tunnels > Create a tunnel > Cloudflared > name it  alma-body"
    Say "  Copy the token out of the install command it shows (the long eyJ... string)"
    Say "  and save JUST that token, one line, into:"
    Say "     $TokenFile"
    Say "  Then add a Public Hostname on that tunnel:"
    Say "     $Hostname   ->   HTTP   ->   127.0.0.1:$LocalPort"
    Say "  Then run this script again."
    exit 4
}
$token = (Get-Content $TokenFile -Raw).Trim()
if ($token.Length -lt 40) { Bad "the token file looks empty or truncated ($($token.Length) chars)"; exit 4 }
Good "tunnel token present ($($token.Length) chars, value never printed)"

# ACL it to this account alone -- by SID, never by name: this machine is called IDDO1 and
# its user is iddo1, so a name lookup resolves to the MACHINE and writes an ACE for nobody.
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls $TokenFile /inheritance:r /grant:r ("*{0}:(F)" -f $sid) | Out-Null
$acl = (Get-Acl $TokenFile).Access | Where-Object { -not $_.IsInherited }
if ($acl.Count -eq 1) { Good "token ACL: this account only" } else { Bad "token ACL has $($acl.Count) entries -- check it by hand" }

# ---------------------------------------------------------------- 4. the logon task
$me      = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action  = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c "D:\CLAUDE\almido\RUN-BODY-TUNNEL.cmd"'
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $me
$set     = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden `
                                        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 `
                                        -RestartInterval (New-TimeSpan -Minutes 1)
$set.Priority = 7
$prin    = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'ALMA-Body-Tunnel' -Action $action -Trigger $trigger -Settings $set `
    -Principal $prin -Force `
    -Description "cloudflared for body.iddoperez.ai -> 127.0.0.1:$LocalPort. Token in state\body_tunnel_token.txt." | Out-Null
Good "logon task ALMA-Body-Tunnel registered (hidden, BELOW_NORMAL)"

if ($SkipStart) { Say "--SkipStart given; not starting."; exit 0 }

# ---------------------------------------------------------------- 5. start and MEASURE
Start-ScheduledTask -TaskName 'ALMA-Body-Tunnel'
Start-Sleep -Seconds 10
$proc = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($proc) { Good "cloudflared running (pid $($proc.Id -join ','), priority $($proc[0].PriorityClass))" }
else       { Bad  "cloudflared is not running -- read D:\CLAUDE\almido\workspace\body-tunnel.log"; exit 5 }

Say ""
Say "--- what the outside sees (this is the test that matters) ---"
try {
    $r = Invoke-WebRequest -Uri "https://$Hostname/health" -MaximumRedirection 0 -SkipHttpErrorCheck -TimeoutSec 20
    $code = $r.StatusCode
} catch { $code = $_.Exception.Response.StatusCode.value__ }

if ($code -eq 200) {
    Bad "https://$Hostname/health returned 200 WITHOUT a login. THE DOOR IS OPEN TO EVERYONE."
    Say "     Create the Access application over this hostname NOW, or stop the tunnel:"
    Say "     Stop-ScheduledTask -TaskName ALMA-Body-Tunnel; Get-Process cloudflared | Stop-Process -Force"
    exit 6
} elseif ($code -in 302,303,401,403) {
    Good "https://$Hostname/health -> $code : Cloudflare Access is in front. That is the wall working."
} else {
    Say "https://$Hostname/health -> $code (DNS or the hostname may still be propagating; re-run in a minute)"
}
Say ""
Say "Next: D:\CLAUDE\almido\BODY-CONNECTOR.md -- the Access application, the service token,"
Say "and how to add the connector in claude.ai / ChatGPT / the CLI."
