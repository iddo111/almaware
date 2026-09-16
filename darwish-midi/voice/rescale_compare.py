"""voice/rescale_compare.py -- Iddo's ear-ruling response, swarm slice
"claude-cli-SONNET-rescale" (RAMCHAT, 2026-09-12 ~02:45).

Iddo listened to tonight's ARRANGED track (psy_render-v4-ARRANGED-chai-
20260912-023406.wav) and ruled it out at the ear: "דרוויש חרא... חירבוש לא
סולם... קקופוניה" -- cacophony, no scale. That overrides claude-cli-
psymode's blunt whole-mix chroma-similarity metric from an hour earlier
(which had scored plain chromatic closest to a real Darwish reference).
His ear is ground truth here, not a number.

WHY THIS IS A NEW, SEPARATE FILE (read the RAMCHAT transcript before
touching anything in this folder): claude-cli-SONNET-psyvoices is editing
voice/psy_synth.py RIGHT NOW. psy_arrange.py's render_section() calls
psy_synth.render(), which imports `bass_note` directly from body/midi_out
(see psy_synth.py line 68 and _degree_freq()) -- it is wired chromatic,
hard, with NO mode parameter at all. Giving psy_arrange.py's real pipeline
a mode switch would mean editing psy_synth.py's pitch path, i.e. the exact
file another agent owns tonight. So, per the task's own fallback clause:
this script does NOT re-render the full 3:36 arrangement. It (a) measures
the REAL arrangement's actual note content honestly from the tokens (no
audio needed for that, no ambiguity), and (b) renders ONE ~60s excerpt of
the same real Chai material in three scales through body/modes.py's own
tiny stdlib preview synth (render_preview_wav -- built by psymode
specifically so a mode's audible identity could be checked without
touching psy_synth.py or body/synth.py). Same excerpt, same drum pattern,
same tempo, same instrumentation each time -- the ONLY variable across the
three renders is which scale the SAME degree stream is snapped to.

Reads only: the three source tokens.json files already pulled by
psyarrange, body/genome.py, body/modes.py. Touches: nothing else. Never
imports psy_synth.py or psy_arrange.py (avoids racing psyvoices' live
edit). Never plays audio. Never touches a microphone.

Run directly:
    python voice/rescale_compare.py
"""
import os
import subprocess
import sys
import time
import json
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                    # darwish-midi/
BODY = os.path.join(ROOT, "body")
for _p in (BODY, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import genome                                                    # noqa: E402
import modes                                                     # noqa: E402

SOURCE_DIR = os.path.join(os.path.dirname(ROOT), "_deliverables",
                           "psytrance", "source")
OUT_DIR = os.path.join(os.path.dirname(ROOT), "_deliverables", "psytrance")
FFMPEG = (r"C:\Users\<user>\AppData\Local\Microsoft\WinGet\Packages\\"
          r"Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\"
          r"ffmpeg-8.1.1-full_build\bin\ffmpeg.exe")

BPM = 144.0  # same bpm psy_arrange.py actually used tonight (measurements.json)

# Read-only copy of psy_arrange.py's own SECTION_PLAN data (not its code --
# that file's docstring calls the plan "data, not code" on purpose) so the
# FULL arrangement's real note content can be measured honestly. Pitch is
# unaffected by the drums= field (masking only ever rewrites the drum bits,
# see psy_arrange.mask_token / this file's own comment below), so it is
# omitted here -- only source/start_bar/n_bars, which is all pitch content
# depends on.
SECTION_PLAN = [
    dict(name="intro",     source="A", start_bar=0,  n_bars=16),
    dict(name="build",     source="B", start_bar=0,  n_bars=16),
    dict(name="drop1",     source="C", start_bar=0,  n_bars=24),
    dict(name="breakdown", source="B", start_bar=16, n_bars=16),
    dict(name="build2",    source="B", start_bar=0,  n_bars=12),
    dict(name="drop2",     source="C", start_bar=16, n_bars=24),
    dict(name="outro",     source="A", start_bar=0,  n_bars=16),
]

SOURCE_FILES = {
    "A": "chai-20260912-013741.tokens.json",
    "B": "chai-20260912-015246.tokens.json",
    "C": "chai-20260912-020906.tokens.json",
}


def lower_priority():
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        return "BELOW_NORMAL_PRIORITY_CLASS set"
    except Exception as e:
        return f"could not lower priority: {e}"


def load_bars(song_key):
    """Same bar-split logic as psy_arrange.load_bars() (structural tokens
    end a bar, EOS ends the song) -- reimplemented locally, read-only, so
    this file never has to import psy_arrange.py (which would transitively
    import psy_synth.py mid-edit by another agent)."""
    path = os.path.join(SOURCE_DIR, SOURCE_FILES[song_key])
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    tokens = data["tokens"]
    bars, cur = [], []
    for t in tokens:
        if t == genome.TOK_EOS:
            break
        if t in genome.STRUCTURAL:
            if cur:
                bars.append(cur)
                cur = []
            continue
        cur.append(t)
    if cur:
        bars.append(cur)
    return data["song_id"], bars


def slice_bars(bars, start_bar, n_bars):
    total = len(bars)
    out = []
    for i in range(n_bars):
        out.extend(bars[(start_bar + i) % total])
    return out


# --------------------------------------------------------- pitch measurement
def analyze(tokens, label):
    """Pitch-class histogram, out-of-scale count, interval distribution --
    for chromatic (= today's live/actual mapping, byte-identical to
    midi_out.bass_note()) and for the two candidate scales, on the SAME
    token stream. This needs no audio at all: modes.bass_note_mode() is the
    exact function midi_out.write() already calls for every real render."""
    out = {"label": label, "n_tokens": len(tokens)}
    root = 45
    # modes.SCALES holds semitone OFFSETS FROM THE ROOT (see modes.py docstring
    # and snap_to_scale/bass_note_mode: chroma = (degree-1)%12, note = root +
    # snap(chroma)), not absolute C-based pitch classes -- so "is this note in
    # scale X" must compare (note - root) % 12 against the set, not note % 12.
    scale_sets = {name: set(vals) for name, vals in modes.SCALES.items()}
    for mode in ("chromatic", "minor", "freygish", "hijaz"):
        notes = modes.note_sequence(tokens, genome.DRUM_BASE, mode=mode, root=root)
        hist = modes.pitch_class_histogram(notes)
        ihist, imean = modes.interval_histogram(notes)
        rel_chromas = [(n - root) % 12 for n in notes]
        out_of = {}
        for scale_name, sset in scale_sets.items():
            out_of[scale_name] = sum(1 for c in rel_chromas if c not in sset)
        out[mode] = {
            "n_sounding_notes": len(notes),
            "pitch_class_histogram_0to11": [round(h, 4) for h in hist],
            "distinct_pitch_classes_used": sum(1 for h in hist if h > 0),
            "notes_outside_each_scale": out_of,
            "interval_histogram_semitones": {str(k): v for k, v in sorted(ihist.items())},
            "mean_abs_interval_semitones": round(imean, 3),
        }
    return out


# ------------------------------------------------------------------- ffmpeg
def to_mp3(wav_path, mp3_path):
    # the preview synth writes 22050 Hz mono (modes.py SR); libmp3lame can
    # only reach true 192kbps CBR at MPEG-1 sample rates (32/44.1/48kHz) --
    # below 32kHz it silently caps at 160kbps even when 192k is requested
    # (measured). -ar 44100 upsamples first so 192k is the REAL rate, not a
    # request the codec quietly downgrades.
    args = [
        FFMPEG, "-y", "-nostdin", "-threads", "1",
        "-i", wav_path, "-ar", "44100", "-b:a", "192k", "-threads", "1", mp3_path,
    ]
    flags = 0
    if hasattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS"):
        flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS
    r = subprocess.run(args, capture_output=True, text=True, creationflags=flags)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {wav_path}:\n{r.stderr[-2000:]}")


def wav_duration_s(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def main():
    t0 = time.time()
    prio_note = lower_priority()
    stamp = time.strftime("%Y%m%d-%H%M%S")

    # ---- 1. load all three sources once
    song_ids, bars_by_key = {}, {}
    for key in SOURCE_FILES:
        sid, bars = load_bars(key)
        song_ids[key] = sid
        bars_by_key[key] = bars

    # ---- 2. FULL arrangement token stream (pitch content only -- drums= in
    # the real SECTION_PLAN never changes the bass/degree value, only which
    # drum bits sound, so it is irrelevant to any of these measurements)
    full_tokens = []
    section_token_counts = []
    for sec in SECTION_PLAN:
        toks = slice_bars(bars_by_key[sec["source"]], sec["start_bar"], sec["n_bars"])
        full_tokens.extend(toks)
        section_token_counts.append({"name": sec["name"], "source": sec["source"],
                                      "n_bars": sec["n_bars"], "n_tokens": len(toks)})

    full_analysis = analyze(full_tokens, "FULL ARRANGED TRACK (all 7 sections, "
                                          "same slicing psy_arrange.py used tonight, "
                                          "216.19s real render)")

    # ---- 3. the ~60s excerpt: source C (used for BOTH drops, the densest,
    # most exposed pitched+drum material -- most likely where cacophony is
    # most audible), 36 bars cyclic from bar 0 -> 36*16 steps @144bpm = 60.0s
    # of musical content before the preview synth's 1s decay tail.
    excerpt_bars = 36
    excerpt_tokens = slice_bars(bars_by_key["C"], 0, excerpt_bars)
    excerpt_analysis = analyze(excerpt_tokens, f"60s EXCERPT (source C, {excerpt_bars} "
                                                 f"bars cyclic from bar 0, same material "
                                                 f"as the real drop1/drop2 sections)")

    # ---- 4. render the SAME excerpt through modes.py's own preview synth,
    # three times, mode is the only thing that changes
    files = {}
    for mode in ("chromatic", "minor", "freygish"):
        wav_path = os.path.join(OUT_DIR, f"darwish-rescale-excerpt-{mode}-{stamp}.wav")
        dur = modes.render_preview_wav(wav_path, excerpt_tokens, genome.DRUM_BASE,
                                        bpm=BPM, mode=mode, root=45)
        mp3_path = wav_path[:-4] + ".mp3"
        to_mp3(wav_path, mp3_path)
        files[mode] = {
            "wav": os.path.basename(wav_path),
            "mp3": os.path.basename(mp3_path),
            "duration_s": round(dur, 2),
            "mp3_bytes": os.path.getsize(mp3_path),
        }

    # ---- 5. write the report
    report = {
        "context": "Iddo's ear ruling 2026-09-12 overrides psymode's chroma-"
                    "similarity metric: ARRANGED track is cacophony, no scale.",
        "why_not_the_full_pipeline": "psy_arrange.render_section() calls "
            "psy_synth.render(), which hardcodes chromatic pitch via "
            "midi_out.bass_note() with no mode= parameter (see psy_synth.py "
            "line 68 `from midi_out import bass_note` and _degree_freq()). "
            "psy_synth.py is being edited live tonight by claude-cli-SONNET-"
            "psyvoices. Giving the real arrangement pipeline a mode switch "
            "would require editing that exact file, which is out of scope "
            "for this slice. Fallback per task instructions: measured the "
            "real arrangement's tokens directly (exact, no audio needed), "
            "and rendered one ~60s excerpt of the same real material in "
            "three scales through body/modes.py's own independent stdlib "
            "preview synth (render_preview_wav), which is NOT psy_synth.py "
            "and was built by psymode specifically for this purpose.",
        "process_priority": prio_note,
        "bpm_used": BPM,
        "sources": song_ids,
        "full_arrangement_section_slicing": section_token_counts,
        "full_arrangement_analysis": full_analysis,
        "excerpt_bars": excerpt_bars,
        "excerpt_analysis": excerpt_analysis,
        "excerpt_files": files,
        "reference_original_full_render": {
            "wav": "psy_render-v4-ARRANGED-chai-20260912-023406.wav",
            "mp3": "psy_render-v4-ARRANGED-chai-20260912-023406.mp3",
            "note": "the actual track Iddo heard and rejected; NOT re-rendered "
                    "here (would need psy_synth.py). Its note content IS the "
                    "'full_arrangement_analysis' block above (same tokens, same "
                    "slicing, chromatic sub-block = byte-identical pitch mapping "
                    "to what that WAV actually contains).",
        },
        "render_wall_time_s": round(time.time() - t0, 2),
        "audio_never_played": True,
        "microphone_never_touched": True,
    }
    json_path = os.path.join(OUT_DIR, f"RESCALE-COMPARISON-{stamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # ---- 6. print the numbers that matter
    fa = full_analysis
    print(f"[rescale] wrote {json_path}")
    for mode in ("chromatic", "minor", "freygish"):
        m = fa[mode]
        print(f"[rescale] FULL TRACK {mode:9s}: {m['n_sounding_notes']} notes, "
              f"{m['distinct_pitch_classes_used']}/12 pitch classes used, "
              f"outside-minor={m['notes_outside_each_scale']['minor']}, "
              f"outside-freygish={m['notes_outside_each_scale']['freygish']}, "
              f"mean interval={m['mean_abs_interval_semitones']} semitones")
    for mode, info in files.items():
        print(f"[rescale] excerpt {mode:9s}: {info['mp3']} ({info['duration_s']}s)")


if __name__ == "__main__":
    main()
