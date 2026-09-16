# SDR wideband power sweep -> CSV -> PNG waterfall.
# Usage:  pwsh -File scan.ps1 88 108 25k     (start_MHz end_MHz binsize)
#         pwsh -File scan.ps1 433 435 5k     (the ISM band our 433 modules use)
param(
    [double]$StartMHz = 88,
    [double]$EndMHz   = 108,
    [string]$Bin      = "25k",
    [int]$Seconds     = 20
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$bin  = Join-Path $here "bin\rtl_power.exe"
$stamp = "{0:yyyyMMdd_HHmmss}" -f (Get-Date)
$csv  = Join-Path $here "captures\sweep_${StartMHz}-${EndMHz}MHz_$stamp.csv"

# device check first — clear message instead of a cryptic failure
$probe = & (Join-Path $here "bin\rtl_test.exe") 2>&1 | Out-String
if ($probe -match "No supported devices") {
    Write-Host "NO DONGLE DETECTED. Plug in the RTL-SDR, run zadig (bin\zadig-2.9.exe ->" -ForegroundColor Yellow
    Write-Host "select 'Bulk-In, Interface (0)' -> WinUSB -> Replace Driver), then retry." -ForegroundColor Yellow
    exit 1
}

Write-Host "Sweeping $StartMHz-$EndMHz MHz, bin=$Bin, ${Seconds}s -> $csv"
& $bin -f "${StartMHz}M:${EndMHz}M:$Bin" -g 40 -i 1 -e $Seconds $csv
Write-Host "done. Plot it:  python plot_sweep.py `"$csv`""
