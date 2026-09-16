# KESHEV gate-19 canary WAV generator - K11 (PHASE2-DESIGN.md section 9).
# Renders the 5 canary phrases from tools/privacy_canaries.py to 16kHz mono
# s16le WAV FILES via System.Speech. SetOutputToWaveFile writes to disk only -
# NO audio output device is opened, ever (Sacred Audio, scar 22).
# Output: tools/replay/wavs/canary/canary1..5.wav (dir is git-ignored).
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $repo 'tools\replay\wavs\canary'
New-Item -ItemType Directory -Force $outDir | Out-Null

# The phrases are duplicated from tools/privacy_canaries.py deliberately kept
# in sync by the audit itself: the sender confirms every phrase decodes with
# its intended rare words, so drift here turns the audit red, never silent.
$phrases = @(
    'The quixotic zeppelin hauled some marmalade.',
    'A porcupine blew the saxophone in a dirigible.',
    'The chrysanthemum tambourine hummed at dusk.',
    'My telescope showed a turquoise armadillo.',
    'The crocodile ate seventeen pistachio cupcakes.'
)

Add-Type -AssemblyName System.Speech
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono)

for ($i = 0; $i -lt $phrases.Count; $i++) {
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    try {
        $synth.Rate = -1
        $path = Join-Path $outDir ("canary{0}.wav" -f ($i + 1))
        $synth.SetOutputToWaveFile($path, $fmt)   # FILE output only
        $synth.Speak($phrases[$i])
        $synth.SetOutputToNull()
    } finally {
        $synth.Dispose()
    }
    Write-Host ("wrote {0}: {1}" -f $path, $phrases[$i])
}
Write-Host "done - $($phrases.Count) canary wavs at 16kHz mono s16le (no audio device opened)"
