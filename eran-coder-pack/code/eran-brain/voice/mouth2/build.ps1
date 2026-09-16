# build.ps1 -- build the MOUTH v2 fast C twin on the PC (Windows).
#
# Needs a REAL x86-64 gcc (mingw-w64). Checked 2026-08-26: this PC's only
# `gcc` on PATH is FPC's bundled i386 gcc 2.95 (C:\FPC\...) -- unusable.
# If you install mingw-w64 (e.g. winget install BrechtSanders.WinLibs.POSIX.UCRT
# or MSYS2), this script will find it and build voc_eran.dll.
#
# -ffp-contract=off is REQUIRED (FMA changes bits; the parity gate is a
# bit-level diff). NO -ffast-math, ever.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$gcc = $null
foreach ($cand in @((Get-Command gcc -ErrorAction SilentlyContinue).Source,
                    "C:\msys64\mingw64\bin\gcc.exe",
                    "C:\msys64\ucrt64\bin\gcc.exe",
                    "C:\mingw64\bin\gcc.exe")) {
    if ($cand -and (Test-Path $cand)) {
        # refuse the FPC i386 gcc 2.95 -- it cannot build a win64 DLL
        if ($cand -like "*FPC*") { continue }
        $v = & $cand -dumpmachine 2>$null
        if ($v -like "*x86_64*") { $gcc = $cand; break }
    }
}
if (-not $gcc) {
    Write-Host "no usable x86-64 gcc found on this PC -- PC build SKIPPED."
    Write-Host "(the C twin builds and is gated on eran2 via build.sh)"
    exit 1
}
& $gcc -O2 -shared -ffp-contract=off -fno-fast-math `
    -o voc_eran.dll voc_eran.c -lm
Write-Host "built voc_eran.dll with $gcc"
