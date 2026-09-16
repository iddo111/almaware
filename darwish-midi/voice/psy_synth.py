"""voice/psy_synth.py — Chai's real psytrance loudspeaker.

LAYER BOUNDARY — read this before touching anything else in this repo:
The BRAIN (body/brain.py, chemistry.py, drives.py, critic.py, parent.py,
ears.py) and the ORGANISM LOOP (darwish_life.py) are pure ALMAWARE: Python
stdlib only, no third-party imports, ever — that is where the six biology
engines live and where "no backprop, legible synapses" is a hard law.

This module is NOT part of that boundary. It is the loudspeaker: a
delivery/rendering stage strictly downstream of the organism's own finished
token stream. It is allowed to import numpy + scipy (both already installed
on eran4) because synthesising a moving analogue filter — a resonant
lowpass whose cutoff is swept by an envelope, a sidechain duck, a
convolution reverb — sample-accurately in pure Python lists would be
unusably slow to write and to run, not because the biology needs numpy.
Nothing here feeds back into the brain; no file under body/ imports this
module; brain.py, chemistry.py etc. are untouched. If a future reader
wonders whether Chai's mind uses numpy: no. Only its voice does.

WHY THIS FILE EXISTS
body/synth.py (kept, untouched, as the "-basic.wav" fallback) writes
alarm-clock oscillators: a falling sine kick, a bare square-wave bass. It
proved the pipeline end-to-end. It was never meant to sound like the genre.
Iddo heard it and said, correctly: "עדיין גרוע ביותר — אתה צריך למצוא
סאונדים של סייקדליק טראנס" (still very bad — go find psychedelic-trance
sounds). A General MIDI soundfont (fluidsynth + FluidR3_GM) was tried next
and rejected too: GM is pianos and violins; psytrance is a *moving filter*,
which a frozen sample can't be. No sample packs or soundfonts are used here
— everything below is synthesised from first principles (oscillators +
envelopes + a resonant filter design), per the project's consent gate.

TOKEN FORMAT THIS RENDERER ASSUMES (see body/genome.py + DESIGN.md):
  token = drums*13 + bass_degree        (DRUM_BASE = 13)
  drums:  3 bits — bit0 kick, bit1 body/snare-ish, bit2 hat
  bass_degree: 0 = rest, 1..12 = scale degree over A1 (see body/midi_out.py
               bass_note()); v0's corpus carries exactly ONE pitched voice —
               there is no separate melodic/lead token yet (DESIGN.md: "Rung
               (b) mono-lead melody tokens: explicitly NOT promised" for v0).
  STRUCTURAL = {TOK_BAR, TOK_PHRASE, TOK_BOS, TOK_EOS} — carry no audio.

Because v0 has only one pitched channel, "map drums -> kick+perc, low
pitches -> bass, upper melodic -> acid lead" (the brief) is realised by
reusing that SAME pitch stream twice, in two registers and two synthesis
paths: one octave down through a duckable rolling-bass filter, and one
octave up through a squelchy TB-303-style acid-lead filter with its own
accent/slide logic. That is a deliberate v0 stand-in for a real lead
channel, documented here so nobody mistakes it for a mapping bug once v1
(DESIGN.md's promised mono-lead rung) adds a genuine second voice.
"""
import argparse
import glob
import json
import os
import shutil
import statistics
import sys
import wave

import numpy as np
from scipy import signal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BODY = os.path.join(ROOT, "body")
if _BODY not in sys.path:
    sys.path.insert(0, _BODY)

import genome                                      # noqa: E402
from midi_out import bass_note                      # noqa: E402

SR = 44100
FOOD_DIR = os.path.join(ROOT, "food")

_bpm_cache = {}


