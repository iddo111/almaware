# CPU Heat Watchdog
# Checks CPU temperature every 30 seconds
# Warn at 85°C, Critical at 95°C
# Log: D:/CLAUDE/tools/watchdogs/logs/cpu_heat.log

$LogFile = "D:\CLAUDE\tools\watchdogs\logs\cpu_heat.log"
$WarnThreshold  = 85
$CritThreshold  = 95
$IntervalSec    = 30

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

function Get-CpuTempCelsius {
    # Try OpenHardwareMonitor WMI namespace first
    try {
        $ohm = Get-WmiObject -Namespace "root\OpenHardwareMonitor" -Class Sensor -ErrorAction Stop |
               Where-Object { $_.SensorType -eq "Temperature" -and $_.Name -like "*CPU*" } |
               Select-Object -First 1
        if ($ohm) { return [math]::Round($ohm.Value, 1) }
    } catch {}

    # Fall back to MSAcpi_ThermalZoneTemperature (returns tenths of Kelvin)
    try {
        $zones = Get-WmiObject -Namespace "root\wmi" -Class MSAcpi_ThermalZoneTemperature -ErrorAction Stop
        if ($zones) {
            $temps = @($zones | ForEach-Object { [math]::Round($_.CurrentTemperature / 10.0 - 273.15, 1) })
            return ($temps | Measure-Object -Maximum).Maximum
        }
    } catch {}

    return $null
}

function Reduce-TopCpuProcessPriority {
    try {
        $top = Get-Process | Sort-Object CPU -Descending |
               Where-Object { $_.Name -notin @("Idle","System","svchost","lsass","csrss") } |
               Select-Object -First 1
        if ($top) {
            $top.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
            Write-Log "Reduced priority of '$($top.Name)' (PID $($top.Id)) to BelowNormal" "ACTION"
        }
    } catch {
        Write-Log "Could not reduce process priority: $_" "WARN"
    }
}

Write-Log "CPU Heat Watchdog started (warn=$WarnThreshold°C, critical=$CritThreshold°C)"

while ($true) {
    $temp = Get-CpuTempCelsius

    if ($null -eq $temp) {
        Write-Log "Could not read CPU temperature (no WMI provider available)" "WARN"
    } elseif ($temp -ge $CritThreshold) {
        Write-Log "CRITICAL — CPU temp ${temp}°C (threshold $CritThreshold°C)" "CRITICAL"
        Send-Toast "CPU CRITICAL TEMP" "CPU is at ${temp}°C! Reducing top process priority."
        Reduce-TopCpuProcessPriority
    } elseif ($temp -ge $WarnThreshold) {
        Write-Log "WARNING — CPU temp ${temp}°C (threshold $WarnThreshold°C)" "WARN"
    } else {
        Write-Log "OK — CPU temp ${temp}°C" "INFO"
    }

    Start-Sleep -Seconds $IntervalSec
}
