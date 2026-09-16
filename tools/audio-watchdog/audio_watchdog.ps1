#Requires -Version 5.1
<#
.SYNOPSIS
    Audio Watchdog - keeps Focusrite Scarlett Solo USB as Default Playback
    and Default Communications device, auto-correcting if another device steals the role.

.DESCRIPTION
    Checks every 30 seconds. Corrects Console, Communications, and Multimedia roles.
    Logs corrections to audio_watchdog.log in the same directory.

    Target device : Speakers (Scarlett Solo USB)
    Target GUID   : {0.0.0.00000000}.{2a19ecc6-16d2-4348-871d-5ad0bac2fe1a}
    VID/PID       : USB\VID_1235&PID_8205

    Also watches Default Communications Capture (Microphone Scarlett Solo USB)
    Target capture: {0.0.1.00000000}.{9e858882-3bd6-4be0-bb70-f066846c47e5}

.NOTES
    Run as the logged-in user (not SYSTEM) so it has access to HKCU audio preferences.
    Registered as Scheduled Task "AudioWatchdog" — triggers at logon + every 30 sec.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'SilentlyContinue'

# ── Configuration ────────────────────────────────────────────────────────────
$SCRIPT_DIR        = Split-Path -Parent $MyInvocation.MyCommand.Definition
$LOG_FILE          = Join-Path $SCRIPT_DIR 'audio_watchdog.log'
$CHECK_INTERVAL_S  = 30

# Scarlett Solo USB render device
$TARGET_RENDER_ID  = '{0.0.0.00000000}.{2a19ecc6-16d2-4348-871d-5ad0bac2fe1a}'
$TARGET_RENDER_NAME = 'Speakers (Scarlett Solo USB)'

# Scarlett Solo USB capture device (for Communications microphone)
$TARGET_CAPTURE_ID  = '{0.0.1.00000000}.{9e858882-3bd6-4be0-bb70-f066846c47e5}'
$TARGET_CAPTURE_NAME = 'Microphone (Scarlett Solo USB)'

# VID substring to detect Scarlett is actually present on USB
$FOCUSRITE_VID     = 'VID_1235'
# ── End Configuration ────────────────────────────────────────────────────────

# ── C# / COM types ───────────────────────────────────────────────────────────
$csharpCode = @'
using System;
using System.Runtime.InteropServices;

namespace AudioWatchdog {

    // EDataFlow
    public enum DataFlow { Render = 0, Capture = 1, All = 2 }

    // ERole
    public enum Role { Console = 0, Multimedia = 1, Communications = 2 }

    [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDeviceEnumerator {
        int EnumAudioEndpoints(DataFlow dataFlow, uint dwStateMask,
            [MarshalAs(UnmanagedType.Interface)] out IMMDeviceCollection ppDevices);
        int GetDefaultAudioEndpoint(DataFlow dataFlow, Role role,
            [MarshalAs(UnmanagedType.Interface)] out IMMDevice ppEndpoint);
        int GetDevice([MarshalAs(UnmanagedType.LPWStr)] string pwstrId,
            [MarshalAs(UnmanagedType.Interface)] out IMMDevice ppDevice);
        int RegisterEndpointNotificationCallback(IntPtr pClient);
        int UnregisterEndpointNotificationCallback(IntPtr pClient);
    }

    [Guid("D666063F-1587-4E43-81F1-B948E807363F")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDevice {
        int Activate(ref Guid iid, int dwClsCtx, IntPtr pActivationParams, out IntPtr ppInterface);
        int OpenPropertyStore(int stgmAccess, out IntPtr ppProperties);
        int GetId([MarshalAs(UnmanagedType.LPWStr)] out string ppstrId);
        int GetState(out uint pdwState);
    }

    [Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDeviceCollection {
        int GetCount(out uint pcDevices);
        int Item(uint nDevice, [MarshalAs(UnmanagedType.Interface)] out IMMDevice ppDevice);
    }

    // IPolicyConfig - undocumented, but stable since Vista
    [Guid("F8679F50-850A-41CF-9C72-430F290290C8")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IPolicyConfig {
        int GetMixFormat(string pszDeviceName, IntPtr ppFormat);
        int GetDeviceFormat(string pszDeviceName, bool bDefault, IntPtr ppFormat);
        int ResetDeviceFormat(string pszDeviceName);
        int SetDeviceFormat(string pszDeviceName, IntPtr pEndpointFormat, IntPtr MixFormat);
        int GetProcessingPeriod(string pszDeviceName, bool bDefault, IntPtr pmftDefaultPeriod, IntPtr pmftMinimumPeriod);
        int SetProcessingPeriod(string pszDeviceName, IntPtr pmftPeriod);
        int GetShareMode(string pszDeviceName, IntPtr pMode);
        int SetShareMode(string pszDeviceName, IntPtr mode);
        int GetPropertyValue(string pszDeviceName, bool bFxStore, IntPtr key, IntPtr pv);
        int SetPropertyValue(string pszDeviceName, bool bFxStore, IntPtr key, IntPtr pv);
        int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)] string pszDeviceName, Role role);
        int SetEndpointVisibility(string pszDeviceName, bool bVisible);
    }

    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    [ClassInterface(ClassInterfaceType.None)]
    public class MMDeviceEnumeratorClass { }

    [ComImport, Guid("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9")]
    [ClassInterface(ClassInterfaceType.None)]
    public class PolicyConfigClass { }

    public static class AudioControl {

        public static string GetDefaultDeviceId(DataFlow flow, Role role) {
            var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumeratorClass();
            IMMDevice device;
            int hr = enumerator.GetDefaultAudioEndpoint(flow, role, out device);
            if (hr != 0) return null;
            string id;
            device.GetId(out id);
            Marshal.ReleaseComObject(device);
            Marshal.ReleaseComObject(enumerator);
            return id;
        }

        public static bool SetDefaultDevice(string deviceId, Role role) {
            var policy = (IPolicyConfig)new PolicyConfigClass();
            int hr = policy.SetDefaultEndpoint(deviceId, role);
            Marshal.ReleaseComObject(policy);
            return (hr == 0);
        }

        public static bool DeviceExists(string deviceId) {
            var enumerator = (IMMDeviceEnumerator)new MMDeviceEnumeratorClass();
            IMMDevice device;
            int hr = enumerator.GetDevice(deviceId, out device);
            Marshal.ReleaseComObject(enumerator);
            if (hr == 0 && device != null) {
                uint state;
                device.GetState(out state);
                Marshal.ReleaseComObject(device);
                return (state == 1); // DEVICE_STATE_ACTIVE = 1
            }
            return false;
        }
    }
}
'@

# Compile only once per run
if (-not ([System.Management.Automation.PSTypeName]'AudioWatchdog.AudioControl').Type) {
    Add-Type -TypeDefinition $csharpCode -Language CSharp 2>$null
}

# ── Logging ───────────────────────────────────────────────────────────────────
function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$ts] [$Level] $Message"
    Add-Content -Path $LOG_FILE -Value $line -Encoding UTF8
    # Also write to console/host if interactive
    if ($Host.UI.RawUI.WindowTitle -ne $null) {
        Write-Host $line
    }
}

