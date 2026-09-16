# Popup Watchdog
# Scans every 10 seconds for windows matching known popup/adware patterns
# Does NOT auto-close and does NOT create notifications - evidence log only.
# Log: D:/CLAUDE/tools/watchdogs/logs/popup.log

$LogFile     = "D:\CLAUDE\tools\watchdogs\logs\popup.log"
$IntervalSec = 10

# Title patterns to flag (case-insensitive)
$TitlePatterns = @(
    "Update available",
    "Install now",
    "Free upgrade",
    "Your PC is at risk",
    "Your computer is at risk",
    "Virus detected",
    "Security alert",
    "Windows Defender Alert",
    "Call Microsoft",
    "Call Apple",
    "Call Support",
    "Activate Windows now",
    "You have a virus",
    "Congratulations",
    "You've been selected",
    "Claim your prize",
    "Download now",
    "Limited time offer",
    "Sponsored",
    "Advertisement",
    "Adobe Flash",
    "Java Update",
    "Chrome Update",
    "Firefox Update",
    "Driver Update",
    "PC Optimizer",
    "Speed up your PC",
    "Registry Cleaner",
    "System Care",
    "PC Cleaner",
    "One-click fix"
)

# Known adware / PUP process names
$AdwareProcesses = @(
    "adaware",
    "conduit",
    "babylon",
    "search_protect",
    "browserprotect",
    "awesomehp",
    "sweetim",
    "delta",
    "iminent",
    "trovi",
    "webssearches",
    "snap.do",
    "mypcbackup",
    "pcspeedup",
    "registrybooster",
    "reimage",
    "ilivid",
    "defaulttab",
    "wajam",
    "shopperz",
    "crossrider",
    "superfish"
)

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

# Load user32 for EnumWindows
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class WinEnum {
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    public static List<Tuple<IntPtr, string, uint>> GetVisibleWindows() {
        var result = new List<Tuple<IntPtr, string, uint>>();
        EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
            if (IsWindowVisible(hWnd)) {
                var sb = new StringBuilder(256);
                GetWindowText(hWnd, sb, 256);
                string title = sb.ToString().Trim();
                if (title.Length > 0) {
                    uint pid = 0;
                    GetWindowThreadProcessId(hWnd, out pid);
                    result.Add(new Tuple<IntPtr, string, uint>(hWnd, title, pid));
                }
            }
            return true;
        }, IntPtr.Zero);
        return result;
    }
}
"@

# Track already-reported windows to avoid spam (hwnd -> title)
$reported = @{}

Write-Log "Popup Watchdog started - scanning every ${IntervalSec}s (log only, no auto-close)"

while ($true) {
    try {
        $windows = [WinEnum]::GetVisibleWindows()
        $currentHwnds = @{}

        foreach ($win in $windows) {
            $hwnd  = $win.Item1
            $title = $win.Item2
            # $PID is a reserved, read-only PowerShell automatic variable.
            $ownerPid = $win.Item3
            $currentHwnds[$hwnd] = $true

            # Check title patterns
            $matchedPattern = $null
            foreach ($pattern in $TitlePatterns) {
                if ($title -match [regex]::Escape($pattern)) {
                    $matchedPattern = $pattern
                    break
                }
            }

            # Check adware process names
            $matchedProcess = $null
            try {
                $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
                if ($proc) {
                    $procName = $proc.Name.ToLower()
                    foreach ($ap in $AdwareProcesses) {
                        if ($procName -like "*$ap*") {
                            $matchedProcess = $proc.Name
                            break
                        }
                    }
                }
            } catch {}

            $isPopup = ($null -ne $matchedPattern) -or ($null -ne $matchedProcess)

            if ($isPopup -and -not $reported.ContainsKey($hwnd)) {
                $reason = if ($matchedPattern) { "title matches '$matchedPattern'" } else { "adware process '$matchedProcess'" }
                $msg = "Popup detected - '$title' (PID $ownerPid) - $reason"
                Write-Log $msg "POPUP"
                $reported[$hwnd] = $title
            }
        }

        # Clean up reported windows that are gone
        $gone = @($reported.Keys | Where-Object { -not $currentHwnds.ContainsKey($_) })
        foreach ($h in $gone) { $reported.Remove($h) }

    } catch {
        Write-Log "Error during window scan: $_" "ERROR"
    }

    Start-Sleep -Seconds $IntervalSec
}
