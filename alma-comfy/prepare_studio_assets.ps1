[CmdletBinding()]
param(
    [ValidateSet('Audit', 'Prepare')]
    [string]$Mode = 'Audit',
    [ValidateSet('dgx3', 'dgx4', 'all')]
    [string]$Node = 'all',
    [string[]]$Asset = @(),
    [switch]$Offline,
    [switch]$FullHash,
    [switch]$SkipSources,
    [switch]$SkipEnvironments,
    [switch]$SkipTools,
    [switch]$SkipComfyLinks,
    [string]$ProjectLoras,
    [string[]]$LicenseReceipt = @()
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Lock = Join-Path $Root 'studio_assets.lock.json'
$Helper = Join-Path $Root 'tools\studio_asset_preparer.py'
$ReceiptRoot = Join-Path $Root 'provenance\studio-asset-preparation'

foreach ($required in @($Lock, $Helper)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required bootstrap file is missing: $required"
    }
}
if ($ProjectLoras -and -not (Test-Path -LiteralPath $ProjectLoras -PathType Leaf)) {
    throw "Project LoRA allowlist is missing: $ProjectLoras"
}
foreach ($receipt in $LicenseReceipt) {
    if (-not (Test-Path -LiteralPath $receipt -PathType Leaf)) {
        throw "License receipt is missing: $receipt"
    }
}

$Targets = @{
    dgx3 = @{ Ssh = 'eran3@<lan-ip>'; Bootstrap = '/home/eran3/alma-studio/bootstrap' }
    dgx4 = @{ Ssh = 'eran4@<lan-ip>'; Bootstrap = '/home/eran4/alma-studio/bootstrap' }
}
$SelectedNodes = if ($Node -eq 'all') { @('dgx3', 'dgx4') } else { @($Node) }
if ($ProjectLoras -and $SelectedNodes -contains 'dgx4') {
    throw 'Project LoRAs are DGX3-only; run with -Node dgx3.'
}

New-Item -ItemType Directory -Path $ReceiptRoot -Force | Out-Null
$Stamp = (Get-Date -Format 'yyyyMMddTHHmmssK').Replace(':', '')
$Results = @()

foreach ($NodeId in $SelectedNodes) {
    $Target = $Targets[$NodeId]
    $RemoteRoot = $Target.Bootstrap
    $RemoteLock = "$RemoteRoot/studio_assets.lock.json"
    $RemoteHelper = "$RemoteRoot/studio_asset_preparer.py"
    $RemoteReceipt = "$RemoteRoot/receipts/$Stamp-$NodeId-$($Mode.ToLowerInvariant()).json"

    & ssh -o BatchMode=yes -o ConnectTimeout=8 $Target.Ssh "mkdir -p '$RemoteRoot/receipts'"
    if ($LASTEXITCODE -ne 0) { throw "Could not create scoped bootstrap directory on $NodeId" }

    & scp -q -o BatchMode=yes -o ConnectTimeout=8 -- $Lock "$($Target.Ssh):$RemoteLock.tmp"
    if ($LASTEXITCODE -ne 0) { throw "Could not copy asset lock to $NodeId" }
    & scp -q -o BatchMode=yes -o ConnectTimeout=8 -- $Helper "$($Target.Ssh):$RemoteHelper.tmp"
    if ($LASTEXITCODE -ne 0) { throw "Could not copy preparer to $NodeId" }
    & ssh -o BatchMode=yes -o ConnectTimeout=8 $Target.Ssh "mv '$RemoteLock.tmp' '$RemoteLock' && mv '$RemoteHelper.tmp' '$RemoteHelper'"
    if ($LASTEXITCODE -ne 0) { throw "Could not atomically install bootstrap files on $NodeId" }

    $RemoteArgs = @(
        'python3', $RemoteHelper,
        '--lock', $RemoteLock,
        '--node', $NodeId,
        '--mode', $Mode.ToLowerInvariant(),
        '--receipt', $RemoteReceipt
    )
    foreach ($AssetId in $Asset) {
        if ($AssetId -notmatch '^[a-z0-9][a-z0-9.-]*$') { throw "Unsafe asset id: $AssetId" }
        $RemoteArgs += @('--asset', $AssetId)
    }
    if ($Offline) { $RemoteArgs += '--offline' }
    if ($FullHash) { $RemoteArgs += '--full-hash' }
    if ($SkipSources) { $RemoteArgs += '--skip-sources' }
    if ($SkipEnvironments) { $RemoteArgs += '--skip-environments' }
    if ($SkipTools) { $RemoteArgs += '--skip-tools' }
    if ($SkipComfyLinks) { $RemoteArgs += '--skip-comfy-links' }

    if ($ProjectLoras) {
        $ProjectName = [IO.Path]::GetFileName($ProjectLoras)
        if ($ProjectName -notmatch '^[A-Za-z0-9._-]+\.json$') { throw 'Unsafe project allowlist filename.' }
        $RemoteProject = "$RemoteRoot/$ProjectName"
        & scp -q -o BatchMode=yes -o ConnectTimeout=8 -- $ProjectLoras "$($Target.Ssh):$RemoteProject"
        if ($LASTEXITCODE -ne 0) { throw 'Could not copy project LoRA allowlist.' }
        $RemoteArgs += @('--project-loras', $RemoteProject)
    }
    foreach ($LocalLicenseReceipt in $LicenseReceipt) {
        $ReceiptName = [IO.Path]::GetFileName($LocalLicenseReceipt)
        if ($ReceiptName -notmatch '^[A-Za-z0-9._-]+\.json$') { throw 'Unsafe license receipt filename.' }
        $RemoteLicenseReceipt = "$RemoteRoot/$ReceiptName"
        & scp -q -o BatchMode=yes -o ConnectTimeout=8 -- $LocalLicenseReceipt "$($Target.Ssh):$RemoteLicenseReceipt"
        if ($LASTEXITCODE -ne 0) { throw "Could not copy license receipt to $NodeId" }
        $RemoteArgs += @('--license-receipt', $RemoteLicenseReceipt)
    }

    # All arguments are either hard-coded paths or validated identifiers.
    if ($RemoteArgs | Where-Object { $_ -match "'" }) {
        throw 'A remote argument contains a forbidden quote character.'
    }
    $Quoted = $RemoteArgs | ForEach-Object { "'$_'" }
    & ssh -o BatchMode=yes -o ConnectTimeout=8 $Target.Ssh ($Quoted -join ' ')
    $RemoteExit = $LASTEXITCODE

    $LocalReceipt = Join-Path $ReceiptRoot "$Stamp-$NodeId-$($Mode.ToLowerInvariant()).json"
    & scp -q -o BatchMode=yes -o ConnectTimeout=8 -- "$($Target.Ssh):$RemoteReceipt" $LocalReceipt
    if ($LASTEXITCODE -ne 0) { throw "Could not retrieve preparation receipt from $NodeId" }
    $Results += [pscustomobject]@{
        Node = $NodeId
        Mode = $Mode
        ExitCode = $RemoteExit
        Receipt = $LocalReceipt
    }
}

$Results | Format-Table -AutoSize
if ($Results.ExitCode | Where-Object { $_ -ne 0 }) { exit 2 }
