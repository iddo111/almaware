<#
  Conservative daily PC maintenance: collect health evidence and remove only
  disposable temporary files older than seven days.  It never edits Registry,
  drivers, Windows Update state, or user documents.
#>
$ErrorActionPreference = 'Continue'
$logDir = Join-Path $PSScriptRoot 'reports'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$log = Join-Path $logDir "pc-health-$stamp.txt"

function Write-Report {
  param([Parameter(ValueFromPipeline = $true)] $value)
  process { $value | Out-String -Width 220 | Tee-Object -FilePath $log -Append }
}

"PC daily maintenance — $(Get-Date -Format o)" | Tee-Object -FilePath $log
"\n== Storage ==" | Tee-Object -FilePath $log -Append
Get-Volume | Where-Object DriveLetter | Select-Object DriveLetter,FileSystem,HealthStatus,@{N='FreeGB';E={[math]::Round($_.SizeRemaining/1GB,1)}},@{N='SizeGB';E={[math]::Round($_.Size/1GB,1)}} | Write-Report
Get-PhysicalDisk | Select-Object FriendlyName,MediaType,HealthStatus,OperationalStatus | Write-Report

"\n== Windows Update candidates (report only) ==" | Tee-Object -FilePath $log -Append
$session = New-Object -ComObject Microsoft.Update.Session
$result = $session.CreateUpdateSearcher().Search('IsInstalled=0 and IsHidden=0')
$result.Updates | Select-Object Title,IsDownloaded,RebootRequired | Write-Report

"\n== Device errors ==" | Tee-Object -FilePath $log -Append
Get-PnpDevice -PresentOnly | Where-Object Status -ne 'OK' | Select-Object Class,FriendlyName,Status,InstanceId | Write-Report

"\n== Printers ==" | Tee-Object -FilePath $log -Append
$printers = Get-Printer | Where-Object { $_.Name -match 'Brother|HP|Canon|Epson' }
$printerRows = foreach ($printer in $printers) {
  $jobs = @(Get-PrintJob -PrinterName $printer.Name -ErrorAction SilentlyContinue)
  [pscustomobject]@{
    Name = $printer.Name
    Status = $printer.PrinterStatus
    Offline = $printer.WorkOffline
    QueuedJobs = $jobs.Count
    Port = $printer.PortName
  }
}
$printerRows | Write-Report

"\n== Recent system errors (24h) ==" | Tee-Object -FilePath $log -Append
Get-WinEvent -FilterHashtable @{LogName='System';StartTime=(Get-Date).AddHours(-24);Level=1,2} -ErrorAction SilentlyContinue |
  Select-Object -First 40 TimeCreated,Id,ProviderName,LevelDisplayName,Message | Write-Report

"\n== Safe temporary-file cleanup ==" | Tee-Object -FilePath $log -Append
$cutoff = (Get-Date).AddDays(-7)
$tempRoots = @($env:TEMP, "$env:WINDIR\Temp") | Where-Object { Test-Path $_ } | Select-Object -Unique
$removed = 0L
foreach ($root in $tempRoots) {
  Get-ChildItem -LiteralPath $root -Force -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    ForEach-Object {
      $length = $_.Length
      Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
      if (-not (Test-Path -LiteralPath $_.FullName)) { $script:removed += $length }
    }
}
"Removed temp files: $([math]::Round($removed / 1MB, 1)) MB" | Tee-Object -FilePath $log -Append
"Report: $log" | Tee-Object -FilePath $log -Append
