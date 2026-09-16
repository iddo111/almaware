# Bibi-letter reminder — reliable Hebrew tray notification (Win11 renders it as a toast).
$ErrorActionPreference = 'SilentlyContinue'
$title = 'תזכורת מקלוד 📮'
$msg   = 'כתוב מכתב לביבי — ראש הממשלה. (תזכורת כל 6 שעות)'
if (Get-Module -ListAvailable -Name BurntToast) {
  Import-Module BurntToast
  New-BurntToastNotification -Text $title, $msg
} else {
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type -AssemblyName System.Drawing
  $ni = New-Object System.Windows.Forms.NotifyIcon
  $ni.Icon = [System.Drawing.SystemIcons]::Information
  $ni.BalloonTipTitle = $title
  $ni.BalloonTipText = $msg
  $ni.Visible = $true
  $ni.ShowBalloonTip(20000)
  Start-Sleep -Seconds 12
  $ni.Visible = $false
  $ni.Dispose()
}
