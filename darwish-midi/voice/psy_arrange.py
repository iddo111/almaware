"""voice/psy_arrange.py -- ARRANGEMENT layer for Chai's psytrance material.

SWARM MEMBER B, DARWISH swarm night 2026-09-12 (claude-cli-SONNET-psyarrange).
Slice: STRUCTURE only. Psytrance has a shape -- intro, build, drop,
breakdown, second drop, outro -- and Chai (darwish-midi, live on eran4)
composes 60-ish-second fragments, not tracks. This module turns two or
three of his own fragments into ONE track with that shape.

INVENTS ZERO NOTES. Every pitch and every drum hit below is copy-pasted
straight out of Chai's own token stream (songs/outbox/<id>.tokens.json,
pulled once via ssh/scp into ../_deliverables/psytrance/source/). All this
module does to that material:
  - slices existing bars out of existing compositions (by index),
  - repeats bars (loops a slice; see BARS_PER_PHRASE wraparound below),
  - mutes/unmutes the two channels the v0 vocabulary actually has --
    "drums" (kick+body+hat, 3 bits) and "degree" (the ONE pitched voice;
    see body/genome.py and voice/psy_synth.py's own docstring for why bass
    and lead are literally the same token in this vocabulary generation --
    that is a FACT of the composer, not something this module works
    around),
  - sweeps ONE post-render mix-bus lowpass filter open/closed per section
    (independent of psy_synth.render()'s own per-note filter -- a standard
    psytrance arrangement technique, not new instrument/voice design; voice
    design is voice/psy_synth.py, owned by another swarm member tonight and
    left completely untouched here),
  - crossfades the seven section renders together and writes one WAV +
    one measurements JSON.

LAYER BOUNDARY: does not import or edit body/*, darwish_life.py, or edit a
single line of psy_synth.py. It only CALLS psy_synth.render() (already the
project's own renderer) and psy_synth.corpus_bpm() (a read-only corpus
stat), the same public contract darwish_life.py itself uses. Read-only on
the live outbox; dmidi-life/dmidi-tap on eran4 are never touched, never
restarted. Never plays audio. Never touches a microphone.

THE PLAN below (`SECTION_PLAN`) is the whole arrangement, on purpose: it is
data, not code, so it can be re-shaped by editing a few lines -- swap a
`source` key, change `n_bars`, flip a `drums` mode, move a `filt` range.

Run directly:
    python voice/psy_arrange.py
"""
import os

# Single-threaded, on purpose (standing PC law: heavy work never starves
# the mic/KESHEV) -- must be set BEFORE numpy/scipy are imported anywhere,
# including transitively via psy_synth.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

import glob
import json
import sys
import time

import numpy as np
import soundfile as sf
from scipy import signal

try:
    import pyloudnorm
except ImportError:
    pyloudnorm = None

try:
    import psutil
except ImportError:
    psutil = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                   # darwish-midi/
