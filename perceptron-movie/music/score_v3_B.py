#!/usr/bin/env python3
"""
score_v3_B.py — TAKE B: slow cinematic hypnotic ambient trance
================================================================
Perceptron documentary score, flavor B.

Design (per brief):
  * 108 BPM halftime feel (kick on 1 and 3 during peak; 1 only during build/release)
  * Hijaz mode on D: D  Eb  F#  G  A  Bb  C
  * Emphasis on evolving pads: long attack, slow SVF filter sweep, supersaw + chorus
  * Sparse percussion: soft sub-kick + wide shaker + occasional darbuka accent
  * Sustained bass drone (D1 sub sine + D2 detuned-saw body) w/ subtle amp LFO
  * Ney-flute style lead: sine + subtle 2nd-harmonic + breath noise + 5.5Hz vibrato,
    long phrases, long rests
  * Reverb-heavy cinematic mix (synthesized 4s hall IR, FFT-convolved, stereo-decorrelated)

Structure (loopable):
  bars 0..31  : 32-bar slow build  (pad opens, ney enters, kick joins at bar 8)
  bars 32..63 : 32-bar peak         (halftime kick, shaker 8ths, ney climbs)
  bars 64..79 : 16-bar release      (kick pulls back, filter closes, wash out)

Total ≈ 80 * (4 * 60/108) ≈ 177.8s (~2:58). Loopable: last bar sustains the tonic.

DSP quality goals (per v3_technical_plan.md post-mortem of v1/v2):
  * PolyBLEP-band-limited saw (no aliasing)
  * Real SVF (Butterworth SOS, chunked) with per-time cutoff (real sweeps)
  * Real convolution reverb via scipy.signal.fftconvolve on synthesized IRs
  * Real ADSR curves
  * Non-mechanical humanization: micro-timing ±5ms, velocity ±10%
  * Proper stereo width via decorrelated per-channel IRs

Output: score_v3_B.wav and score_v3_B.mp3 (via ffmpeg).
"""
import numpy as np, wave, os, subprocess, sys, time
from scipy import signal

# ------------------------------------------------------------------ constants
SR    = 44100
BPM   = 108.0
BEAT  = 60.0 / BPM             # 0.5556 s
BAR   = BEAT * 4               # 2.2222 s
BARS  = 80                     # 32 build + 32 peak + 16 release
TOTAL_S = BARS * BAR
N_TOTAL = int(TOTAL_S * SR)

HERE  = os.path.dirname(os.path.abspath(__file__))
OUT_WAV = os.path.join(HERE, "score_v3_B.wav")
OUT_MP3 = os.path.join(HERE, "score_v3_B.mp3")

# Hijaz mode on D (D Eb F# G A Bb C) MIDI degrees relative to D
# Extended two octaves for ney
def hz(midi): return 440.0 * 2 ** ((midi - 69) / 12.0)
D3=50; Eb3=51; F3s=54; G3=55; A3=57; Bb3=58; C4=60
D4=62; Eb4=63; F4s=66; G4=67; A4=69; Bb4=70; C5=72
D5=74; Eb5=75; F5s=78; G5=79; A5=81

rng = np.random.default_rng(11)

print(f"[score_v3_B] BPM={BPM}  bars={BARS}  total={TOTAL_S:.1f}s  samples={N_TOTAL}", flush=True)

# ------------------------------------------------------------------ helpers
def place(buf, t_s, sig, gain=1.0):
    i = int(t_s * SR); e = min(i + len(sig), len(buf))
    if i < len(buf) and e > i:
        buf[i:e] += sig[:e-i] * gain

def humanize(t_s, jitter_ms=4.0):
    return t_s + rng.normal(0, jitter_ms*1e-3)

# ------------------------------------------------------------------ oscillators
def polyblep(t, dt):
    """PolyBLEP correction to reduce sawtooth aliasing."""
    r = np.zeros_like(t)
    m1 = t < dt
    if np.any(m1):
        tt = t[m1] / dt[m1]
        r[m1] = tt + tt - tt*tt - 1
    m2 = t > 1.0 - dt
    if np.any(m2):
        tt = (t[m2] - 1.0) / dt[m2]
        r[m2] = tt*tt + tt + tt + 1
    return r

