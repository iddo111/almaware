[CmdletBinding()]
param(
    [string]$ProjectRoot = $PSScriptRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$resolvedProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
$pythonCommand = Get-Command python -ErrorAction Stop

function Invoke-PythonStep {
    param([Parameter(Mandatory)][string[]]$PythonArguments)

    & $pythonCommand.Source @PythonArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python step failed with exit code ${LASTEXITCODE}: $($PythonArguments -join ' ')"
    }
}

Push-Location -LiteralPath $resolvedProject
try {
    Invoke-PythonStep -PythonArguments @(
        'corpus.py', 'validate', '--root', 'recordings',
        '--manifest', 'recordings\manifest.json'
    )
    Invoke-PythonStep -PythonArguments @(
        '-m', 'unittest', 'discover', '-s', 'tests', '-v'
    )
    Invoke-PythonStep -PythonArguments @(
        'colony.py', 'train', '--recordings', 'recordings',
        '--manifest', 'recordings\manifest.json', '--state', 'state'
    )
    Invoke-PythonStep -PythonArguments @(
        'acceptance.py', '--project', '.',
        '--output', 'state\acceptance-current.json'
    )
    Write-Output 'STAGE1_LOAD_COMPLETE_FULL_PRODUCT_PARTIAL'
}
finally {
    Pop-Location
}
