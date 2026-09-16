# ALMAWARE safe popup evidence monitor.
# Evidence only: never closes windows and never emits Toast notifications.
[CmdletBinding()]
param(
    [switch]$RunOnce,
    [ValidateRange(2, 3600)]
    [int]$IntervalSec = 10,
    [string]$LogFile = 'D:\CLAUDE\tools\watchdogs\logs\popup-safe.jsonl'
)

$ErrorActionPreference = 'Stop'
$logDir = Split-Path -Parent $LogFile
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$suspiciousTitlePatterns = @(
    'update available', 'install now', 'free upgrade', 'your pc is at risk',
    'your computer is at risk', 'virus detected', 'call microsoft',
    'call support', 'you have a virus', 'claim your prize', 'download now',
    'limited time offer', 'advertisement', 'driver update', 'pc optimizer',
    'registry cleaner', 'one-click fix'
)

$protectedTitlePatterns = @(
    'user account control', 'windows security', 'microsoft defender',
    'credential', 'password', 'passkey', 'sign in', 'permission', 'consent'
)

Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public sealed class SafePopupWindowRecord {
    public long Handle;
    public string Title;
    public string WindowClass;
    public uint ProcessId;
}

public static class SafePopupWindowAudit {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr hWnd, StringBuilder className, int maxCount);
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    public static List<SafePopupWindowRecord> VisibleWindows() {
        var records = new List<SafePopupWindowRecord>();
        EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
            if (!IsWindowVisible(hWnd)) return true;
            var title = new StringBuilder(1024);
            GetWindowText(hWnd, title, title.Capacity);
            var titleText = title.ToString().Trim();
            if (titleText.Length == 0) return true;
            var className = new StringBuilder(256);
            GetClassName(hWnd, className, className.Capacity);
            uint processId;
            GetWindowThreadProcessId(hWnd, out processId);
            records.Add(new SafePopupWindowRecord {
                Handle = hWnd.ToInt64(),
                Title = titleText,
                WindowClass = className.ToString(),
                ProcessId = processId
            });
            return true;
        }, IntPtr.Zero);
        return records;
    }
}
"@

function Test-PatternList {
    param([string]$Text, [string[]]$Patterns)
    $lower = $Text.ToLowerInvariant()
    foreach ($pattern in $Patterns) {
        if ($lower.Contains($pattern)) { return $pattern }
    }
    return $null
}

function Write-Evidence {
    param($Window, [string]$Event)
    $processName = '[unavailable]'
    $processPath = '[unavailable]'
    try {
        $process = Get-Process -Id $Window.ProcessId -ErrorAction Stop
        $processName = $process.ProcessName
        try { $processPath = $process.Path } catch {}
    }
    catch {}

    $suspiciousMatch = Test-PatternList -Text $Window.Title -Patterns $suspiciousTitlePatterns
    $protectedMatch = Test-PatternList -Text $Window.Title -Patterns $protectedTitlePatterns
    $record = [ordered]@{
        timestamp = (Get-Date).ToString('o')
        event = $Event
        handle = $Window.Handle
        title = $Window.Title
        window_class = $Window.WindowClass
        process_id = $Window.ProcessId
        process_name = $processName
        process_path = $processPath
        suspicious_title_match = $suspiciousMatch
        protected_system_or_consent_ui = [bool]$protectedMatch
        action = 'none_evidence_only'
    }
    Add-Content -LiteralPath $LogFile -Value ($record | ConvertTo-Json -Compress)
    if ($suspiciousMatch) {
        Write-Host "POPUP_EVIDENCE title='$($Window.Title)' pid=$($Window.ProcessId) process='$processName' path='$processPath' match='$suspiciousMatch'" -ForegroundColor Yellow
    }
}

$seen = @{}
Write-Host "Safe popup monitor started. Evidence: $LogFile" -ForegroundColor Green
Write-Host 'No windows will be closed; no Toast notifications will be created.'

do {
    $current = @{}
    foreach ($window in [SafePopupWindowAudit]::VisibleWindows()) {
        $key = "$($window.Handle)|$($window.Title)"
        $current[$key] = $true
        if (-not $seen.ContainsKey($key)) {
            Write-Evidence -Window $window -Event 'appeared'
        }
    }
    foreach ($key in @($seen.Keys)) {
        if (-not $current.ContainsKey($key)) {
            $goneRecord = [ordered]@{
                timestamp = (Get-Date).ToString('o')
                event = 'disappeared'
                window_key = $key
                action = 'none_evidence_only'
            }
            Add-Content -LiteralPath $LogFile -Value ($goneRecord | ConvertTo-Json -Compress)
        }
    }
    $seen = $current
    if ($RunOnce) { break }
    Start-Sleep -Seconds $IntervalSec
} while ($true)

Write-Host 'Safe popup monitor completed one pass.'