def bl_saw(freq, N, phase=0.0):
    """Band-limited sawtooth via PolyBLEP. freq: scalar or (N,) array."""
    if np.isscalar(freq):
        f_arr = np.full(N, float(freq))
    else:
        f_arr = np.asarray(freq, dtype=np.float64)
        if len(f_arr) < N:
            f_arr = np.pad(f_arr, (0, N - len(f_arr)), mode='edge')
    dt = f_arr / SR
    t = (phase + np.cumsum(dt)) % 1.0
    saw = 2*t - 1 - polyblep(t, dt)
    return saw

def supersaw(freq, N, voices=5, detune_cents=14, drift_hz=0.18, seed=0):
    r = np.random.default_rng(seed)
    out = np.zeros(N)
    t = np.arange(N)/SR
    for v in range(voices):
        # spread cents across [-detune_cents .. +detune_cents]
        c = detune_cents * (2*v/(voices-1) - 1) if voices > 1 else 0
        # slow analog drift ±3c
        drift = 3.0 * np.sin(2*np.pi*(drift_hz + 0.03*r.random())*t + r.random()*6.283)
        f_inst = freq * 2**((c + drift)/1200.0)
        ph = r.random()
        out += bl_saw(f_inst, N, phase=ph)
    return out / voices

# ------------------------------------------------------------------ filters
def svf_lp_swept(x, cutoff_hz_arr, q=0.9, chunk=512):
    """Chunked 4th-order Butterworth LP with per-time cutoff. Filter state is
    preserved across chunks for continuous, click-free sweeps."""
    N = len(x)
    out = np.zeros(N)
    zi = None
    last_fc = None
    for i in range(0, N, chunk):
        e = min(i+chunk, N)
        fc = float(np.clip(cutoff_hz_arr[i], 40.0, SR/2.5))
        if last_fc is None or abs(fc - last_fc) / max(last_fc, 1) > 0.005:
            sos = signal.butter(4, fc, btype='lowpass', fs=SR, output='sos')
            if zi is None:
                zi = signal.sosfilt_zi(sos) * x[i]
            last_fc = fc
            last_sos = sos
        y, zi = signal.sosfilt(last_sos, x[i:e], zi=zi)
        out[i:e] = y
    return out

def bandpass(x, lo, hi):
    sos = signal.butter(4, [lo, hi], btype='bandpass', fs=SR, output='sos')
    return signal.sosfilt(sos, x)

def hipass(x, fc, order=4):
    sos = signal.butter(order, fc, btype='highpass', fs=SR, output='sos')
    return signal.sosfilt(sos, x)

def lopass(x, fc, order=4):
    sos = signal.butter(order, fc, btype='lowpass', fs=SR, output='sos')
    return signal.sosfilt(sos, x)

# ------------------------------------------------------------------ reverb IR
def make_hall_ir(dur=4.2, decay_rate=1.15, seed=1):
    """Synthesized diffuse hall IR: exponentially-decaying filtered noise
    + shaped early reflections."""
    r = np.random.default_rng(seed)
    N = int(dur*SR)
    t = np.arange(N)/SR
    noise = r.standard_normal(N)
    env = np.exp(-t*decay_rate)
    # exponentially-densifying early reflection density (pre-delay 18ms)
    er = np.zeros(N)
    pre = int(0.018*SR)
    er_taps = [(0.019,0.55),(0.028,0.48),(0.041,0.42),(0.055,0.38),
               (0.072,0.34),(0.091,0.30),(0.113,0.26),(0.137,0.22),
               (0.166,0.18),(0.201,0.15)]
    for delay, gain in er_taps:
        s = int(delay*SR)
        if s < N:
            er[s] += gain
    ir = 0.65*noise*env + 0.55*er
    # tonal shaping — cinematic warmth
    ir = bandpass(ir, 90, 8500)
    # normalize
    ir /= np.max(np.abs(ir)) + 1e-9
    ir *= 0.9
    return ir

def convolve_fft(x, ir):
    return signal.fftconvolve(x, ir)[:len(x)]

