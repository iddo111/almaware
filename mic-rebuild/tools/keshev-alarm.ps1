<#
    KESHEV ALARM — the window Iddo actually SEES when the mic is broken.

    Born 2026-08-17. The watchdog's old ALARM was a line in state\watchdog.log
    — the 04:06 scar with one file's indirection: a whole night of dictation
    lost while the report of the loss sat unread on disk. When the watchdog
    cannot fix the mic (restarts held, exhausted, or forbidden), a HUMAN must
    know NOW, in his eyeline.

    LAWS HONORED:
      * SACRED AUDIO — this script makes NO sound. No beep, no MessageBox
        (MessageBoxW plays the system sound), no SystemSounds. A bright
        topmost window only.
      * CLICKABLE-ACCESS — no paths for him to click; one button restarts
        KESHEV FOR him, one dismisses.
      * The restart button routes through RUN-KESHEV.cmd — the same single
        entry point the watchdog and the human use. No new launch mechanism.

    Invoked by tools\keshev-watchdog.ps1 (Show-Alarm). Test: -SelfTest builds
    the whole window without showing it and prints ALARM-SELFTEST-OK.
#>
param(
    [string]$Verdict = 'FAULT',
    [string]$Detail = '',
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
$ROOT   = Split-Path -Parent $PSScriptRoot
$RUNNER = Join-Path $ROOT 'RUN-KESHEV.cmd'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text            = 'KESHEV'
$form.StartPosition   = 'CenterScreen'
$form.TopMost         = $true
$form.MinimizeBox     = $false
$form.MaximizeBox     = $false
$form.FormBorderStyle = 'FixedDialog'
$form.ClientSize      = New-Object System.Drawing.Size(640, 300)
$form.BackColor       = [System.Drawing.Color]::White

$title = New-Object System.Windows.Forms.Label
$title.Text      = "KESHEV IS $Verdict — THE MIC IS NOT WORKING"
$title.Font      = New-Object System.Drawing.Font('Segoe UI', 20, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(185, 28, 28)   # bright red on white
$title.AutoSize  = $false
$title.TextAlign = 'MiddleCenter'
$title.Dock      = 'Top'
$title.Height    = 70

$hebrew = New-Object System.Windows.Forms.Label
$hebrew.Text      = 'קשב לא שומע אותך — מה שאתה אומר עכשיו לא נקלט'
$hebrew.Font      = New-Object System.Drawing.Font('Segoe UI', 15, [System.Drawing.FontStyle]::Bold)
$hebrew.ForeColor = [System.Drawing.Color]::FromArgb(17, 24, 39)
$hebrew.AutoSize  = $false
$hebrew.TextAlign = 'MiddleCenter'
$hebrew.RightToLeft = 'Yes'
$hebrew.Dock      = 'Top'
$hebrew.Height    = 44

$body = New-Object System.Windows.Forms.Label
$body.Text      = "$Detail`n$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  ·  the watchdog could not fix this by restarting"
$body.Font      = New-Object System.Drawing.Font('Segoe UI', 10)
$body.ForeColor = [System.Drawing.Color]::FromArgb(55, 65, 81)
$body.AutoSize  = $false
$body.TextAlign = 'MiddleCenter'
$body.Dock      = 'Top'
$body.Height    = 80

$panel = New-Object System.Windows.Forms.FlowLayoutPanel
$panel.Dock          = 'Bottom'
$panel.Height        = 78
$panel.FlowDirection = 'LeftToRight'
$panel.Padding       = New-Object System.Windows.Forms.Padding(60, 12, 12, 12)

$btnRestart = New-Object System.Windows.Forms.Button
$btnRestart.Text      = 'הפעל את קשב מחדש  ·  Restart KESHEV now'
$btnRestart.Font      = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
$btnRestart.BackColor = [System.Drawing.Color]::FromArgb(22, 101, 52)
$btnRestart.ForeColor = [System.Drawing.Color]::White
$btnRestart.FlatStyle = 'Flat'
$btnRestart.Size      = New-Object System.Drawing.Size(340, 52)
$btnRestart.Add_Click({
    Start-Process -FilePath $RUNNER -WorkingDirectory $ROOT
    $form.Close()
})

$btnDismiss = New-Object System.Windows.Forms.Button
$btnDismiss.Text      = 'הבנתי  ·  Dismiss'
$btnDismiss.Font      = New-Object System.Drawing.Font('Segoe UI', 12)
$btnDismiss.BackColor = [System.Drawing.Color]::FromArgb(229, 231, 235)
$btnDismiss.ForeColor = [System.Drawing.Color]::FromArgb(17, 24, 39)
$btnDismiss.FlatStyle = 'Flat'
$btnDismiss.Size      = New-Object System.Drawing.Size(180, 52)
$btnDismiss.Add_Click({ $form.Close() })

$panel.Controls.Add($btnRestart)
$panel.Controls.Add($btnDismiss)

$form.Controls.Add($body)
$form.Controls.Add($hebrew)
$form.Controls.Add($title)
$form.Controls.Add($panel)

if ($SelfTest) {
    # Prove the window BUILDS (fonts, colors, handlers, runner path resolved)
    # without stealing focus or flashing anything — the focus-courtesy
    # guardrail applies to alarms too, until a real fault earns the intrusion.
    if (-not (Test-Path $RUNNER)) {
        Write-Output "ALARM-SELFTEST-FAIL: runner missing at $RUNNER"
        exit 1
    }
    Write-Output 'ALARM-SELFTEST-OK'
    $form.Dispose()
    exit 0
}

[void]$form.ShowDialog()