BODY = os.path.join(ROOT, "body")
for _p in (BODY, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import genome                                                   # noqa: E402
import psy_synth                                                 # noqa: E402

SR = psy_synth.SR
SOURCE_DIR = os.path.join(os.path.dirname(ROOT), "_deliverables",
                           "psytrance", "source")
OUT_DIR = os.path.join(os.path.dirname(ROOT), "_deliverables", "psytrance")
TMP_DIR = os.path.join(OUT_DIR, "_tmp_arrange_sections")

# Three of Chai's own fragments, composed tonight on eran4, pulled once
# (scp) into SOURCE_DIR -- see RAMCHAT claude-cli-SONNET-psyarrange claim.
SOURCE_FILES = {
    "A": "chai-20260912-013741.tokens.json",   # 01:37 -- intro/outro anchor
    "B": "chai-20260912-015246.tokens.json",   # 01:52 -- build/breakdown
    "C": "chai-20260912-020906.tokens.json",   # 02:09 -- freshest -- drops
}

# ---------------------------------------------------------------- THE PLAN
# One row per section. start_bar/n_bars index cyclically into that source's
# own bars (len 32 tonight: BARS_PER_PHRASE=16 x 2 phrases) -- change any
# field to reshape the track without touching a line of logic below.
#   drums:  "off"  = strip kick+body+hat, keep his degree line
#           "kick" = kick only (body+hat stripped)
#           "full" = untouched, exactly as composed
#   filt:   (start_hz, end_hz) linear sweep of ONE mix-bus lowpass across
#           the section -- "filters opening over 16 bars"
#   gain:   (start, end) linear level ramp across the section
#   phrase: True -> prepend one TOK_PHRASE (psy_synth's own existing
#           riser-on-phrase-boundary feature, not new code here)
SECTION_PLAN = [
    dict(name="intro",     source="A", start_bar=0,  n_bars=16,
         drums="off",  filt=(600, 900),      gain=(0.45, 0.70), phrase=False),
    dict(name="build",     source="B", start_bar=0,  n_bars=16,
         drums="kick", filt=(900, 3500),     gain=(0.70, 0.88), phrase=False),
    dict(name="drop1",     source="C", start_bar=0,  n_bars=24,
         drums="full", filt=(3500, 18000),   gain=(0.90, 1.00), phrase=True),
    dict(name="breakdown", source="B", start_bar=16, n_bars=16,
         drums="off",  filt=(18000, 900),    gain=(0.85, 0.55), phrase=False),
    dict(name="build2",    source="B", start_bar=0,  n_bars=12,
         drums="kick", filt=(900, 4200),     gain=(0.60, 0.88), phrase=False),
    dict(name="drop2",     source="C", start_bar=16, n_bars=24,
         drums="full", filt=(4200, 18000),   gain=(0.92, 0.97), phrase=True),
    dict(name="outro",     source="A", start_bar=0,  n_bars=16,
         drums="off",  filt=(9000, 500),     gain=(0.80, 0.0),  phrase=False),
]

XFADE_S = 0.28          # crossfade between sections, seconds
CEILING_DB = -0.5       # final safety-limiter ceiling


# --------------------------------------------------------------- tokens in
def load_bars(song_key):
    """Read songs/outbox/<id>.tokens.json and split it into bars, dropping
    every structural token (BOS/EOS/BAR/PHRASE) -- see genome.STRUCTURAL.
    Each bar is a plain list of audio tokens (drums*13 + degree), typically
    16 of them. Never modifies the source file."""
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


def mask_token(tok, drums_mode):
    """Mute/unmute channels of ONE existing token. Never changes the
    degree (pitch) value on its own -- only the 3 drum bits, or nothing."""
    drums, degree = divmod(tok, genome.DRUM_BASE)
    if drums_mode == "off":
        drums = 0
    elif drums_mode == "kick":
        drums = drums & 0b001
    # "full": untouched
    return drums * genome.DRUM_BASE + degree


def build_section_tokens(bars, start_bar, n_bars, drums_mode, phrase):
    out = []
    if phrase:
        out.append(genome.TOK_PHRASE)
    total = len(bars)
    for i in range(n_bars):
        bar = bars[(start_bar + i) % total]
        out.extend(mask_token(t, drums_mode) for t in bar)
    return out


# ------------------------------------------------------------- arrangement
def sweep_lowpass(x, f_start, f_end, sr=SR, block=2048, order=2):
    """Time-varying lowpass across the whole array x (1-D), cutoff swept
    linearly f_start->f_end. This is a MIX-BUS filter this module owns for
    arrangement purposes -- separate from, and applied on top of, whatever
    psy_synth.render() already baked into the per-note sound."""
    n = len(x)
    if n == 0:
        return x
    nyq = sr / 2.0
    out = np.empty(n, dtype=np.float64)
    zi = None
    for start in range(0, n, block):
        end = min(start + block, n)
        frac = start / max(1, n - 1)
        fc = f_start + (f_end - f_start) * frac
        fc = min(max(fc, 20.0), nyq * 0.97)
        b, a = signal.butter(order, fc / nyq, btype="low")
        if zi is None:
            zi = signal.lfilter_zi(b, a) * x[start]
        seg, zi = signal.lfilter(b, a, x[start:end], zi=zi)
        out[start:end] = seg
    return out


def apply_gain_ramp(stereo, g_start, g_end):
    n = len(stereo)
    ramp = np.linspace(g_start, g_end, n)[:, None]
    return stereo * ramp


def render_section(sec, bpm, idx):
    song_id, bars = load_bars(sec["source"])
    tokens = build_section_tokens(bars, sec["start_bar"], sec["n_bars"],
                                   sec["drums"], sec["phrase"])
    os.makedirs(TMP_DIR, exist_ok=True)
    tmp_path = os.path.join(TMP_DIR, f"{idx:02d}-{sec['name']}.wav")
    dur = psy_synth.render(tmp_path, tokens, bpm=bpm)
    audio, sr = sf.read(tmp_path, dtype="float64", always_2d=True)
    assert sr == SR
    f0, f1 = sec["filt"]
    filtered = np.stack([
        sweep_lowpass(audio[:, 0], f0, f1, sr=sr),
        sweep_lowpass(audio[:, 1], f0, f1, sr=sr),
    ], axis=1)
    g0, g1 = sec["gain"]
    shaped = apply_gain_ramp(filtered, g0, g1)
    return {
        "name": sec["name"], "source_song_id": song_id,
        "n_bars": sec["n_bars"], "drums": sec["drums"], "filt": sec["filt"],
        "raw_duration_s": round(dur, 3), "samples": len(shaped),
    }, shaped


def crossfade_concat(chunks, xfade_s, sr=SR):
    xfade_n = int(xfade_s * sr)
    out = None
    starts = []
    for seg in chunks:
        if out is None:
            out = seg.copy()
            starts.append(0)
            continue
        n = min(xfade_n, len(out), len(seg))
        if n <= 0:
            starts.append(len(out))
            out = np.concatenate([out, seg], axis=0)
            continue
        fade_out = np.linspace(1.0, 0.0, n)[:, None]
        fade_in = np.linspace(0.0, 1.0, n)[:, None]
        head = out[:-n]
        blended = out[-n:] * fade_out + seg[:n] * fade_in
        starts.append(len(head))
        out = np.concatenate([head, blended, seg[n:]], axis=0)
    return out, starts


def soft_limit(stereo, ceiling_db=CEILING_DB):
    ceiling = 10.0 ** (ceiling_db / 20.0)
    peak = float(np.max(np.abs(stereo))) or 1e-9
    if peak > ceiling:
        stereo = stereo * (ceiling / peak)
    return np.clip(stereo, -1.0, 1.0)


# ------------------------------------------------------------- measurement
def lufs_windows(mono_or_stereo, sr=SR, window_s=10.0):
    if pyloudnorm is None:
        return None, "pyloudnorm not installed -- LUFS curve skipped"
    meter = pyloudnorm.Meter(sr)
    n = len(mono_or_stereo)
    win_n = int(window_s * sr)
    out = []
    for start in range(0, n, win_n):
        end = min(start + win_n, n)
        seg = mono_or_stereo[start:end]
        if len(seg) < int(0.5 * sr):
            continue
        try:
            l = meter.integrated_loudness(seg)
        except Exception:
            l = float("nan")
        out.append({
            "t_start_s": round(start / sr, 2),
            "t_end_s": round(end / sr, 2),
            "lufs": None if l != l else round(float(l), 2),
        })
    return out, None


def lower_priority():
    if psutil is None:
        return "psutil not installed -- priority left at default"
    try:
        p = psutil.Process()
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        return "BELOW_NORMAL_PRIORITY_CLASS set"
    except Exception as e:
        return f"could not lower priority: {e}"


def main():
    t0 = time.time()
    prio_note = lower_priority()
    bpm = psy_synth.corpus_bpm()  # falls back to 144.0 -- no local food/ dir

    section_reports, section_audios = [], []
    for i, sec in enumerate(SECTION_PLAN):
        rep, audio = render_section(sec, bpm, i)
        section_reports.append(rep)
        section_audios.append(audio)

    master, starts = crossfade_concat(section_audios, XFADE_S, sr=SR)
    master = soft_limit(master)

    # cleanup temp section files -- nothing left behind
    for f in glob.glob(os.path.join(TMP_DIR, "*.wav")):
        try:
            os.remove(f)
        except OSError:
            pass
    try:
        os.rmdir(TMP_DIR)
    except OSError:
        pass

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_name = f"psy_render-v4-ARRANGED-chai-{stamp}"
    wav_path = os.path.join(OUT_DIR, out_name + ".wav")
    os.makedirs(OUT_DIR, exist_ok=True)
    sf.write(wav_path, master, SR, subtype="PCM_16")

    total_s = len(master) / SR
    peak_dbfs = 20 * np.log10((np.max(np.abs(master)) or 1e-9))
    mono = master.mean(axis=1)
    curve, curve_note = lufs_windows(mono, SR, 10.0)
    integrated = None
    if pyloudnorm is not None:
        try:
            integrated = round(float(pyloudnorm.Meter(SR).integrated_loudness(mono)), 2)
        except Exception:
            integrated = None

    drop_times_s = {
        s["name"]: round(starts[i] / SR, 2)
        for i, s in enumerate(SECTION_PLAN)
        if s["name"].startswith("drop")
    }

    measurements = {
        "measured_by": "this module (soundfile + pyloudnorm), read back from "
                        "the actual written WAV, not a self-report",
        "renderer": "voice/psy_synth.py render() per section, unmodified, "
                    "called once per SECTION_PLAN row (see this file's header)",
        "arranger": "voice/psy_arrange.py (SWARM MEMBER B, claude-cli-SONNET-psyarrange)",
        "sources": {k: v for k, v in SOURCE_FILES.items()},
        "bpm_used": bpm,
        "process_priority": prio_note,
        "single_threaded_env": {v: os.environ.get(v) for v in
                                 ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                                  "MKL_NUM_THREADS")},
        "file": os.path.basename(wav_path),
        "total_duration_s": round(total_s, 2),
        "n_sections": len(SECTION_PLAN),
        "sections": section_reports,
        "section_start_times_s": {s["name"]: round(starts[i] / SR, 2)
                                   for i, s in enumerate(SECTION_PLAN)},
        "drop_times_s": drop_times_s,
        "crossfade_s": XFADE_S,
        "peak_dbfs": round(float(peak_dbfs), 2),
        "integrated_lufs": integrated,
        "lufs_per_10s_window": curve,
        "lufs_note": curve_note,
        "render_wall_time_s": round(time.time() - t0, 2),
        "notes": "zero invented notes: every pitch/drum hit traces to one of "
                 "the three source tokens.json files listed above; this "
                 "module only slices bars, repeats them, mutes drums/degree, "
                 "and sweeps ONE mix-bus filter per section",
    }
    json_path = os.path.join(OUT_DIR, out_name + ".measurements.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(measurements, f, indent=2, ensure_ascii=False)

    print(f"[psy_arrange] wrote {wav_path}")
    print(f"[psy_arrange] wrote {json_path}")
    print(f"[psy_arrange] total {total_s:.2f}s, {len(SECTION_PLAN)} sections, "
          f"drops at {drop_times_s}, integrated {integrated} LUFS, "
          f"peak {peak_dbfs:.2f} dBFS")


if __name__ == "__main__":
    main()