# ------------------------------------------------------------------ ney flute
def ney_note(midi, dur_s, vel=0.8, seed=0, breath_amt=0.10):
    """Ney-style: sine + subtle 2nd harmonic + breath noise + 5.5 Hz vibrato.
    Vibrato ramps in over ~0.4 s after 0.12 s attack — like real breath control."""
    N = int(dur_s * SR)
    t = np.arange(N)/SR
    freq = hz(midi)
    # vibrato: ramp in, 5.5 Hz sine, ±25 cents at full depth
    vib_ramp = np.clip((t - 0.12)/0.42, 0, 1)
    vib = 25.0 * vib_ramp * np.sin(2*np.pi*5.5*t + 0.7*seed)
    # subtle drift for organic feel
    drift = 4.0 * np.sin(2*np.pi*0.23*t + 1.2*seed)
    f_inst = freq * 2**((vib + drift)/1200.0)
    ph = np.cumsum(f_inst/SR)
    tone = np.sin(2*np.pi*ph)
    # 2nd harmonic softens attack
    tone += 0.09 * np.sin(4*np.pi*ph)
    # 3rd harmonic gives ney "reed" bite (very quiet)
    tone += 0.03 * np.sin(6*np.pi*ph)
    # ADSR: A=0.12 exp-in, D=0.05, S=0.90, R=min(0.55s, 40% of note)
    att = int(0.12*SR)
    rel = int(min(0.55, dur_s*0.4) * SR)
    env = np.full(N, 0.90)
    if att < N:
        env[:att] = np.linspace(0, 1, att)**1.4
    if rel < N:
        env[-rel:] = np.linspace(1, 0, rel)**1.6 * 0.90
    # breath noise (bandpassed pink-ish air)
    rr = np.random.default_rng(seed+7)
    br = rr.standard_normal(N)
    br = bandpass(br, 1400, 4800)
    br_env = env * breath_amt + 0.02*(env>0.4)
    y = tone*env + br*br_env
    return y * vel

# ------------------------------------------------------------------ drums
def soft_kick(vel=1.0, seed=0):
    """Soft sub kick: pitch envelope 95->42 Hz, sine body, long tail, tiny click."""
    N = int(0.55*SR); t = np.arange(N)/SR
    f = 42.0 + 55.0*np.exp(-t*22.0)
    ph = np.cumsum(f/SR)
    body = np.sin(2*np.pi*ph)
    env = np.exp(-t*3.4)
    # very short click (10 ms) for punch even in ambient mix
    click_N = int(0.008*SR)
    r = np.random.default_rng(seed+1)
    click = r.standard_normal(click_N) * np.exp(-np.arange(click_N)/(0.003*SR)) * 0.35
    out = body*env
    out[:click_N] += click
    return out * vel * 0.85

def shaker(vel=1.0, seed=0):
    """Filtered noise burst, gentle."""
    N = int(0.075*SR); t = np.arange(N)/SR
    r = np.random.default_rng(seed+31)
    n = r.standard_normal(N)
    n = bandpass(n, 4200, 10500)
    env = np.exp(-t/0.028)
    return n*env*0.38*vel

def darbuka_accent(vel=1.0, seed=0):
    """Simple darbuka 'dum' hit: modal resonances + tiny attack noise."""
    N = int(0.35*SR); t = np.arange(N)/SR
    body = np.sin(2*np.pi*168*t)*np.exp(-t*11.0)
    body += 0.45*np.sin(2*np.pi*385*t)*np.exp(-t*18.0)
    body += 0.20*np.sin(2*np.pi*720*t)*np.exp(-t*30.0)
    r = np.random.default_rng(seed+53)
    click_N = int(0.006*SR)
    click = r.standard_normal(click_N)*0.55*np.exp(-np.arange(click_N)/(0.002*SR))
    out = body*0.7
    out[:click_N] += click
    return out*vel*0.7

# ------------------------------------------------------------------ pad
def pad_layer(chord_midis, duration_s, seed=0):
    """5-voice supersaw stack per chord tone. Return dry mono pad."""
    N = int(duration_s*SR)
    y = np.zeros(N)
    for i, m in enumerate(chord_midis):
        y += supersaw(hz(m), N, voices=5, detune_cents=13, drift_hz=0.15+0.04*i, seed=seed+i)
    return y / max(1, len(chord_midis)) * 0.9

