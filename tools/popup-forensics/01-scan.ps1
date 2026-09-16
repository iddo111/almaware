# popup-forensics scan — read-only inventory of bot tasks, processes, startup, notifications
# Outputs JSON-ish blocks to a transcript log. No state changes.
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$logRoot = 'C:\Users\<user>\.claude\projects\D--CLAUDE\logs'
$null = New-Item -ItemType Directory -Force -Path $logRoot
$transcript = Join-Path $logRoot "popup-forensics-scan-$ts.log"
Start-Transcript -Path $transcript -Append | Out-Null

function Section($name) {
    Write-Output ''
    Write-Output ('===== ' + $name + ' =====')
}

Section 'BOT-TASKS'
try {
    Get-ScheduledTask -TaskName 'Bot-*' -ErrorAction SilentlyContinue |
        ForEach-Object {
            $info = $_ | Get-ScheduledTaskInfo
            [pscustomobject]@{
                TaskName    = $_.TaskName
                State       = $_.State
                LastRun     = $info.LastRunTime
                LastResult  = ('0x{0:X}' -f $info.LastTaskResult)
                NextRun     = $info.NextRunTime
            }
        } | Format-Table -AutoSize | Out-String -Width 200
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'BOT-POPUPGUARDIAN-DETAILS'
try {
    $tn = 'Bot-PopupWindowGuardian'
    $task = Get-ScheduledTask -TaskName $tn -ErrorAction SilentlyContinue
    if ($task) {
        $task | Format-List TaskName,State,Description | Out-String -Width 200
        $task.Actions | ForEach-Object {
            [pscustomobject]@{
                Execute   = $_.Execute
                Arguments = $_.Arguments
                WorkDir   = $_.WorkingDirectory
            }
        } | Format-List | Out-String -Width 200
    } else { Write-Output "Bot-PopupWindowGuardian NOT FOUND" }
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'BOT-IFMAGONYWATCHER-DETAILS'
try {
    $tn2 = 'Bot-IFMAgonyWatcher'
    $task2 = Get-ScheduledTask -TaskName $tn2 -ErrorAction SilentlyContinue
    if ($task2) {
        $task2 | Format-List TaskName,State,Description | Out-String -Width 200
    } else { Write-Output "Bot-IFMAgonyWatcher NOT FOUND" }
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'WINDOWED-PROCESSES'
try {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -ne '' } |
        Sort-Object ProcessName |
        Select-Object Id, ProcessName, MainWindowTitle, Path |
        Format-Table -AutoSize -Wrap | Out-String -Width 240
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'POPUP-CANDIDATE-PROCESSES'
$patterns = @(
    'vlc','Microsoft.Photos','Photos','ZuneVideo','Films','GameBar','Xbox','Cortana',
    'MicrosoftEdgeUpdate','EdgeUpdate','OneDrive','SecHealthUI','SecurityHealth',
    'HPNotifications','HPSupportAssistant','DellSupport','LenovoVantage','LenovoCompanion',
    'NvBackend','NVIDIA','GeForce','RealtekAudio','RtkAudUService','OfficeClickToRun',
    'MSOSync','OfficeC2RClient','Zoom','Teams','BraveBrowserUpdate','ChromeUpdater',
    'GoogleUpdate','AdobeUpdate','RuntimeBroker','SearchApp','WidgetService','CrossDeviceService'
)
try {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object {
            $name = $_.ProcessName
            $patterns | Where-Object { $name -like "*$_*" }
        } |
        Select-Object Id, ProcessName, MainWindowTitle, StartTime, Path |
        Format-Table -AutoSize -Wrap | Out-String -Width 240
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'STARTUP-COMMANDS'
try {
    Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue |
        Select-Object Name, User, Location, Command |
        Format-Table -AutoSize -Wrap | Out-String -Width 240
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'HKCU-RUN'
try {
    Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -ErrorAction SilentlyContinue |
        Select-Object * -ExcludeProperty PS* |
        Format-List | Out-String -Width 240
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'HKCU-RUNONCE'
try {
    Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -ErrorAction SilentlyContinue |
        Select-Object * -ExcludeProperty PS* |
        Format-List | Out-String -Width 240
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'HKLM-RUN'
try {
    Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run' -ErrorAction SilentlyContinue |
        Select-Object * -ExcludeProperty PS* |
        Format-List | Out-String -Width 240
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'HKLM-RUN-WOW64'
try {
    Get-ItemProperty 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run' -ErrorAction SilentlyContinue |
        Select-Object * -ExcludeProperty PS* |
        Format-List | Out-String -Width 240
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'NOTIFICATION-SETTINGS'
try {
    $base = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings'
    if (Test-Path $base) {
        Get-ChildItem $base -ErrorAction SilentlyContinue | ForEach-Object {
            $sub = $_
            $vals = Get-ItemProperty -Path $sub.PSPath -ErrorAction SilentlyContinue
            [pscustomobject]@{
                App     = $sub.PSChildName
                Enabled = $vals.Enabled
                ShowInActionCenter = $vals.ShowInActionCenter
                ShowOnLockScreen = $vals.ShowOnLockScreen
                ShowBanner = $vals.ShowBanner
            }
        } | Format-Table -AutoSize -Wrap | Out-String -Width 240
    } else { Write-Output "Notifications base key not found" }
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'FOCUS-ASSIST-QUIET-HOURS'
try {
    $qh = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings\Windows.SystemToast.QuietHours'
    if (Test-Path $qh) {
        Get-ItemProperty $qh -ErrorAction SilentlyContinue |
            Select-Object * -ExcludeProperty PS* | Format-List | Out-String -Width 240
    } else { Write-Output 'QuietHours key not found' }
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'TOAST-GLOBAL-TOGGLES'
try {
    $pn = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\PushNotifications'
    if (Test-Path $pn) {
        Get-ItemProperty $pn -ErrorAction SilentlyContinue |
            Select-Object * -ExcludeProperty PS* | Format-List | Out-String -Width 240
    } else { Write-Output 'PushNotifications key not found' }
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'PENDING-REBOOT'
try {
    $r1 = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending'
    $r2 = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
    [pscustomobject]@{ CBS_RebootPending = $r1; WUAU_RebootRequired = $r2 } | Format-List | Out-String -Width 240
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'DEFENDER-STATE'
try {
    Get-MpComputerStatus -ErrorAction SilentlyContinue |
        Select-Object QuickScanInProgress, FullScanInProgress, AntivirusSignatureLastUpdated, AMServiceEnabled, RealTimeProtectionEnabled |
        Format-List | Out-String -Width 240
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Section 'STARTUP-FOLDERS'
try {
    Get-ChildItem 'C:\Users\<user>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup' -ErrorAction SilentlyContinue |
        Select-Object Name, FullName | Format-Table -AutoSize -Wrap | Out-String -Width 240
    Get-ChildItem 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp' -ErrorAction SilentlyContinue |
        Select-Object Name, FullName | Format-Table -AutoSize -Wrap | Out-String -Width 240
} catch { Write-Output "ERR: $($_.Exception.Message)" }

Stop-Transcript | Out-Null
Write-Output ('TRANSCRIPT: ' + $transcript)
exit 0
