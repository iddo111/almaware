# Listen to a station live through the PC speakers (or record it).
# Usage:  pwsh -File listen_fm.ps1 100.5          (FM broadcast, wideband)
#         pwsh -File listen_fm.ps1 100.5 wav      (also save a .wav)
#         pwsh -File listen_fm.ps1 446.0 nfm      (narrowband — walkie / PMR)
param(
    [double]$MHz = 100.5,
    [string]$Mode = "wfm",      # wfm = broadcast FM ; nfm = narrow (voice radios)
    [switch]$Wav
)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$rtlfm = Join-Path $here "bin\rtl_fm.exe"
$stamp = "{0:yyyyMMdd_HHmmss}" -f (Get-Date)

if ($Mode -eq "wfm") { $samp = "200k"; $resamp = "48k"; $extra = @() }
else                 { $samp = "12k";  $resamp = "48k"; $extra = @("-l","0") }

# ffmpeg plays the raw audio stream rtl_fm emits on stdout
$rtlArgs = @("-f","${MHz}M","-M",$Mode,"-s",$samp,"-r",$resamp,"-g","40") + $extra + @("-")
Write-Host "Tuning $MHz MHz ($Mode).  Ctrl+C to stop."
if ($Wav) {
    $wav = Join-Path $here "captures\listen_${MHz}MHz_$stamp.wav"
    Write-Host "recording -> $wav"
    & $rtlfm @rtlArgs | ffmpeg -f s16le -ar $resamp -ac 1 -i - -y $wav
} else {
    & $rtlfm @rtlArgs | ffmpeg -f s16le -ar $resamp -ac 1 -i - -f wav - | ffplay -nodisp -autoexit -
}
