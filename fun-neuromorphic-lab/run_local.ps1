$ErrorActionPreference = 'Stop'
$labDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvDir = Join-Path $labDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv $venvDir
}

& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $labDir 'requirements-local.txt')
& $venvPython (Join-Path $labDir 'memristor_crossbar_demo.py')
& $venvPython (Join-Path $labDir 'spiking_lif_demo.py')
& $venvPython (Join-Path $labDir 'reservoir_demo.py')