# ------------------------------------------------------------------ bass drone
def bass_drone(midi_low, midi_body, duration_s, seed=0):
    """Sub-sine at D1 + slightly detuned bl_saw body at D2, gentle amp LFO."""
    N = int(duration_s*SR)
    t = np.arange(N)/SR
    # sub sine (pure)
    sub = np.sin(2*np.pi*hz(midi_low)*t) * 0.9
    # body: 3 detuned bl_saws around D2 with slow drift
    body = supersaw(hz(midi_body), N, voices=3, detune_cents=8, drift_hz=0.12, seed=seed+3)
    # LP the body to keep it dark
    body = lopass(body, 480, order=4)
    # slow amp LFO 0.11 Hz, ±6%
    lfo = 1.0 + 0.06*np.sin(2*np.pi*0.11*t + 1.4)
    return (sub*0.55 + body*0.55) * lfo

# ================================================================== TIMELINE
print("[score_v3_B] rendering pad ...", flush=True)
# ---- PAD -----------------------------------------------------------------
# Whole-piece pad. Chord: D-F#-A-Bb (Dm(b6) shell). Add C occasionally via 2nd layer.
CHORD_MAIN  = [D3, F3s, A3, Bb3]
CHORD_ALT   = [D3, F3s, A3, C4]        # bar 40-55 lifts slightly
CHORD_DARK  = [D3, F3s, Bb3, Eb4]      # bar 56-63 tension push

pad = np.zeros(N_TOTAL)
# main pad = one long take
pad_main = pad_layer(CHORD_MAIN, TOTAL_S, seed=101)
pad[:len(pad_main)] += pad_main

# second layer only during peak (bars 32..63) using CHORD_ALT/DARK
peak_start_s = 32 * BAR
peak_end_s   = 64 * BAR
peak_dur     = peak_end_s - peak_start_s
pad_alt = pad_layer(CHORD_ALT, peak_dur, seed=202) * 0.85
# fade in over first 2 bars, cross to CHORD_DARK second half
Npk = len(pad_alt); tp = np.arange(Npk)/SR
alt_env = np.clip(tp/(2*BAR), 0, 1) * np.clip((peak_dur - tp)/(4*BAR), 0, 1)
place(pad, peak_start_s, pad_alt * alt_env, gain=1.0)

pad_dark = pad_layer(CHORD_DARK, 8*BAR, seed=303) * 0.65
place(pad, 56*BAR, pad_dark * np.hanning(len(pad_dark))**0.5, gain=1.0)

# ---- Pad filter sweep (SLOW, cinematic) ----
# build: 250 Hz -> 2200 Hz (bars 0..31)
# peak:  2200 Hz -> 3800 Hz (bars 32..47), hold 3800 (48..55), open to 4800 (56..63)
# release: 4800 -> 380 Hz (bars 64..79) — the "wash out" close
t_full = np.arange(N_TOTAL)/SR
cutoff = np.zeros(N_TOTAL)
def bar_to_i(b): return int(b*BAR*SR)

# build
i0, i1 = 0, bar_to_i(32)
cutoff[i0:i1] = np.linspace(250, 2200, i1-i0)
# peak, part 1: 32..48 rise
i0, i1 = bar_to_i(32), bar_to_i(48)
cutoff[i0:i1] = np.linspace(2200, 3800, i1-i0)
# peak, part 2: 48..56 hold with subtle 0.08Hz LFO ±350Hz
i0, i1 = bar_to_i(48), bar_to_i(56)
t_seg = t_full[i0:i1]
cutoff[i0:i1] = 3800 + 350*np.sin(2*np.pi*0.08*(t_seg - t_seg[0]))
# peak, part 3: 56..64 push open
i0, i1 = bar_to_i(56), bar_to_i(64)
cutoff[i0:i1] = np.linspace(3800, 4800, i1-i0)
# release: 64..80 close
i0, i1 = bar_to_i(64), N_TOTAL
cutoff[i0:i1] = np.geomspace(4800, 380, i1-i0)

pad_filt = svf_lp_swept(pad, cutoff, q=1.05, chunk=256)