# --------------------------------------------------------------- tempo/key
def corpus_bpm(food_dir=None, fallback=144.0):
    """Read tempo from the corpus itself (median bpm across food/*.json
    shard headers), not a hardcoded constant — Darwish's band sits ~138-150
    BPM per Iddo; the measured median (323 shards, 2026-08-21) is 143.55."""
    food_dir = food_dir or FOOD_DIR
    if food_dir in _bpm_cache:
        return _bpm_cache[food_dir]
    vals = []
    for p in glob.glob(os.path.join(food_dir, "*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            b = d.get("bpm")
            if b:
                vals.append(float(b))
        except (OSError, ValueError):
            continue
    bpm = statistics.median(vals) if vals else fallback
    bpm = min(160.0, max(130.0, bpm))                # sane genre clamp
    _bpm_cache[food_dir] = bpm
    return bpm


# ------------------------------------------------------------------ filters
def _rbj_lowpass(fc, q, sr):
    """2-pole resonant lowpass biquad (RBJ Audio-EQ-Cookbook formulas) — the
    'state-variable / Moog-ladder approximation' the brief asks for: a real
    resonance peak at cutoff, unlike a maximally-flat Butterworth."""
    fc = min(max(fc, 20.0), sr * 0.45)
    q = max(q, 0.5)
    w0 = 2 * np.pi * fc / sr
    alpha = np.sin(w0) / (2 * q)
    cosw0 = np.cos(w0)
    b0, b1, b2 = (1 - cosw0) / 2, 1 - cosw0, (1 - cosw0) / 2
    a0, a1, a2 = 1 + alpha, -2 * cosw0, 1 - alpha
    b = np.array([b0, b1, b2]) / a0
    a = np.array([1.0, a1 / a0, a2 / a0])
    return b, a


def resonant_lowpass(x, fc, q, sr=SR, block=128):
    """Time-varying resonant lowpass: coefficients recomputed every `block`
    samples from the mean cutoff over that block (control-rate modulation —
    128 samples @44.1kHz = 2.9ms resolution, far below audible stepping);
    filter state (zi) carries across block seams so there are no clicks."""
    n = len(x)
    fc_arr = np.full(n, fc, dtype=np.float64) if np.isscalar(fc) else fc
    y = np.empty(n)
    zi = np.zeros(2)
    i = 0
    while i < n:
        j = min(i + block, n)
        b, a = _rbj_lowpass(float(np.mean(fc_arr[i:j])), q, sr)
        y[i:j], zi = signal.lfilter(b, a, x[i:j], zi=zi)
        i = j
    return y


def highpass(x, fc, sr=SR, order=2):
    sos = signal.butter(order, fc / (sr / 2), btype="highpass", output="sos")
    return signal.sosfilt(sos, x)


def bandpass(x, lo, hi, sr=SR, order=2):
    sos = signal.butter(order, [lo / (sr / 2), hi / (sr / 2)], btype="bandpass",
                         output="sos")
    return signal.sosfilt(sos, x)


# --------------------------------------------------------------- utilities
def _add_at(buf, start, arr):
    """Additive placement of a short one-shot into a longer buffer, clipped
    to bounds — every voice is built this way, so overlaps just sum."""
    end = min(start + len(arr), len(buf))
    if end <= start:
        return
    buf[start:end] += arr[:end - start]


def _steps(tokens):
    return [t for t in tokens if t not in genome.STRUCTURAL]


def _decode(tok):
    drums, bass = divmod(tok, genome.DRUM_BASE)
    return bool(drums & 1), bool((drums >> 1) & 1), bool((drums >> 2) & 1), bass


def _degree_freq(degree, octave_shift=0):
    note = bass_note(degree) + 12 * octave_shift
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


# ------------------------------------------------------------------ voices
def _make_kick(sr=SR, seed=genome.SEED):
    """Sine w/ fast exponential pitch-drop (150->50Hz, tau 14ms) + fast amp
    envelope (~350ms audible tail) + a short differentiated-noise click for
    attack punch. This is the heart of the genre — tune-by-ear territory."""
    dur = 0.4
    n = int(sr * dur)
    t = np.arange(n) / sr
    f = 50.0 + 100.0 * np.exp(-t / 0.014)
    phase = 2 * np.pi * np.cumsum(f) / sr
    amp = np.exp(-t / 0.09)
    tone = np.sin(phase) * amp
    click_n = int(sr * 0.005)
    rng = np.random.default_rng(seed)
    click = np.zeros(n)
    click[:click_n] = rng.uniform(-1, 1, click_n) * np.exp(-np.arange(click_n) / (sr * 0.0012))
    click = np.diff(click, prepend=0.0)              # crude HF emphasis
    out = tone * 0.95 + click * 0.55
    peak = np.max(np.abs(out)) or 1.0
    return out / peak


def _perc_hit(kind, rng, sr=SR):
    """Filtered-noise percussion: 'hat' = bright highpassed tick, 'body' =
    a mid-band bandpassed thud (this v0 corpus's kick/body/hat 3-bit field
    maps to 40-120Hz / 200-2kHz / 6-12kHz per DESIGN.md)."""
    if kind == "hat":
        n = int(sr * 0.05)
        env = np.exp(-np.arange(n) / (sr * 0.006))
        sig = highpass(rng.uniform(-1, 1, n), 7000, sr) * env
    else:
        n = int(sr * 0.09)
        env = np.exp(-np.arange(n) / (sr * 0.018))
        sig = bandpass(rng.uniform(-1, 1, n), 300, 1200, sr) * env
    peak = np.max(np.abs(sig)) or 1.0
    return sig / peak


def _make_ir(sr=SR, seconds=1.1, seed=None):
    """Synthesised impulse response for a Schroeder-style reverb-by-
    convolution: bandpassed exponentially-decaying noise, slightly different
    per channel for width. No sampled IRs, no licensing questions."""
    seed = genome.SEED + 7 if seed is None else seed
    n = int(sr * seconds)
    rng = np.random.default_rng(seed)
    t = np.arange(n) / sr
    decay = np.exp(-t / 0.35)
    irL = bandpass(rng.uniform(-1, 1, n), 150, 9000, sr) * decay
    irR = bandpass(rng.uniform(-1, 1, n), 150, 9000, sr) * decay
    irL /= (np.max(np.abs(irL)) or 1.0)
    irR /= (np.max(np.abs(irR)) or 1.0)
    return irL * 0.35, irR * 0.35


def _ping_pong(mono, delay_samples, feedback=0.38, repeats=7):
    L = np.zeros_like(mono)
    R = np.zeros_like(mono)
    cur = mono.copy()
    left = True
    for _ in range(repeats):
        cur = np.concatenate([np.zeros(delay_samples), cur])[:len(mono)] * feedback
        if left:
            L += cur
        else:
            R += cur
        left = not left
    return L, R


def _envelope_follower(x, sr=SR, tau_s=0.03):
    a = np.exp(-1.0 / (sr * tau_s))
    return signal.lfilter([1 - a], [1, -a], np.abs(x))


# ------------------------------------------------------------------ render
def render(path, tokens, bpm=None, seed=genome.SEED):
    """Render `tokens` (Chai's own song, see body/voice.py) to a 44.1kHz
    stereo psytrance WAV at `path`. Returns duration in seconds — same
    contract as body/synth.render() so darwish_life.py can call either."""
    bpm = bpm or corpus_bpm()
    step_dur = 60.0 / bpm / 4.0
    steps = _steps(tokens)
    n_steps = len(steps)
    positions = np.round(np.arange(n_steps + 1) * step_dur * SR).astype(np.int64)
    tail = int(1.6 * SR)                              # room for release + reverb tail
    total = int(positions[-1]) + tail

    kick_track = np.zeros(total)
    perc_track = np.zeros(total)
    bass_dry = np.zeros(total)
    bass_cut = np.full(total, 260.0)
    lead_freq = np.zeros(total)
    lead_amp = np.zeros(total)
    lead_cut = np.full(total, 300.0)

    kick_one = _make_kick(SR, seed)
    rng = np.random.default_rng(seed + 1)
    kick_onsets = []
    phrase_positions = []
    last_lead_step = None                             # for slide/legato detection

    step_idx = 0
    for tok in tokens:
        if tok == genome.TOK_PHRASE:
            phrase_positions.append(int(positions[min(step_idx, n_steps)]))
            continue
        if tok in genome.STRUCTURAL:
            continue
        kick, body, hat, degree = _decode(tok)
        s0, s1 = int(positions[step_idx]), int(positions[step_idx + 1])
        step_n = max(1, s1 - s0)
        phase_in_bar = step_idx % genome.STEPS_PER_BAR
        accent = (phase_in_bar % 4 == 0)

        if kick:
            kick_onsets.append(s0)
            _add_at(kick_track, s0, kick_one * 0.95)
        if body:
            _add_at(perc_track, s0, _perc_hit("body", rng) * 0.6)
        if hat:
            _add_at(perc_track, s0, _perc_hit("hat", rng) * 0.4)

        if degree > 0:
            note_n = min(int(step_n * 1.3), total - s0)
            if note_n > 4:
                t_local = np.arange(note_n) / SR

                # --- rolling bass: one octave down, always retriggered ---
                bass_f = _degree_freq(degree, octave_shift=-1)
                saw = 2.0 * ((t_local * bass_f) % 1.0) - 1.0
                env_b = np.exp(-t_local / 0.10)
                _add_at(bass_dry, s0, saw * env_b)
                cut_bump = 260.0 + 900.0 * np.exp(-t_local / 0.05)
                end = min(s0 + note_n, total)
                bass_cut[s0:end] = np.maximum(bass_cut[s0:end], cut_bump[:end - s0])

                # --- acid lead: one octave up, accent + slide/portamento ---
                is_slide = (last_lead_step == step_idx - 1)
                lead_f = _degree_freq(degree, octave_shift=1)
                end = min(s0 + note_n, total)
                seg = end - s0
                if is_slide and s0 > 0:
                    glide_n = min(seg, max(1, int(step_n * 0.35)))
                    prev_f = lead_freq[s0 - 1] or lead_f
                    lead_freq[s0:s0 + glide_n] = np.linspace(prev_f, lead_f, glide_n)
                    lead_freq[s0 + glide_n:end] = lead_f
                    bump_h = 0.55 * (1.4 if accent else 1.0)
                    cut_peak = 900.0 * (1.5 if accent else 1.0)
                else:
                    lead_freq[s0:end] = lead_f
                    bump_h = 1.0 * (1.5 if accent else 1.0)
                    cut_peak = 1800.0 * (1.5 if accent else 1.0)
                env_l = np.exp(-t_local[:seg] / 0.14) * bump_h
                lead_amp[s0:end] = np.maximum(lead_amp[s0:end], env_l)
                cut_bump_l = 350.0 + cut_peak * np.exp(-t_local[:seg] / 0.11)
                lead_cut[s0:end] = np.maximum(lead_cut[s0:end], cut_bump_l)
                last_lead_step = step_idx
        step_idx += 1

    # --------------------------------------------------------- sidechain duck
    duck = np.ones(total)
    dip_len = int(SR * 0.14)
    t_dip = np.arange(dip_len) / SR
    dip_shape = 1.0 - 0.82 * np.exp(-t_dip / 0.05)     # ~82% dip, ~80-120ms recovery
    for onset in kick_onsets:
        end = min(onset + dip_len, total)
        seg = end - onset
        duck[onset:end] = np.minimum(duck[onset:end], dip_shape[:seg])
    duck_lead = 0.55 + 0.45 * duck                      # lighter duck on the lead

    # ---------------------------------------------------------------- bass
    bass_wet = resonant_lowpass(bass_dry, np.clip(bass_cut, 60.0, 1200.0), q=2.2)
    bass_wet *= duck
    bass_wet = np.tanh(bass_wet * 1.3) * 0.8

    # ---------------------------------------------------------------- lead
    lead_phase = 2 * np.pi * np.cumsum(lead_freq) / SR
    lead_dry = (2.0 * ((lead_phase / (2 * np.pi)) % 1.0) - 1.0) * lead_amp
    lead_wet = resonant_lowpass(lead_dry, np.clip(lead_cut, 250.0, 3200.0), q=7.5)
    lead_wet = np.tanh(lead_wet * 1.6) * 0.85
    lead_wet *= duck_lead
    delay_samples = max(1, int(step_dur * 3 * SR))      # dotted-16th-ish tempo-synced echo
    echo_L, echo_R = _ping_pong(lead_wet, delay_samples)
    lead_L = lead_wet * 0.85 + echo_L * 0.45
    lead_R = lead_wet * 0.85 + echo_R * 0.45

    # ----------------------------------------------------------- atmosphere
    rngA = np.random.default_rng(seed + 2)
    bar_dur = step_dur * genome.STEPS_PER_BAR
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * np.arange(total) / SR / max(bar_dur * 4, 1.0))
    atmo_cut = 300.0 + 3000.0 * lfo
    atmo_L = resonant_lowpass(rngA.uniform(-1, 1, total), atmo_cut, q=1.2) * 0.045
    atmo_R = resonant_lowpass(rngA.uniform(-1, 1, total), atmo_cut, q=1.2) * 0.045
    for p in phrase_positions:                          # a riser into every 16-bar phrase
        riser_n = min(int(bar_dur * SR), total - p)
        if riser_n > SR // 10:
            cut_sweep = np.linspace(300.0, 6000.0, riser_n)
            riser = resonant_lowpass(rngA.uniform(-1, 1, riser_n), cut_sweep, q=1.5)
            riser *= np.linspace(0.0, 0.12, riser_n)
            _add_at(atmo_L, p, riser)
            _add_at(atmo_R, p, riser)

    # --------------------------------------------------------------- reverb
    fx_bus = lead_wet * 0.6 + (atmo_L + atmo_R) * 0.5 + perc_track * 0.15
    irL, irR = _make_ir(SR, seed=seed + 7)
    rev_L = signal.fftconvolve(fx_bus, irL)[:total]
    rev_R = signal.fftconvolve(fx_bus, irR)[:total]

    # ---------------------------------------------------------------- master
    mono_bus = kick_track + bass_wet                    # kick + bass: mono, centered
    L = mono_bus + lead_L + atmo_L + perc_track * 0.55 + rev_L * 0.22
    R = mono_bus + lead_R + atmo_R + perc_track * 0.55 + rev_R * 0.22

    L = highpass(L, 28.0)
    R = highpass(R, 28.0)

    env = np.maximum(_envelope_follower(L), _envelope_follower(R))
    thresh, ratio = 0.35, 3.0
    gr = np.ones_like(env)
    above = env > thresh
    gr[above] = (thresh + (env[above] - thresh) / ratio) / env[above]
    L *= gr
    R *= gr

    stereo = np.stack([L, R], axis=1)
    target_peak = 10.0 ** (-0.5 / 20.0)                 # -0.5 dBFS ceiling
    up = signal.resample_poly(stereo, 4, 1, axis=0)      # 4x for a true-peak-aware gain
    true_peak = float(np.max(np.abs(up))) or 1e-9
    if true_peak > target_peak:
        stereo *= target_peak / true_peak
    stereo = _soft_knee_limit(stereo, target_peak)       # safety net, never boosts

    _write_wav(path, stereo[:, 0], stereo[:, 1])
    return total / SR


def _soft_knee_limit(x, ceiling, knee_frac=0.85):
    """Identity below `knee_frac*ceiling`; smoothly asymptotes toward
    `ceiling` above it (never exceeds it). Unlike a plain tanh rescale, this
    leaves normal-level signal untouched — only the rare peak gets caught."""
    knee = knee_frac * ceiling
    mag = np.abs(x)
    over = mag > knee
    out = x.copy()
    if np.any(over):
        sign = np.sign(x[over])
        out[over] = sign * (knee + (ceiling - knee) * np.tanh((mag[over] - knee) / (ceiling - knee)))
    return out


def _write_wav(path, L, R, sr=SR):
    n = len(L)
    inter = np.empty(n * 2, dtype=np.int16)
    inter[0::2] = (np.clip(L, -1.0, 1.0) * 32767.0).astype(np.int16)
    inter[1::2] = (np.clip(R, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(inter.tobytes())


# ------------------------------------------------------------------- proof
def measure_wav(path):
    """RMS, true peak (4x-oversampled), spectral centroid, and the fraction
    of spectral energy below 80Hz — the honesty check: a psytrance kick
    that doesn't show up under 80Hz is not a kick."""
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if ch == 2:
        data = data.reshape(-1, 2)
        mono = data.mean(axis=1)
    else:
        mono = data
        data = data.reshape(-1, 1)
    rms = float(np.sqrt(np.mean(mono ** 2)))
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    up = signal.resample_poly(data, 4, 1, axis=0)
    true_peak = float(np.max(np.abs(up))) if up.size else 0.0
    spec = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
    freqs = np.fft.rfftfreq(len(mono), d=1.0 / sr)
    total_e = float(np.sum(spec ** 2)) or 1e-12
    low_e = float(np.sum(spec[freqs < 80.0] ** 2))
    centroid = float(np.sum(freqs * spec) / (np.sum(spec) or 1e-12))
    return {
        "path": os.path.basename(path),
        "sr": sr, "channels": ch, "duration_s": round(n / sr, 2),
        "rms_dbfs": round(20 * np.log10(rms + 1e-12), 2),
        "peak_dbfs": round(20 * np.log10(peak + 1e-12), 2),
        "true_peak_dbfs": round(20 * np.log10(true_peak + 1e-12), 2),
        "spectral_centroid_hz": round(centroid, 1),
        "energy_below_80hz_fraction": round(low_e / total_e, 5),
    }


# --------------------------------------------------------------------- CLI
def rerender_outbox(outbox_dir):
    """Re-render every existing song's saved tokens with this voice, keeping
    whatever old .wav is already there as '<song_id>-basic.wav' so nothing
    is lost. Returns the list of measurement dicts for the new renders."""
    results = []
    bpm = corpus_bpm()
    for tp in sorted(glob.glob(os.path.join(outbox_dir, "*.tokens.json"))):
        song_id = os.path.basename(tp)[: -len(".tokens.json")]
        with open(tp, "r", encoding="utf-8") as f:
            tokens = json.load(f)["tokens"]
        wav_path = os.path.join(outbox_dir, song_id + ".wav")
        basic_path = os.path.join(outbox_dir, song_id + "-basic.wav")
        if os.path.exists(wav_path) and not os.path.exists(basic_path):
            shutil.copyfile(wav_path, basic_path)
        dur = render(wav_path, tokens, bpm=bpm)
        m = measure_wav(wav_path)
        m["song_id"] = song_id
        m["bpm"] = round(bpm, 2)
        print(f"[psy_synth] {song_id}: {dur:.1f}s @ {bpm:.1f} BPM -> {wav_path}")
        results.append(m)
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="Chai's psytrance loudspeaker")
    ap.add_argument("--rerender-outbox", action="store_true",
                     help="re-render every songs/outbox/*.tokens.json with this voice")
    ap.add_argument("--outbox", default=os.path.join(ROOT, "songs", "outbox"))
    ap.add_argument("--results", default=None,
                     help="write measurements here (results/psy-render-<date>.json)")
    args = ap.parse_args(argv)
    if args.rerender_outbox:
        results = rerender_outbox(args.outbox)
        if args.results:
            os.makedirs(os.path.dirname(args.results), exist_ok=True)
            with open(args.results, "w", encoding="utf-8") as f:
                json.dump({"bpm": corpus_bpm(), "songs": results}, f, indent=2)
            print(f"[psy_synth] measurements -> {args.results}")


if __name__ == "__main__":
    main()
