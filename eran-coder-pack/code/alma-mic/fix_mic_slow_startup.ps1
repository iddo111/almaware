# Run this in an elevated (Run as administrator) PowerShell.
# Fixes alma-mic's ~22s startup delay: Windows Defender real-time-scans the
# 59MB ctranslate2.dll (faster-whisper's native backend) on every process start.
Add-MpPreference -ExclusionPath "C:\Users\<user>\AppData\Local\Programs\Python\Python313\Lib\site-packages\ctranslate2"
Write-Host "Exclusion added. Verify:" -ForegroundColor Green
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