# amp envelope: fade in first 4 bars, hold, gentle taper last 4 bars
amp_env = np.ones(N_TOTAL)
fi = bar_to_i(4)
amp_env[:fi] = np.linspace(0, 1, fi)**1.3
fo_start = bar_to_i(76); fo_len = N_TOTAL - fo_start
amp_env[fo_start:] = np.linspace(1, 0, fo_len)**1.5
pad_filt *= amp_env * 0.42

# ---- BASS DRONE ----------------------------------------------------------
print("[score_v3_B] rendering bass drone ...", flush=True)
D1 = 26  # D1 ~= 36.7 Hz
D2 = 38  # D2 ~= 73.4 Hz
bass = bass_drone(D1, D2, TOTAL_S, seed=15)
# amp env: fade in over 4 bars, hold, fade out over 6 bars
be = np.ones(N_TOTAL)
be[:bar_to_i(4)] = np.linspace(0, 1, bar_to_i(4))**1.4
foL = bar_to_i(74); be[foL:] = np.linspace(1, 0, N_TOTAL-foL)**1.4
# subtle harmonic-lift boost during peak
i0, i1 = bar_to_i(32), bar_to_i(64)
peak_boost = np.ones(N_TOTAL); peak_boost[i0:i1] = np.linspace(1.0, 1.15, i1-i0)
peak_boost[i1:] = np.linspace(1.15, 1.0, N_TOTAL-i1)
bass *= be * peak_boost * 0.55

# ---- KICK ---------------------------------------------------------------
print("[score_v3_B] scheduling kick ...", flush=True)
kick_track = np.zeros(N_TOTAL)
K_variants = [soft_kick(vel=1.0, seed=i) for i in range(6)]
def add_kick(t_s, vel=1.0):
    K = K_variants[rng.integers(0,6)] * vel
    place(kick_track, humanize(t_s, 3.0), K)

# Bars 8..15: kick on beat 1, low velocity ramp
for b in range(8, 16):
    v = 0.35 + 0.055*(b-8)   # 0.35 -> 0.735
    add_kick(b*BAR + 0*BEAT, vel=v)
# Bars 16..31: kick on beat 1
for b in range(16, 32):
    add_kick(b*BAR + 0*BEAT, vel=0.85)
# Bars 32..63 PEAK: kick on beats 1 and 3 (halftime feel)
for b in range(32, 64):
    add_kick(b*BAR + 0*BEAT, vel=1.0)
    add_kick(b*BAR + 2*BEAT, vel=0.92)
# Bars 64..71 release: back to beat 1 only, decreasing
for b in range(64, 72):
    v = 0.85 - 0.075*(b-64)   # 0.85 -> ~0.325
    add_kick(b*BAR + 0*BEAT, vel=v)
# Bars 72..79: no kick (wash)

# ---- SHAKER -------------------------------------------------------------
print("[score_v3_B] scheduling shaker ...", flush=True)
shaker_track_L = np.zeros(N_TOTAL)
shaker_track_R = np.zeros(N_TOTAL)
S_variants = [shaker(vel=1.0, seed=i) for i in range(8)]
def add_shaker(t_s, vel=1.0, pan=0.0):
    S = S_variants[rng.integers(0,8)] * vel * (0.85 + 0.15*rng.random())
    L_gain = np.sqrt(0.5*(1 - pan))
    R_gain = np.sqrt(0.5*(1 + pan))
    ts = humanize(t_s, 5.0)
    place(shaker_track_L, ts, S, gain=L_gain)
    place(shaker_track_R, ts, S, gain=R_gain)

# Bars 16..63: 8ths (8 per bar), gentle swing (55/45), alternating pan
for b in range(16, 64):
    for e8 in range(8):
        # swing: even 8ths (0,2,4,6) on grid, odd (1,3,5,7) delayed 10% of eighth
        swing = 0.10*(BEAT/2) if (e8 % 2 == 1) else 0
        t = b*BAR + e8*(BEAT/2) + swing
        # emphasize downbeats slightly
        v = 0.55 if e8 % 2 == 0 else 0.38
        # ramp-in over bars 16..19
        if b < 20: v *= (b-16)/4.0 + 0.15
        # ramp-out over bars 60..63
        if b >= 60: v *= max(0, (64-b)/4.0)
        pan = 0.55 if e8 % 2 == 0 else -0.55
        pan *= 0.7
        add_shaker(t, vel=v, pan=pan)

