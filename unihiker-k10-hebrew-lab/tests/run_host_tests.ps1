$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$compilerCommand = Get-Command g++ -ErrorAction SilentlyContinue
$compiler = if ($compilerCommand) { $compilerCommand.Source } else { $null }

if (-not $compiler) {
    $msysCompiler = 'C:\msys64\usr\bin\g++.exe'
    if (Test-Path -LiteralPath $msysCompiler) {
        $compiler = $msysCompiler
    }
}

if (-not $compiler) {
    throw 'No host g++ compiler found. Install one or add it to PATH.'
}

$buildDirectory = Join-Path $projectRoot '.host-test-build'
if (-not (Test-Path -LiteralPath $buildDirectory)) {
    New-Item -ItemType Directory -Path $buildDirectory | Out-Null
}

$testSource = Join-Path $PSScriptRoot 'dashboard_logic_tests.cpp'
$testExecutable = Join-Path $buildDirectory 'dashboard_logic_tests.exe'
$includeDirectory = Join-Path $projectRoot 'include'

if ($compiler -ieq 'C:\msys64\usr\bin\g++.exe') {
    $bash = 'C:\msys64\usr\bin\bash.exe'
    $cygpath = 'C:\msys64\usr\bin\cygpath.exe'
    $posixRoot = (& $cygpath -u $projectRoot).Trim()
    $hostCommand = "g++ -std=c++11 -Wall -Wextra -Werror -I'$posixRoot/include' '$posixRoot/tests/dashboard_logic_tests.cpp' -o '$posixRoot/.host-test-build/dashboard_logic_tests.exe' && '$posixRoot/.host-test-build/dashboard_logic_tests.exe'"
    & $bash -lc $hostCommand
    if ($LASTEXITCODE -ne 0) {
        throw "MSYS2 host logic tests failed with exit code $LASTEXITCODE"
    }
} else {
    & $compiler '-std=c++11' '-Wall' '-Wextra' '-Werror' "-I$includeDirectory" $testSource '-o' $testExecutable
    if ($LASTEXITCODE -ne 0) {
        throw "Host test compilation failed with exit code $LASTEXITCODE"
    }

    $compilerDirectory = Split-Path -Parent $compiler
    $env:PATH = "$compilerDirectory;$env:PATH"
    & $testExecutable
    if ($LASTEXITCODE -ne 0) {
        throw "Host logic tests failed with exit code $LASTEXITCODE"
    }
}

& python (Join-Path $PSScriptRoot 'test_policy.py')
if ($LASTEXITCODE -ne 0) {
    throw "Policy test failed with exit code $LASTEXITCODE"
}
