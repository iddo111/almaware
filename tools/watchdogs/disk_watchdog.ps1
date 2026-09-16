# Disk Watchdog
# Checks C: and D: drive usage every 60 seconds
# Warns if either drive > 90% full
# Warns if disk queue length avg > 2 for 3+ consecutive checks
# Log: D:/CLAUDE/tools/watchdogs/logs/disk.log

$LogFile          = "D:\CLAUDE\tools\watchdogs\logs\disk.log"
$UsageWarnPct     = 90
$QueueWarnLevel   = 2
$QueueConsecutive = 3
$IntervalSec      = 60
$Drives           = @("C:", "D:")

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

# Track consecutive high-queue counts per drive letter (strip colon)
$queueStreak = @{}
foreach ($d in $Drives) { $queueStreak[$d] = 0 }

Write-Log "Disk Watchdog started (drives=$($Drives -join ','), usage_warn=${UsageWarnPct}%, queue_warn=$QueueWarnLevel for $QueueConsecutive consecutive checks)"

while ($true) {
    # --- Drive usage ---
    foreach ($drive in $Drives) {
        try {
            $disk = Get-PSDrive -Name ($drive.TrimEnd(':')) -ErrorAction Stop
            $used  = $disk.Used
            $free  = $disk.Free
            $total = $used + $free
            if ($total -gt 0) {
                $pct = [math]::Round(($used / $total) * 100, 1)
                $usedGB  = [math]::Round($used  / 1GB, 1)
                $freeGB  = [math]::Round($free  / 1GB, 1)
                $totalGB = [math]::Round($total / 1GB, 1)
                if ($pct -ge $UsageWarnPct) {
                    Write-Log "WARNING — $drive usage ${pct}% (${usedGB}GB used / ${totalGB}GB, ${freeGB}GB free)" "WARN"
                    Send-Toast "Disk Space Warning ($drive)" "$drive is ${pct}% full — only ${freeGB} GB remaining."
                } else {
                    Write-Log "OK — $drive usage ${pct}% (${freeGB}GB free of ${totalGB}GB)" "INFO"
                }
            }
        } catch {
            Write-Log "Could not read drive $drive : $_" "WARN"
        }
    }

    # --- Disk queue length via performance counters ---
    foreach ($drive in $Drives) {
        $driveLetter = $drive.TrimEnd(':')
        # Performance counter instance name uses drive letter without colon
        $counterPath = "\PhysicalDisk(*)\Avg. Disk Queue Length"
        try {
            $samples = Get-Counter -Counter $counterPath -SampleInterval 2 -MaxSamples 3 -ErrorAction Stop
            # Sum across all physical disks (conservative: if any disk is overloaded)
            $avgQueue = ($samples.CounterSamples | Where-Object { $_.InstanceName -ne "_total" } |
                         Measure-Object -Property CookedValue -Average).Average
            $avgQueue = [math]::Round($avgQueue, 2)

            if ($avgQueue -gt $QueueWarnLevel) {
                $queueStreak[$drive]++
                Write-Log "Queue check — avg disk queue length $avgQueue (streak $($queueStreak[$drive])/$QueueConsecutive)" "INFO"
                if ($queueStreak[$drive] -ge $QueueConsecutive) {
                    Write-Log "WARNING — Disk queue length avg $avgQueue exceeded $QueueWarnLevel for $($queueStreak[$drive]) consecutive checks — disk overload suspected" "WARN"
                    Send-Toast "Disk Overload Warning" "Avg disk queue length is $avgQueue — sustained I/O bottleneck detected."
                    $queueStreak[$drive] = 0  # reset after alerting
                }
            } else {
                if ($queueStreak[$drive] -gt 0) {
                    Write-Log "Queue normalized — avg disk queue length $avgQueue (streak reset)" "INFO"
                }
                $queueStreak[$drive] = 0
            }
            break  # Only need one queue check per cycle (covers all physical disks)
        } catch {
            Write-Log "Could not read disk queue counter: $_" "WARN"
            break
        }
    }

    Start-Sleep -Seconds $IntervalSec
}
