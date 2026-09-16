param(
    [switch]$ProbeWasapi
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $project '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
$requirements = Join-Path $project 'requirements-music.txt'

if (-not (Test-Path -LiteralPath $venvPython)) {
    $systemPython = (Get-Command python -ErrorAction Stop).Source
    Write-Host 'Creating isolated Python environment · יוצר סביבת Python מבודדת'
    & $systemPython -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'python -m venv failed' }
}

Write-Host 'Installing pinned local-media dependencies · מתקין תלויות מדיה נעולות גרסה'
& $venvPython -m pip install --disable-pip-version-check --require-virtualenv --requirement $requirements
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

& $venvPython -c "import aiohttp, aiortc, av, numpy, soundcard; from importlib.metadata import version; print('imports: OK'); print('aiortc', aiortc.__version__, 'PyAV', av.__version__, 'NumPy', numpy.__version__, 'SoundCard', version('SoundCard'))"
if ($LASTEXITCODE -ne 0) { throw 'Dependency import check failed' }

Write-Host 'Available Windows audio outputs · יציאות שמע זמינות ב-Windows'
& $venvPython (Join-Path $project 'music_relay.py') --list-devices
if ($LASTEXITCODE -ne 0) { throw 'Audio device enumeration failed' }

if ($ProbeWasapi) {
    Write-Host 'Opening a 20 ms WASAPI loopback probe · פותח בדיקת loopback של 20 מילישניות'
    & $venvPython (Join-Path $project 'music_relay.py') --probe
    if ($LASTEXITCODE -ne 0) { throw 'WASAPI loopback probe failed' }
}

Write-Host 'Setup complete. No service was started · ההתקנה הושלמה; לא הופעל שירות'
