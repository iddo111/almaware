# popup-forensics remediation — reversibly disable toast spam offenders.
# All edits to HKCU only (no admin escalation needed for these specific keys).
# Backup .reg files written first; reversal commands logged.

$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$logRoot = 'C:\Users\<user>\.claude\projects\D--CLAUDE\logs'
$regBackupRoot = 'C:\Users\<user>\.claude\projects\D--CLAUDE\backups\reg'
$null = New-Item -ItemType Directory -Force -Path $logRoot, $regBackupRoot
$transcript = Join-Path $logRoot ("popup-forensics-remediate-$ts.log")
$reversal = Join-Path $logRoot ("popup-forensics-remediate-$ts.reversal.txt")
Start-Transcript -Path $transcript -Append | Out-Null

Write-Output ('=== popup-forensics remediation @ ' + (Get-Date -Format o) + ' ===')

# Targets: AUMIDs whose toasts are currently default-ON (Enabled = unset/null = treated ON).
# Each key gets Enabled=0 (DWORD). Reversal: delete the value or set =1.
$targets = @(
    'Microsoft.YourPhone_8wekyb3d8bbwe!YourPhoneMessages_29e270dc-4a97-4347-bddf-6938cc6d6b73',
    'Microsoft.YourPhone_8wekyb3d8bbwe!YourPhoneNotifications_com.anthropic.claude',
    'Microsoft.YourPhone_8wekyb3d8bbwe!YourPhoneNotifications_com.einnovation.temu',
    'Microsoft.YourPhone_8wekyb3d8bbwe!YourPhoneNotifications_com.whatsapp',
    'MicrosoftWindows.CrossDevice_cw5n1h2txyewy!NewPhotoToast_29e270dc-4a97-4347-bddf-6938cc6d6b73',
    'Windows.SystemToast.DefaultAudioEndpoint'
)

# Some targets we are NOT touching even if "ENABLED unset":
#   - Chrome (some web apps depend on toasts)
#   - WhatsApp UWP (Iddo uses)
#   - Claude (Iddo uses)
#   - Microsoft.WSL (rare; benign)
#   - immersivecontrolpanel (Settings app)
#   - NotifyIconGenerated... (tray icons; can't tell which app -- leave)

$base = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings'

# Reg-export the whole Settings subtree as a single backup (cheaper than per-key).
$bak = Join-Path $regBackupRoot ("Notifications-Settings-$ts.reg")
& reg.exe export 'HKCU\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings' $bak /y | Out-Null
Write-Output ("BACKUP: $bak")

# Build reversal lines header
$rev = @()
$rev += "# Reversal commands for popup-forensics remediation $ts"
$rev += "# To restore the original (toasts default-on) state for these AUMIDs:"
$rev += "# Option A: import the backup .reg"
$rev += ('reg import "' + $bak + '"')
$rev += ''
$rev += "# Option B: per-key delete the Enabled value (re-defaults to ON)"

foreach ($aumid in $targets) {
    $key = Join-Path $base $aumid
    if (-not (Test-Path $key)) {
        # create the key so we can pin Enabled=0
        try {
            New-Item -Path $key -Force | Out-Null
            Write-Output ("CREATED: $key")
        } catch {
            Write-Output ("ERR-CREATE: $key -- $($_.Exception.Message)")
            continue
        }
    }
    try {
        $existing = (Get-ItemProperty -LiteralPath $key -Name Enabled -ErrorAction SilentlyContinue).Enabled
        Set-ItemProperty -LiteralPath $key -Name Enabled -Value 0 -Type DWord -Force
        Write-Output ("SET Enabled=0 (was: $existing) -- $aumid")
        if ($null -eq $existing) {
            $rev += ('Remove-ItemProperty -LiteralPath "' + $key + '" -Name Enabled -ErrorAction SilentlyContinue')
        } else {
            $rev += ('Set-ItemProperty -LiteralPath "' + $key + '" -Name Enabled -Value ' + $existing + ' -Type DWord -Force')
        }
    } catch {
        Write-Output ("ERR-SET: $aumid -- $($_.Exception.Message)")
    }
}

$rev | Set-Content -LiteralPath $reversal -Encoding UTF8
Write-Output ("REVERSAL FILE: $reversal")

Stop-Transcript | Out-Null
Write-Output ("TRANSCRIPT: $transcript")
exit 0
