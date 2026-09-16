#Requires -Version 5.1
<#
.SYNOPSIS
    Re-index D:\CLAUDE\ in OpenGrok. Safe to run manually or via Task Scheduler.
    iddoperez.ai

.DESCRIPTION
    Runs the OpenGrok indexer (opengrok.jar) against SRC_ROOT = D:\CLAUDE\
    and writes updated index data to DATA_ROOT.
    Tomcat does NOT need to be restarted — OpenGrok picks up the new index live.

.EXAMPLE
    # Manual run:
    powershell -File D:\CLAUDE\tools\opengrok\reindex.ps1

    # Schedule weekly (run once as admin):
    $action  = New-ScheduledTaskAction -Execute "powershell.exe" `
                   -Argument "-NonInteractive -File D:\CLAUDE\tools\opengrok\reindex.ps1"
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3am
    Register-ScheduledTask -TaskName "OpenGrok-Weekly-Reindex" -Action $action `
                           -Trigger $trigger -RunLevel Highest
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Configuration ────────────────────────────────────────────────────────────
$OPENGROK_HOME = "D:\CLAUDE\tools\opengrok"
$SRC_ROOT      = "D:\CLAUDE"
$DATA_ROOT     = "$OPENGROK_HOME\data"
$CTAGS_EXE     = "$OPENGROK_HOME\ctags\ctags.exe"
$OG_JAR        = "$OPENGROK_HOME\opengrok\opengrok-1.14.11\lib\opengrok.jar"
$WEBINF        = "$OPENGROK_HOME\tomcat\webapps\source\WEB-INF"
$LOG_FILE      = "$OPENGROK_HOME\data\reindex.log"
$OG_URL        = "http://localhost:8088/source"

# Auto-detect JAVA_HOME
if (-not $env:JAVA_HOME) {
    $candidates = @(
        "C:\Program Files\Java\jdk-21",
        "D:\CLAUDE\tools\jdk21\jdk-21"
    )
    foreach ($c in $candidates) {
        if (Test-Path "$c\bin\java.exe") {
            $env:JAVA_HOME = $c
            break
        }
    }
}
if (-not $env:JAVA_HOME) {
    Write-Error "JAVA_HOME not set and JDK 21 not found. See INSTALL.md Step 1."
    exit 1
}
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"

# ── Pre-flight checks ────────────────────────────────────────────────────────
function Check-Exists([string]$path, [string]$label) {
    if (-not (Test-Path $path)) {
        Write-Error "$label not found at: $path`nSee INSTALL.md for setup."
        exit 1
    }
}

Check-Exists $OG_JAR    "OpenGrok JAR"
Check-Exists $CTAGS_EXE "Universal Ctags"
Check-Exists $WEBINF    "Tomcat WEB-INF (Tomcat must be started at least once)"
Check-Exists $SRC_ROOT  "Source root D:\CLAUDE"

# Ensure data dir exists
New-Item -ItemType Directory -Force -Path $DATA_ROOT | Out-Null

# ── Run indexer ──────────────────────────────────────────────────────────────
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[$timestamp] Starting OpenGrok reindex of $SRC_ROOT ..."

$logProps = "$WEBINF\logging.properties"
$configXml = "$WEBINF\configuration.xml"

$javaArgs = @(
    "-Djava.util.logging.config.file=`"$logProps`"",
    "-jar", "`"$OG_JAR`"",
    "-s", "`"$SRC_ROOT`"",
    "-d", "`"$DATA_ROOT`"",
    "-c", "`"$CTAGS_EXE`"",
    "-W", "`"$configXml`"",
    "-H",      # history
    "-P",      # generate projects
    "-S",      # scan for projects
    "-G",      # assign groups
    "-U", $OG_URL
)

# Exclusions — skip large binary/generated dirs to keep index fast
# Add more patterns as needed. OpenGrok uses -i for ignore patterns.
$ignorePatterns = @(
    "-i", "*.pyc",
    "-i", "__pycache__",
    "-i", "node_modules",
    "-i", ".git",
    "-i", "*.jar",
    "-i", "*.zip",
    "-i", "*.tar.gz",
    "-i", "*.mp3",
    "-i", "*.mp4",
    "-i", "*.wav",
    "-i", "*.png",
    "-i", "*.jpg",
    "-i", "*.jpeg",
    "-i", "*.gif",
    "-i", "*.ico",
    "-i", "auth_info_baileys",
    "-i", "data"  # skip opengrok's own data dir
)

$allArgs = $javaArgs + $ignorePatterns

$startTime = Get-Date
try {
    $proc = Start-Process -FilePath "java.exe" `
                          -ArgumentList $allArgs `
                          -NoNewWindow -Wait -PassThru `
                          -RedirectStandardOutput "$DATA_ROOT\indexer_stdout.log" `
                          -RedirectStandardError  "$DATA_ROOT\indexer_stderr.log"
    $elapsed = ((Get-Date) - $startTime).TotalSeconds
    if ($proc.ExitCode -eq 0) {
        $msg = "[$timestamp] Reindex completed in $([math]::Round($elapsed,1))s. Exit: 0"
        Write-Host $msg -ForegroundColor Green
    } else {
        $msg = "[$timestamp] Reindex FAILED in $([math]::Round($elapsed,1))s. Exit: $($proc.ExitCode)"
        Write-Warning $msg
        Write-Host "Check: $DATA_ROOT\indexer_stderr.log"
    }
} catch {
    $msg = "[$timestamp] ERROR launching indexer: $_"
    Write-Error $msg
}

# Append to rolling log
Add-Content -Path $LOG_FILE -Value $msg -Encoding UTF8

Write-Host ""
Write-Host "Browse your indexed code at: $OG_URL/"