# Bars 64..71: quarter shakers, tapering
for b in range(64, 72):
    for bt in range(4):
        v = 0.42 * (72-b)/8.0
        add_shaker(b*BAR + bt*BEAT, vel=v, pan=0.3*((-1)**bt))

# ---- DARBUKA ACCENTS ----------------------------------------------------
print("[score_v3_B] scheduling darbuka accents ...", flush=True)
darb_track = np.zeros(N_TOTAL)
D_variants = [darbuka_accent(vel=1.0, seed=i) for i in range(4)]
def add_darb(t_s, vel=1.0):
    D = D_variants[rng.integers(0,4)] * vel
    place(darb_track, humanize(t_s, 6.0), D)

# Occasional accents: bar 15 beat 3.5, bar 23 beat 3.5, bar 31 beat 3.5 (build punctuation)
add_darb(15*BAR + 3.5*BEAT, vel=0.5)
add_darb(23*BAR + 3.5*BEAT, vel=0.6)
add_darb(31*BAR + 3.5*BEAT, vel=0.75)   # anticipation of the peak
# Peak: darbuka every 4 bars on beat 4 for pulse
for b in [35, 39, 43, 47, 51, 55, 59, 63]:
    add_darb(b*BAR + 3.0*BEAT, vel=0.7)
    # add a soft tak on beat 4.5 half the time
    if rng.random() < 0.5:
        add_darb(b*BAR + 3.5*BEAT, vel=0.35)

# ---- NEY LEAD -----------------------------------------------------------
print("[score_v3_B] rendering ney lead ...", flush=True)
ney_track = np.zeros(N_TOTAL)

def ney_phrase(bar_start, notes):
    """notes: list of (midi, dur_beats, vel). Silent-slot midi = None."""
    t = bar_start * BAR
    for i, (m, d, v) in enumerate(notes):
        dur_s = d * BEAT
        if m is not None:
            note = ney_note(m, dur_s, vel=v, seed=int(bar_start*7 + i))
            place(ney_track, humanize(t, 6.0), note)
        t += dur_s

# --- BUILD SECTION PHRASES (bars 8..31, very sparse) ---
# Bars 8..15: motif A — quiet high-register question
# D5 (2 beats) rest(2) — Eb5(2) D5(1) rest(1)  — total 8 beats = 2 bars, sparse
ney_phrase(9, [
    (D5,  2.0, 0.55), (None, 2.0, 0),
    (Eb5, 2.0, 0.55), (D5,  1.5, 0.50), (None, 0.5, 0),
])                                                    # bars 9..10
ney_phrase(12, [
    (C5,  1.5, 0.55), (Bb4, 1.0, 0.50), (A4, 2.5, 0.55), (None, 3.0, 0),
])                                                    # bars 12..13

# Bars 16..23: motif B — mid-register answer, breath at bar 19
ney_phrase(17, [
    (F4s, 1.5, 0.60), (G4, 1.0, 0.58),
    (A4,  1.5, 0.62), (Bb4, 1.0, 0.60), (A4, 2.0, 0.60), (None, 1.0, 0),
])                                                    # bars 17..18
ney_phrase(20, [
    (F4s, 2.0, 0.60), (G4, 1.5, 0.58), (A4, 2.5, 0.62),
    (F4s, 3.0, 0.55), (None, 3.0, 0),
])                                                    # bars 20..22

# Bars 24..31: silence + one long D4 anchor (bar 28..30)
ney_phrase(27, [
    (D4, 6.0, 0.62), (None, 2.0, 0),                  # bars 27..28
])
ney_phrase(30, [
    (F4s, 4.0, 0.55), (None, 4.0, 0),                 # anticipation
])