# ── Core check function ───────────────────────────────────────────────────────
function Invoke-AudioCheck {
    # First verify Focusrite is actually plugged in and active
    $focusritePresent = [AudioWatchdog.AudioControl]::DeviceExists($TARGET_RENDER_ID)
    if (-not $focusritePresent) {
        Write-Log "Focusrite Scarlett Solo USB not active/connected — skipping correction" 'WARN'
        return
    }

    $changed = $false

    # Check render roles: Console (0), Multimedia (1), Communications (2)
    $renderRoles = @(
        [AudioWatchdog.Role]::Console,
        [AudioWatchdog.Role]::Multimedia,
        [AudioWatchdog.Role]::Communications
    )
    foreach ($role in $renderRoles) {
        $current = [AudioWatchdog.AudioControl]::GetDefaultDeviceId([AudioWatchdog.DataFlow]::Render, $role)
        if ($current -ne $TARGET_RENDER_ID) {
            $ok = [AudioWatchdog.AudioControl]::SetDefaultDevice($TARGET_RENDER_ID, $role)
            if ($ok) {
                Write-Log "FIXED Render/${role}: was '$current' -> set to '$TARGET_RENDER_NAME'" 'FIX'
                $changed = $true
            } else {
                Write-Log "FAILED to fix Render/${role}: was '$current'" 'ERROR'
            }
        }
    }

    # Check capture Communications role (so Discord/Teams mic is also Scarlett)
    $focusCapturePresent = [AudioWatchdog.AudioControl]::DeviceExists($TARGET_CAPTURE_ID)
    if ($focusCapturePresent) {
        $currentCap = [AudioWatchdog.AudioControl]::GetDefaultDeviceId([AudioWatchdog.DataFlow]::Capture, [AudioWatchdog.Role]::Communications)
        if ($currentCap -ne $TARGET_CAPTURE_ID) {
            $ok = [AudioWatchdog.AudioControl]::SetDefaultDevice($TARGET_CAPTURE_ID, [AudioWatchdog.Role]::Communications)
            if ($ok) {
                Write-Log "FIXED Capture/Communications: was '$currentCap' -> set to '$TARGET_CAPTURE_NAME'" 'FIX'
                $changed = $true
            }
        }
    }

    if (-not $changed) {
        # Uncomment the next line for verbose heartbeat logging:
        # Write-Log "OK — all audio roles correct" 'OK'
    }
}

# ── Entry point ───────────────────────────────────────────────────────────────
Write-Log "AudioWatchdog started. Monitoring every $CHECK_INTERVAL_S seconds."
Write-Log "Target render : $TARGET_RENDER_NAME ($TARGET_RENDER_ID)"
Write-Log "Target capture: $TARGET_CAPTURE_NAME ($TARGET_CAPTURE_ID)"

# Run once immediately
Invoke-AudioCheck

# Then loop
while ($true) {
    Start-Sleep -Seconds $CHECK_INTERVAL_S
    Invoke-AudioCheck
}
