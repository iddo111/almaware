# GPU Heat Watchdog (RTX 3070 Ti)
# Checks GPU temperature every 30 seconds via nvidia-smi
# Warn at 80°C, Critical at 90°C
# Ollama conflict warning at 85°C
# Log: D:/CLAUDE/tools/watchdogs/logs/gpu_heat.log

$LogFile       = "D:\CLAUDE\tools\watchdogs\logs\gpu_heat.log"
$WarnThreshold = 80
$CritThreshold = 90
$OllamaWarn    = 85
$IntervalSec   = 30

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

function Send-Toast {
    param([string]$Title, [string]$Message)
    try {
        $app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        $template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02
        $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template)
        $xml.GetElementsByTagName("text")[0].AppendChild($xml.CreateTextNode($Title)) | Out-Null
        $xml.GetElementsByTagName("text")[1].AppendChild($xml.CreateTextNode($Message)) | Out-Null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show($toast)
    } catch {
        Write-Log "Toast notification failed: $_" "WARN"
    }
}

function Get-GpuTempCelsius {
    try {
        $nvidiaSmi = (Get-Command "nvidia-smi" -ErrorAction Stop).Source
        $raw = & $nvidiaSmi --query-gpu=temperature.gpu --format=csv,noheader 2>$null
        if ($raw -match '^\s*(\d+)\s*$') { return [int]$Matches[1] }
    } catch {}
    return $null
}

function Test-OllamaRunning {
    $proc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
    return ($null -ne $proc)
}

Write-Log "GPU Heat Watchdog started (warn=$WarnThreshold°C, critical=$CritThreshold°C, ollama_warn=$OllamaWarn°C)"

while ($true) {
    $temp = Get-GpuTempCelsius

    if ($null -eq $temp) {
        Write-Log "Could not read GPU temperature (nvidia-smi not available or no NVIDIA GPU)" "WARN"
    } elseif ($temp -ge $CritThreshold) {
        Write-Log "CRITICAL — GPU temp ${temp}°C (threshold $CritThreshold°C)" "CRITICAL"
        Send-Toast "GPU CRITICAL TEMP" "RTX 3070 Ti is at ${temp}°C! Check cooling immediately."
    } elseif ($temp -ge $WarnThreshold) {
        Write-Log "WARNING — GPU temp ${temp}°C (threshold $WarnThreshold°C)" "WARN"
        Send-Toast "GPU High Temperature" "RTX 3070 Ti is at ${temp}°C — approaching critical."
    } else {
        Write-Log "OK — GPU temp ${temp}°C" "INFO"
    }

    # Ollama conflict check (independent of above — fires from 85°C)
    if ($null -ne $temp -and $temp -ge $OllamaWarn -and (Test-OllamaRunning)) {
        Write-Log "WARNING — Ollama is running while GPU temp is ${temp}°C (>= $OllamaWarn°C) — training/inference conflict risk" "WARN"
    }

    Start-Sleep -Seconds $IntervalSec
}