# --- PEAK SECTION PHRASES (bars 32..63) ---
# Motif C: climb — F#4 G4 A4 Bb4 A4 G4 F#4 D4
ney_phrase(33, [
    (F4s, 1.0, 0.72), (G4, 1.0, 0.70), (A4, 1.0, 0.72), (Bb4, 1.5, 0.75),
    (A4, 1.0, 0.72), (G4, 1.0, 0.70), (F4s, 1.5, 0.68), (None, 0.0, 0),
])                                                    # bars 33..35
ney_phrase(36, [
    (D4, 3.0, 0.65), (F4s, 2.5, 0.68), (None, 2.5, 0),
])                                                    # 36..37

# Bars 40..47: motif A variation, higher register (D5..A5)
ney_phrase(41, [
    (D5, 1.5, 0.78), (Eb5, 1.0, 0.72), (D5, 2.5, 0.75), (None, 3.0, 0),
])
ney_phrase(44, [
    (F5s, 1.5, 0.80), (G5, 1.0, 0.75), (F5s, 1.0, 0.72), (Eb5, 1.5, 0.70),
    (D5, 3.0, 0.72), (None, 2.0, 0),
])                                                    # 44..47

# Bars 48..55: motif B answer, more elaborated
ney_phrase(49, [
    (A4, 1.0, 0.72), (Bb4, 1.0, 0.72), (A4, 1.0, 0.70), (G4, 1.0, 0.68),
    (F4s, 2.0, 0.65), (D4, 2.0, 0.62), (None, 1.0, 0),  # (a full 2 bars)
])
ney_phrase(52, [
    (F4s, 1.5, 0.72), (G4, 1.0, 0.70), (A4, 1.0, 0.72), (Bb4, 1.5, 0.75),
    (A4, 1.0, 0.72), (G4, 1.0, 0.70), (F4s, 2.0, 0.68), (None, 1.0, 0),
])                                                    # 52..54

# Bars 56..63: motif C climb high, tension via Eb5 and F#5, resolve to A5 briefly
ney_phrase(57, [
    (F4s, 1.0, 0.78), (A4, 1.0, 0.80), (D5, 1.0, 0.82), (Eb5, 1.5, 0.85),
    (F5s, 1.0, 0.85), (G5, 1.5, 0.82), (A5, 2.0, 0.85), (None, 1.0, 0),
])                                                    # 57..60
ney_phrase(61, [
    (G5, 1.0, 0.80), (F5s, 1.0, 0.78), (Eb5, 1.5, 0.75), (D5, 2.5, 0.75),
    (None, 2.0, 0),
])                                                    # 61..63

# --- RELEASE SECTION PHRASES (bars 64..79) ---
# Motif A slow, echoing, dropping
ney_phrase(65, [
    (A4, 2.5, 0.65), (G4, 2.0, 0.58), (F4s, 3.5, 0.55), (None, 4.0, 0),
])                                                    # 65..67
ney_phrase(70, [
    (F4s, 3.0, 0.55), (Eb4, 2.0, 0.50), (D4, 3.0, 0.55), (None, 4.0, 0),
])                                                    # 70..73
ney_phrase(75, [
    (D4, 10.0, 0.60), (None, 0.0, 0),                # long tonic anchor, ~2.5 bars
])
# very last: a soft D5 whisper into the fade
ney_phrase(78, [
    (D5, 4.0, 0.42), (None, 0.0, 0),
])

# ================================================================== MIXING
print("[score_v3_B] building reverb ...", flush=True)
ir_L = make_hall_ir(dur=4.2, decay_rate=1.15, seed=1)
ir_R = make_hall_ir(dur=4.2, decay_rate=1.15, seed=2)   # decorrelated

def reverb_wet_stereo(x_mono, ir_l, ir_r):
    return convolve_fft(x_mono, ir_l), convolve_fft(x_mono, ir_r)

print("[score_v3_B] convolving pad reverb ...", flush=True)
pad_L, pad_R = reverb_wet_stereo(pad_filt, ir_L, ir_R)
# blend dry pad + wet reverb (heavy wet: 55%)
pad_L = 0.45*pad_filt + 0.60*pad_L
pad_R = 0.45*pad_filt + 0.60*pad_R

print("[score_v3_B] convolving ney reverb ...", flush=True)
ney_L, ney_R = reverb_wet_stereo(ney_track, ir_L, ir_R)
ney_L = 0.50*ney_track + 0.70*ney_L
ney_R = 0.50*ney_track + 0.70*ney_R

