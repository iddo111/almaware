# corpus-big/human — Iddo's own Hebrew recordings

16 kHz mono PCM16 WAV. Built alongside `recordings/`; nothing in `recordings/`
or `state/` was modified.

## Provenance — all of it is Iddo's own material

| source | what it is | original format |
|---|---|---|
| `kafe` | `D:\קפה-קלוד\*.WAV` — the Cafe-Claude ideation sessions | 48 kHz stereo PCM16 |
| `vinput` | `D:\CLAUDE\voice-input\profiles\iddo1\samples\*.wav` — dictation capture | 16 kHz mono PCM16 |
| `almamic` | `D:\CLAUDE\alma-mic\voice_corpus\*.wav` — alma-mic dictation capture | 16 kHz mono PCM16 |

Nothing scraped, nothing licensed, nothing third-party. No YouTube, no Spotify.

## What was deliberately EXCLUDED

**Synthetic — must never enter the human corpus.** These *pass* every acoustic
quality metric, because imitating speech is exactly what they were trained to do.
They can only be excluded by path:

- `D:\CLAUDE\eran-audio\babbles\` (1394 files) — Eran model babble
- `D:\CLAUDE\eran-audio\grounded_ah\output\` (51 files)
- `D:\CLAUDE\eran-audio\babble_latest.wav`, `babble_untrained_reference.wav`
- `C:\Users\<user>\Desktop\Eran-First-Voice\`, `Eran-Nursery\mirror-babble\`,
  `_Organized\Eran-Media\eran-*.wav` / `yigael-*.wav`, `Eran-AH-*.wav`
- `D:\CLAUDE\voice-ant-farm\fire\` — ant output, never human
- `D:\CLAUDE\ai-sensory-deprivation\dream_out\`

**Derived duplicates of material already included** — including these would put
the same recording in two splits and inflate every score:

- `D:\קפה-קלוד\cleaned\` (32 mp3 + 1 wav) — re-encodes of the root WAVs
- `C:\Users\<user>\Desktop\Cafe-Claude-Show\_work\seg\` — segments of the 2026-06-25 session
- `C:\Users\<user>\Desktop\קפה קלוד - נקי\` — mp3 renders of the same sessions
- `Cafe-Claude-Show1.mp3`, `Cafe-Claude-Show2.mp3` — edited programme renders

**Music / silence** — rejected by the quality filter (see below).

**Licensing-excluded**: `D:\CLAUDE\downloads\youtube\` was found and not used.

**Quarantined, not used**: `_unverified_provenance/` holds
`eran-audio\heard\cheder\{letters_heb,syllables_heb}.wav`. They sound like a male
voice reading Hebrew letters and syllables and would be unusually useful material,
but both files were remuxed through ffmpeg so their origin metadata is gone and I
could not prove they are recorded rather than TTS. They are **not** in any split.
If Iddo confirms he recorded them, move them into `train/`.

## Quality filter (`audioqc.py`, pure numpy)

Per file/segment: duration, RMS dBFS, peak, DC offset, clipping (runs of >=3
samples at the rail), envelope dynamic range as SNR proxy, speech-active
fraction, voiced fraction + median F0 (FFT autocorrelation), 2–8 Hz syllabic
modulation, spectral centroid variation, spectral flatness.

Reject if: `duration < 1 s`, `RMS < -48 dBFS`, `clipped run fraction > 0.5 %`,
`speech-active fraction < 10 %`, `SNR < 12 dB`, `voiced fraction < 12 %`,
`2–8 Hz modulation < 0.07` (files >= 4 s only), or the music signature
(`voiced > 0.85` and `centroid CV < 0.40` and `SNR < 20`).

Thresholds were calibrated against known-good speech (the existing 253 s
corpus), known music (`heard_music_wav/bach`, `hamalach`) and known silence
(`heard_a70/*`): all 10 speech files pass, both music files and all silence are
rejected.

## Splitting — whole calendar-date sessions

`session_id` is the **calendar date**, shared across *all* sources. A random
split, or even a per-source split, would put the same speaking occasion in both
train and heldout and inflate every number.

Sessions 2026-06-18 (train), 2026-06-24 + 2026-06-25 (heldout) and 2026-07-01
(evaluation) are **pinned** to the assignment already used by `recordings/`, so
previously reported results stay comparable.

Long-form `kafe` recordings are VAD-segmented into speech spans (max 20 s, split
at the quietest interior frame; gaps < 0.35 s merged; 0.2 s padding). Every
segment carries `source_path` + `source_offset_s`, so each one is traceable to
its exact position in the original recording.

## Result

| | files | hours |
|---|---|---|
| **before** (`recordings/`) | 24 | **0.070** (252.7 s) |
| **after** (`corpus-big/human/`) | 23,683 | **33.651** |

479x more audio. 3.7 GB on disk.

| split | files | hours |
|---|---|---|
| train | 18,146 | 26.746 |
| heldout | 1,903 | 3.552 |
| evaluation | 3,618 | 3.325 |
| `_unverified_provenance` | 16 | 0.028 (not in any split) |

Scanned 38.0 h raw; 33.65 h accepted, 3,107 items rejected:

| reason | n | seconds |
|---|---|---|
| too_short (<1 s) | 1,439 | 1,065 |
| silence_low_level | 613 | 1,663 |
| low_snr_or_continuous | 321 | 2,038 |
| clipped | 205 | 1,096 |
| not_speech_unvoiced | 204 | 1,059 |
| music_like | 172 | 1,134 |
| duplicate_audio | 77 | 648 |
| not_speech_no_syllabic_rhythm | 66 | 393 |
| no_speech_activity | 10 | 21 |

Verified after the build: no session spans two splits; no source file contributes
to two splits; 0 duplicate PCM hashes; `pcm_sha256` re-verified against disk on a
200-file sample; format re-checked on a 300-file sample.

## The honest caveat: this does not by itself fix /a/

LPC formant scan (`scripts/formants.py`), fraction of voiced frames landing in
the /a/ region (F1 650-850, F2 1000-1500):

| corpus | F1 median | /a/-region frames |
|---|---|---|
| old (253 s) | 599 Hz | 5.05 % |
| new train (all sources) | 607 Hz | 6.06 % |
| new kafe only | 572 Hz | 4.08 % |

The **rate** of clean /a/ is essentially unchanged, because this is the same
speaker with the same vowel space — F1 median 607 Hz still sits below the
650-850 Hz /a/ target, exactly as the original diagnosis found for Iddo's own
recordings (F1 510-546).

What did change is the **absolute** amount: roughly 13 seconds of /a/-region
material before, roughly 1.6 hours now (~450x).

So this corpus fixes the *quantity* problem and not the *coverage* problem.
Everything here is still one voice. To get Hebrew's /a/ rather than Iddo's /a/,
multi-speaker material is still required — see `corpus-big/open/`.
