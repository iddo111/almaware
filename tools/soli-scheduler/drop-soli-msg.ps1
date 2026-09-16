# Drops the Soli WA message into wa-puppeteer outbox.
# Scheduled to run once at 10:00 IL on 2026-05-27.
# Reads Soli's JID from soli-jid.txt next to this script.
# Format of soli-jid.txt: one line, e.g. "9725XXXXXXXX@s.whatsapp.net" or "<lid>@lid"

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$jidFile = Join-Path $here 'soli-jid.txt'
$msgFile = 'D:\CLAUDE\soli-msg-2026-05-27.txt'
$outbox = 'D:\CLAUDE\whatsapp-bridge\outbox'
$log = Join-Path $here 'drop.log'

function W($m) { "{0:o} {1}" -f (Get-Date), $m | Out-File -Append -Encoding utf8 $log }

if (-not (Test-Path $jidFile)) { W "ABORT no soli-jid.txt — paste Soli's JID in $jidFile and re-run"; exit 2 }
if (-not (Test-Path $msgFile)) { W "ABORT no message file at $msgFile"; exit 2 }
if (-not (Test-Path $outbox))  { W "ABORT outbox missing: $outbox"; exit 2 }

$jid  = (Get-Content $jidFile -Raw).Trim()
$body = (Get-Content $msgFile -Raw -Encoding utf8).Trim()
$ts   = [int64]((Get-Date).ToUniversalTime() - (Get-Date '1970-01-01')).TotalMilliseconds

$obj = [ordered]@{
  to     = $jid
  body   = $body
  text   = $body
  source = 'wa-mcp/clod-cli/soli-daily-tip-2026-05-27'
  ts_ms  = $ts
}
$json = $obj | ConvertTo-Json -Compress -Depth 4
$out  = Join-Path $outbox "$ts-soli-daily.json"
[System.IO.File]::WriteAllText($out, $json, (New-Object System.Text.UTF8Encoding $false))
W "DROPPED $out -> $jid ($($body.Length) chars)"