print("[score_v3_B] convolving darbuka reverb ...", flush=True)
darb_L, darb_R = reverb_wet_stereo(darb_track, ir_L, ir_R)
darb_L = 0.60*darb_track + 0.55*darb_L
darb_R = 0.60*darb_track + 0.55*darb_R

# Kick: mostly dry (tiny short reverb so it "sits" in the room)
print("[score_v3_B] convolving kick reverb ...", flush=True)
short_ir = make_hall_ir(dur=1.4, decay_rate=3.2, seed=5)
kick_wet_L, kick_wet_R = reverb_wet_stereo(kick_track, short_ir, short_ir)
kick_L = kick_track + 0.12*kick_wet_L
kick_R = kick_track + 0.12*kick_wet_R

# Bass: dry (would just muddy in reverb)
bass_L = bass * 0.98
bass_R = bass * 1.02  # very subtle stereo diff via level

# Shaker: already stereo; add moderate reverb send
print("[score_v3_B] convolving shaker reverb ...", flush=True)
shk_wet_LL, shk_wet_LR = reverb_wet_stereo(shaker_track_L, ir_L, ir_R)
shk_wet_RL, shk_wet_RR = reverb_wet_stereo(shaker_track_R, ir_L, ir_R)
shk_L = 0.70*shaker_track_L + 0.28*(shk_wet_LL + shk_wet_RL*0.4)
shk_R = 0.70*shaker_track_R + 0.28*(shk_wet_RR + shk_wet_LR*0.4)

# ------------------------------------------------------------------ SUM BUS
print("[score_v3_B] summing bus ...", flush=True)
L = pad_L*0.42 + ney_L*0.55 + darb_L*0.42 + kick_L*0.78 + bass_L*0.82 + shk_L*0.38
R = pad_R*0.42 + ney_R*0.55 + darb_R*0.42 + kick_R*0.78 + bass_R*0.82 + shk_R*0.38

# Master HPF at 25 Hz (kill subsonic) and gentle master LPF taper above 15 kHz
L = hipass(L, 25, order=2); R = hipass(R, 25, order=2)

# Very gentle tape-style saturation
def sat(x, drive=1.12): return np.tanh(x*drive) / np.tanh(drive)
L = sat(L*0.92, 1.10)
R = sat(R*0.92, 1.10)

# soft knee limit + normalize
peak = max(np.max(np.abs(L)), np.max(np.abs(R))) + 1e-9
L = L / peak * 0.94
R = R / peak * 0.94

# ------------------------------------------------------------------ WRITE WAV
print(f"[score_v3_B] writing WAV -> {OUT_WAV}", flush=True)
def write_wav_stereo(path, L, R):
    L = np.clip(L, -1, 1); R = np.clip(R, -1, 1)
    fr = np.empty(L.size*2, dtype=np.float64)
    fr[0::2] = L; fr[1::2] = R[:L.size]
    pcm = (fr * 32767.0).astype(np.int16)
    with wave.open(path, 'w') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())

t0 = time.time()
write_wav_stereo(OUT_WAV, L, R)
print(f"[score_v3_B] WAV written in {time.time()-t0:.1f}s", flush=True)

# ------------------------------------------------------------------ MP3
print(f"[score_v3_B] encoding MP3 -> {OUT_MP3}", flush=True)
try:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", OUT_WAV, "-codec:a", "libmp3lame", "-qscale:a", "2", OUT_MP3],
        check=True
    )
    mp3_ok = True
except Exception as e:
    print(f"[score_v3_B] MP3 encode failed: {e}", flush=True)
    mp3_ok = False

# ------------------------------------------------------------------ SUMMARY
dur = N_TOTAL / SR
mm = int(dur // 60); ss = dur - mm*60
print()
print("=" * 60)
print(f"SCORE_V3_B  duration = {mm}:{ss:05.2f}  ({dur:.2f}s)")
print(f"  BPM={BPM}  bars={BARS}  mode=Hijaz on D")
print(f"  WAV: {OUT_WAV}")
print(f"  MP3: {OUT_MP3 if mp3_ok else '(FAILED)'}")
print("=" * 60)
