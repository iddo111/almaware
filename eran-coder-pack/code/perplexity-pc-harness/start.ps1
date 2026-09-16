[CmdletBinding()]
param(
    [string]$Prompt,
    [string]$Model = 'perplexity/sonar',
    [switch]$DryRun,
    [switch]$ObserveOnly
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Get-Command python -ErrorAction Stop
$secretPointer = [IntPtr]::Zero
$promptedKey = $false
$priorApiKey = $env:PERPLEXITY_API_KEY

try {
    if ([string]::IsNullOrWhiteSpace($env:PERPLEXITY_API_KEY)) {
        $secureKey = Read-Host 'Perplexity API key (memory only; not saved)' -AsSecureString
        $secretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        $env:PERPLEXITY_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPointer)
        $promptedKey = $true
    }

    $arguments = @((Join-Path $projectDir 'harness.py'), '--model', $Model)
    if ($DryRun) {
        $arguments += '--dry-run'
    }
    if ($ObserveOnly) {
        $arguments += '--observe-only'
    }
    if (-not [string]::IsNullOrWhiteSpace($Prompt)) {
        $arguments += $Prompt
    }
    & $python.Source @arguments
    exit $LASTEXITCODE
}
finally {
    if ($promptedKey) {
        Remove-Item Env:PERPLEXITY_API_KEY -ErrorAction SilentlyContinue
    }
    elseif ($null -ne $priorApiKey) {
        $env:PERPLEXITY_API_KEY = $priorApiKey
    }
    if ($secretPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPointer)
    }
}
