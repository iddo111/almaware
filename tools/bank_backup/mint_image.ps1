# mint_image.ps1 - Option-a: full disk image of \\.\PhysicalDrive1 (Mint SSD)
# Requires:
#   - VM SHUT DOWN (raw passthrough disk must be free)
#   - PowerShell as ADMINISTRATOR (raw disk access)
#   - WSL with zstd installed
# ASCII only, no em-dashes.
#
# To run: shut down the Mint VM in VirtualBox, then open PowerShell as Admin
# and run:
#     powershell -ExecutionPolicy Bypass -File D:\CLAUDE\tools\bank_backup\mint_image.ps1
#
# Output: N:\mint-ssd\image-YYYY-MM-DD.img.zst + .sha256 manifest

$ErrorActionPreference = 'Stop'
$ts = Get-Date -Format 'yyyy-MM-dd-HHmmss'
$dest = "N:\mint-ssd\image-$ts.img.zst"
$sha  = "N:\mint-ssd\image-$ts.sha256"

# Check admin
$me = [Security.Principal.WindowsIdentity]::GetCurrent()
$prin = New-Object Security.Principal.WindowsPrincipal($me)
if (-not $prin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Must be run as Administrator. Right-click PowerShell -> Run as administrator."
    exit 1
}

# Check VM is NOT running
$vbm = 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe'
if (Test-Path $vbm) {
    $running = & $vbm list runningvms 2>$null
    if ($running -match 'Mint') {
        Write-Error "Mint VM is still running. Shut it down in VirtualBox first."
        exit 1
    }
}

# Check WSL + zstd
$rc = (& wsl.exe -e which zstd 2>$null)
if (-not $rc) {
    Write-Output "Installing zstd in WSL..."
    & wsl.exe -e sudo -n apt-get install -y zstd
}

Write-Output "Imaging \\.\PhysicalDrive1 -> $dest"
Write-Output "Started: $(Get-Date)"

# Use dd via WSL (it can read /dev/sdX raw, but here we want PhysicalDrive1
# which translates to /dev/sda or /dev/sdb in WSL2 -- depends on mount.
# Safer: use PowerShell raw read.

# Approach: use 7zip or built-in to read raw and pipe through zstd in WSL.
# Use [System.IO.File] streaming.

$rawStream = New-Object System.IO.FileStream('\\.\PhysicalDrive1',
    [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::Read,
    [System.IO.FileShare]::Read)

# zstd compression via WSL
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'wsl.exe'
$psi.Arguments = '-e zstd -19 -T0 -o ' + ($dest -replace '\\','/').Replace('N:','/mnt/n')
$psi.RedirectStandardInput = $true
$psi.UseShellExecute = $false
$zstd = [System.Diagnostics.Process]::Start($psi)

$buf = New-Object byte[] 16777216  # 16MB
$totalBytes = 0L
$start = Get-Date
try {
    while ($true) {
        $n = $rawStream.Read($buf, 0, $buf.Length)
        if ($n -le 0) { break }
        $zstd.StandardInput.BaseStream.Write($buf, 0, $n)
        $totalBytes += $n
        if (($totalBytes % (1GB)) -lt 16MB) {
            $elapsed = (Get-Date) - $start
            Write-Output ("  {0} GB read in {1:N1}s ({2:N1} MB/s)" -f ($totalBytes / 1GB), $elapsed.TotalSeconds, ($totalBytes / 1MB / $elapsed.TotalSeconds))
        }
    }
} finally {
    $zstd.StandardInput.Close()
    $rawStream.Close()
    $zstd.WaitForExit()
}

# SHA-256 the compressed image
Write-Output "Computing SHA-256 of compressed image..."
$h = Get-FileHash -Algorithm SHA256 -LiteralPath $dest
"$($h.Hash)  $dest" | Out-File $sha -Encoding ASCII
Write-Output "Done. Image: $dest"
Write-Output "SHA-256:    $($h.Hash)"
Write-Output "Total raw:  $totalBytes bytes"
Write-Output "Elapsed:    $((Get-Date) - $start)"
