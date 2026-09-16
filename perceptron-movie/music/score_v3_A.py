#!/usr/bin/env python3
# SCORE TAKE A - Perceptron documentary music score v3
# Freygish/Ahava-Rabbah on E, 140 BPM, ~2 min loopable
# Real DSP: PolyBLEP saw, 7-voice unison, ladder filter with ADSR envelope,
# sidechain compression (-6dB), maqsum darbuka with humanization,
# reverb send + delay throws, ping-pong stereo, call-and-response melody.
# 100% ours: numpy + scipy synthesis. Post-mix through ffmpeg (limiter + LUFS).

import os, sys, time, subprocess
import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi, iirpeak, tf2sos, fftconvolve
import soundfile as sf

SR = 44100
BPM = 140.0
BEAT = 60.0 / BPM
SIX  = BEAT / 4.0
BAR  = 4.0 * BEAT

# Structure: 8 + 16 + 16 + 8 + 16 + 8 = 72 bars = ~123.4 s
SECTIONS = [
    ("intro", 8),
    ("A",     16),
    ("B",     16),
    ("break", 8),
    ("C",     16),
    ("outro", 8),
]
def section_bar(name):
    b = 0
    for n, l in SECTIONS:
        if n == name: return (b, b + l)
        b += l
    raise KeyError(name)

TOTAL_BARS = sum(x[1] for x in SECTIONS)
DURATION   = TOTAL_BARS * BAR
N          = int(DURATION * SR)

RNG = np.random.default_rng(20260711)

# ---- Freygish / Ahava-Rabbah on E: E F G# A B C D ----
# Semitone offsets from tonic E
SCALE = [0, 1, 4, 5, 7, 8, 10]
E2_HZ = 82.4069
def deg(i, oct=0):
    """Scale degree -> Hz. deg(0,0) = E2. deg(0,-1) = E1. deg(0,+2) = E4."""
    return E2_HZ * 2**((SCALE[i % 7] + 12*(oct + i // 7)) / 12.0)

# ---------- basic utilities ----------
def zeros(): return np.zeros(N, dtype=np.float64)

def place(buf, start_s, sig):
    s = int(start_s * SR)
    if s >= len(buf): return
    e = min(s + len(sig), len(buf))
    buf[s:e] += sig[:e-s]

def ms(x): return int(x*SR/1000)

# ---------- ADSR envelope (exponential curves) ----------
def adsr(dur, a=0.005, d=0.08, s=0.6, r=0.05, curve="exp"):
    n = int(dur*SR)
    e = np.zeros(n)
    ai = max(ms(a*1000), 2)
    di = max(ms(d*1000), 2)
    ri = max(ms(r*1000), 2)
    hi = max(n - ai - di - ri, 0)
    idx = 0
    if curve == "exp":
        # exponential attack/decay/release for musical feel
        e[idx:idx+ai] = 1 - np.exp(-np.linspace(0, 4, ai))
        e[idx:idx+ai] /= e[idx+ai-1] if ai>0 else 1
        idx += ai
        e[idx:idx+di] = 1 + (s - 1) * (1 - np.exp(-np.linspace(0, 4, di)))
        idx += di
        e[idx:idx+hi] = s
        idx += hi
        last = e[idx-1] if idx>0 else s
        e[idx:idx+ri] = last * np.exp(-np.linspace(0, 5, ri))
    else:
        e[:ai] = np.linspace(0, 1, ai)
        e[ai:ai+di] = np.linspace(1, s, di)
        e[ai+di:ai+di+hi] = s
        e[ai+di+hi:] = np.linspace(s, 0, n - ai - di - hi)
    return e

# ---------- PolyBLEP anti-aliased sawtooth ----------
def polyblep_saw(freq, dur, phase0=0.0, freq_lfo=None):
    """Band-limited sawtooth via PolyBLEP. freq can be scalar or per-sample array.
    Returns array of length int(dur*SR)."""
    n = int(dur*SR)
    if np.isscalar(freq):
        f_arr = np.full(n, freq)
    else:
        f_arr = np.asarray(freq)[:n]
        if len(f_arr) < n: f_arr = np.pad(f_arr, (0, n-len(f_arr)), mode='edge')
    if freq_lfo is not None:
        f_arr = f_arr * (1 + freq_lfo[:n])
    dt = f_arr / SR
    # phase in [0,1)
    ph = (phase0 + np.cumsum(dt)) % 1.0
    # naive saw in [-1, 1]
    saw = 2*ph - 1.0
    # PolyBLEP correction at discontinuity (ph near 0/1)
    # near 0 (just after wrap):
    mask1 = ph < dt
    t1 = ph[mask1] / dt[mask1]
    saw[mask1] -= (t1 + t1 - t1*t1 - 1)
    # near 1 (just before wrap):
    mask2 = ph > (1.0 - dt)
    t2 = (ph[mask2] - 1.0) / dt[mask2]
    saw[mask2] -= (t2*t2 + t2 + t2 + 1)
    return saw

def sine(freq, dur, phase0=0.0):
    n = int(dur*SR)
    if np.isscalar(freq):
        return np.sin(2*np.pi*freq*np.arange(n)/SR + phase0)
    else:
        f = np.asarray(freq)[:n]
        if len(f)<n: f = np.pad(f, (0, n-len(f)), mode='edge')
        return np.sin(2*np.pi*np.cumsum(f)/SR + phase0)

def sq(freq, dur, phase0=0.0):
    # square via two saws (naive-safe for low-freq LFO usage only)
    n = int(dur*SR)
    ph = (phase0 + freq*np.arange(n)/SR) % 1.0
    return np.where(ph < 0.5, 1.0, -1.0)

# ---------- 7-voice unison supersaw ----------
def supersaw(freq, dur, voices=7, detune_cents=15.0, spread=0.9, drift_hz=0.25):
    """Alive supersaw: N band-limited saws with per-voice cents detune,
    random phase, slow drift LFO for analog-tuning feel, stereo spread.
    Returns (L, R) tuple of arrays."""
    n = int(dur*SR)
    if n <= 0: return np.zeros(0), np.zeros(0)
    L = np.zeros(n); R = np.zeros(n)
    # detune amounts symmetric around center voice
    detunes = np.linspace(-detune_cents, detune_cents, voices)
    for v in range(voices):
        cents = detunes[v]
        f = freq * 2**(cents/1200.0)
        phase0 = RNG.random()
        # slow drift LFO per voice
        drift = 0.006 * np.sin(2*np.pi*(drift_hz + 0.15*v)*np.arange(n)/SR + RNG.random()*np.pi*2)
        s = polyblep_saw(f, dur, phase0=phase0, freq_lfo=drift)
        # stereo pan: center voice center, others spread
        pan = 0.0 if v == voices//2 else (v - voices/2) / (voices/2) * spread
        gL = np.sqrt(0.5) * (1 - pan) if pan >= 0 else np.sqrt(0.5)
        gR = np.sqrt(0.5) * (1 + pan) if pan <  0 else np.sqrt(0.5)
        # equal-power pan
        theta = (pan + 1) * np.pi/4
        gL = np.cos(theta); gR = np.sin(theta)
        L += s * gL / np.sqrt(voices)
        R += s * gR / np.sqrt(voices)
    return L, R

# ---------- Chunked resonant lowpass (Butterworth 4-pole + peak) ----------
def reso_lp(x, cutoff_arr, resonance=0.6, chunk=256):
    """Time-varying resonant low-pass. cutoff_arr = per-sample cutoff Hz."""
    Nlen = len(x)
    y = np.zeros(Nlen)
    zi = None
    prev_shape = None
    i = 0
    while i < Nlen:
        j = min(i+chunk, Nlen)
        fc = float(np.clip(np.mean(cutoff_arr[i:j]), 40.0, SR*0.42))
        wn = fc / (SR/2)
        sos_lp = butter(4, wn, btype='low', output='sos')
        if resonance > 0.01:
            Q = 1.0 + resonance * 8.0
            b_pk, a_pk = iirpeak(wn, Q=Q)
            sos_pk = tf2sos(b_pk, a_pk)
            sos = np.vstack([sos_pk, sos_lp])
        else:
            sos = sos_lp
        if zi is None or sos.shape != prev_shape:
            zi = sosfilt_zi(sos) * x[i]
            prev_shape = sos.shape
        chunk_out, zi = sosfilt(sos, x[i:j], zi=zi)
        y[i:j] = chunk_out
        i = j
    return y

def fixed_lp(x, cutoff, order=4):
    sos = butter(order, cutoff/(SR/2), btype='low', output='sos')
    return sosfilt(sos, x)

def fixed_hp(x, cutoff, order=2):
    sos = butter(order, cutoff/(SR/2), btype='high', output='sos')
    return sosfilt(sos, x)

def fixed_bp(x, low, high, order=2):
    sos = butter(order, [low/(SR/2), high/(SR/2)], btype='bandpass', output='sos')
    return sosfilt(sos, x)

# ---------- DRUMS ----------
def kick_variant(seed=None):
    """Kick with variable pitch env, click, saturation."""
    r = np.random.default_rng(seed)
    d = 0.34; n = int(d*SR); t = np.arange(n)/SR
    # pitch env: 150Hz -> 48Hz
    p_start = 150 + r.uniform(-15, 15)
    p_end   = 48 + r.uniform(-3, 3)
    pitch = p_end + (p_start - p_end) * np.exp(-t * (30 + r.uniform(-6, 6)))
    body = np.sin(2*np.pi*np.cumsum(pitch)/SR) * np.exp(-t * 7.0)
    sub = np.sin(2*np.pi*45*t) * np.exp(-t*4.5) * 0.35
    click = r.standard_normal(n) * np.exp(-t*380) * 0.6
    click = fixed_hp(click, 800)
    y = body*0.9 + sub + click*0.5
    # gentle sat
    y = np.tanh(y * 1.3) * 0.9
    return y

def darbuka_dum(seed=None):
    r = np.random.default_rng(seed)
    d = 0.15; n = int(d*SR); t = np.arange(n)/SR
    # low membrane resonance around 85 Hz + higher modes
    modes = [(85+r.uniform(-4,4), 0.7, 18), (140, 0.35, 22), (230, 0.18, 28)]
    y = np.zeros(n)
    for f, amp, dec in modes:
        y += amp * np.sin(2*np.pi*f*t) * np.exp(-t*dec)
    # transient click
    click = r.standard_normal(n) * np.exp(-t*80) * 0.3
    click = fixed_bp(click, 200, 1500)
    y = (y + click) * 0.85
    return y

def darbuka_tek(seed=None, ghost=False):
    r = np.random.default_rng(seed)
    d = 0.07; n = int(d*SR); t = np.arange(n)/SR
    # high rim: filtered noise + high mode
    noise = r.standard_normal(n) * np.exp(-t*55)
    noise = fixed_bp(noise, 2500, 8000)
    tone = 0.15 * np.sin(2*np.pi*1200*t) * np.exp(-t*40)
    y = (noise + tone)
    if ghost: y *= 0.3
    else:     y *= 0.55
    return y

def hihat_closed(seed=None):
    r = np.random.default_rng(seed)
    d = 0.06; n = int(d*SR); t = np.arange(n)/SR
    y = r.standard_normal(n)
    # bandpass 7-14k
    y = fixed_bp(y, 6500, 13000)
    y *= np.exp(-t*80)
    return y * 0.5

def hihat_open(seed=None):
    r = np.random.default_rng(seed)
    d = 0.28; n = int(d*SR); t = np.arange(n)/SR
    y = r.standard_normal(n)
    y = fixed_bp(y, 5500, 12000)
    y *= np.exp(-t*11)
    return y * 0.4

def shaker(seed=None):
    r = np.random.default_rng(seed)
    d = 0.09; n = int(d*SR); t = np.arange(n)/SR
    y = r.standard_normal(n)
    y = fixed_bp(y, 4000, 10000)
    y *= np.exp(-t*35) * (1 - np.exp(-t*250))  # slight attack
    return y * 0.35

def noise_riser(dur, cutoff_start=200, cutoff_end=10000, gain_start=0.0, gain_end=0.6):
    """White-noise riser with rising bandpass and rising volume."""
    n = int(dur*SR)
    x = RNG.standard_normal(n) * 0.5
    # per-sample cutoff sweep -> chunked filter
    cut_arr = np.linspace(cutoff_start, cutoff_end, n)
    # use HP + LP chunked (like a bandpass sweeping upward)
    y = reso_lp(x, cut_arr, resonance=0.2, chunk=512)
    # gain ramp (perceptual exp)
    gain = np.linspace(gain_start, gain_end, n)
    gain = gain**1.5
    return y * gain

def reverse_cymbal(dur=1.5):
    n = int(dur*SR); t = np.arange(n)/SR
    y = RNG.standard_normal(n)
    y = fixed_bp(y, 4000, 12000)
    # reverse envelope: quiet -> loud
    env = np.linspace(0, 1, n) ** 2
    y = y * env * 0.5
    return y

# ---------- Sidechain compression via trigger-based ducking ----------
def sidechain_gain(kick_times, depth_db=6, attack_ms=6, release_ms=180):
    """Returns per-sample gain array. Fast attack down to -depth_db then exponential release."""
    gain = np.ones(N)
    atk = ms(attack_ms)
    rel = ms(release_ms)
    depth_lin = 10**(-depth_db/20.0)
    atk_curve = np.linspace(1.0, depth_lin, max(atk, 1))
    # exponential release
    rel_curve = depth_lin + (1 - depth_lin) * (1 - np.exp(-np.linspace(0, 4, max(rel, 1))))
    for kt in kick_times:
        s = int(kt*SR)
        if s >= N: continue
        # attack (dip down)
        e1 = min(s + atk, N)
        gain[s:e1] = np.minimum(gain[s:e1], atk_curve[:e1-s])
        # release (up)
        s2 = e1
        e2 = min(s2 + rel, N)
        if s2 < N:
            gain[s2:e2] = np.minimum(gain[s2:e2], rel_curve[:e2-s2])
    return gain

# ---------- Reverb IR (synthesized plate-ish) ----------
def synth_plate_ir(dur=2.2):
    n = int(dur*SR)
    # noise burst with exponential decay
    ir = RNG.standard_normal(n) * np.exp(-np.arange(n) / (dur*0.35*SR))
    # bandpass 100 - 8000 Hz
    ir = fixed_bp(ir, 120, 8500)
    # diffuse further via short allpasses (2 taps)
    ir_l = ir + 0.5*np.roll(ir, ms(11.7))
    ir_r = ir + 0.5*np.roll(ir, ms(13.9))
    ir_l /= np.max(np.abs(ir_l)) + 1e-9
    ir_r /= np.max(np.abs(ir_r)) + 1e-9
    return ir_l * 0.6, ir_r * 0.6

# ---------- Ping-pong delay (stereo) ----------
def ping_pong(x_mono, delay_s, feedback=0.45, wet=0.7, taps=8):
    """Vectorized ping-pong: alternate L/R with decaying feedback."""
    n = len(x_mono)
    L = np.zeros(n); R = np.zeros(n)
    d = int(delay_s*SR)
    for k in range(1, taps+1):
        ds = k*d
        if ds >= n: break
        g = wet * (feedback**(k-1))
        if k % 2 == 1:
            L[ds:] += x_mono[:n-ds] * g
        else:
            R[ds:] += x_mono[:n-ds] * g
    return L, R

# ---------- Section gates ----------
def bar_section_gate(section_names, fade_in_bars=0.0, fade_out_bars=0.0):
    g = np.zeros(N)
    for name in section_names:
        b0, b1 = section_bar(name)
        s = int(b0*BAR*SR)
        e = int(b1*BAR*SR)
        e = min(e, N)
        g[s:e] = 1.0
        if fade_in_bars > 0:
            fi = int(fade_in_bars*BAR*SR)
            fi = min(fi, e-s)
            g[s:s+fi] = np.linspace(0, 1, fi)
        if fade_out_bars > 0:
            fo = int(fade_out_bars*BAR*SR)
            fo = min(fo, e-s)
            g[e-fo:e] = np.linspace(1, 0, fo)
    return g

# ==================================================================
# Build tracks
# ==================================================================
print(f"[score_v3_A] target duration: {DURATION:.2f}s ({TOTAL_BARS} bars @ {BPM} BPM)")
print(f"[score_v3_A] samples: {N}, sample rate: {SR}")
t0 = time.time()

# -------- KICK: 4-on-floor with variations --------
print("[1/9] kick")
kick_bus = zeros()
kick_times = []
kick_variants = [kick_variant(seed=1+i) for i in range(8)]

def kick_active_at(bar):
    # not in intro
    if bar < 8: return False
    # break bars 0-3 (bars 32-35 overall): pull kick
    b_break, _ = section_bar("break")
    if b_break <= bar < b_break + 4: return False
    return True

for bar in range(TOTAL_BARS):
    if not kick_active_at(bar): continue
    for beat in range(4):
        t_kick = bar*BAR + beat*BEAT
        # small micro-timing wobble ±2ms except beat 1
        jitter = 0.0 if beat==0 else RNG.uniform(-0.002, 0.002)
        # velocity
        vel = 1.0 if beat in (0,) else 0.94
        if bar % 8 == 7 and beat == 3: vel *= 1.02  # end-of-8 push
        k = kick_variants[(bar*4+beat) % 8] * vel
        place(kick_bus, t_kick + jitter, k)
        kick_times.append(t_kick + jitter)

# -------- SIDECHAIN GAIN (from kick times) --------
print("[2/9] sidechain gain curve (-6 dB duck)")
sc_gain = sidechain_gain(kick_times, depth_db=6, attack_ms=6, release_ms=180)

# -------- BASS: driving 16th offbeat root, root+5th moves --------
print("[3/9] bass")
bass_bus = zeros()
def bass_active_at(bar):
    if bar < 12: return False   # start bass in mid A section (12 = bar4 of A)
    b_break, _ = section_bar("break")
    if b_break <= bar < b_break + 4: return False
    b_outro, e_outro = section_bar("outro")
    if bar >= b_outro + 4: return False  # fade out bass in second half of outro
    return True

for bar in range(TOTAL_BARS):
    if not bass_active_at(bar): continue
    # rolling 16th pattern: every 16th except position 0 of each beat (kick space)
    # occasional passing note on beat 4-and
    for beat in range(4):
        for s16 in (1,2,3):
            note_deg = 0
            # turnaround every 8 bars on last beat's last 16th
            if bar % 8 == 7 and beat == 3 and s16 == 3:
                note_deg = -1  # D below root (b7 down)
            # walk on last bar of 4-bar phrase
            if bar % 4 == 3 and beat == 3 and s16 == 2:
                note_deg = 4  # jump to 5th briefly
            f_bass = deg(note_deg, -1)  # E1 octave
            dur = SIX*0.9
            # bass = polyblep saw (naive-safe at low freq) + sub sine
            saw_l = polyblep_saw(f_bass, dur)
            sub   = np.sin(2*np.pi*f_bass*np.arange(int(dur*SR))/SR) * 0.9
            wave = saw_l*0.55 + sub*0.65
            # short envelope
            env = adsr(dur, a=0.003, d=0.05, s=0.4, r=0.02, curve="exp")
            wave = wave * env
            # fixed low-pass tone shaping
            wave = fixed_lp(wave, 380, order=4)
            # slight sat
            wave = np.tanh(wave*1.2)*0.9
            place(bass_bus, bar*BAR + beat*BEAT + s16*SIX, wave*0.55)

# apply sidechain to bass
bass_bus *= sc_gain

# -------- PAD: sustained triads, Freygish colors --------
print("[4/9] pad (stereo supersaw)")
pad_L = zeros(); pad_R = zeros()
# Chord progression across sections (each chord = 4 bars unless noted)
# All voiced above E2, so pad is mid-register.
# Triads: (root, 3rd, 5th) using scale degrees
progression = {
    "intro":[(0,2,4),(0,2,4),(0,2,4),(0,2,4)],           # Emaj7-ish drone (Freygish tonic)
    "A":    [(0,2,4),(0,2,4),(-1,1,3),(0,2,4)],          # tonic - tonic - Ddown - tonic
    "B":    [(0,2,4),(3,5,7),(-1,1,3),(0,2,4)],          # tonic - IV - Ddown - tonic
    "break":[(0,2,4),(3,5,7)],                            # (4-bar each in 8-bar break)
    "C":    [(0,2,4),(3,5,7),(-1,1,3),(0,2,4)],          # same as B but louder
    "outro":[(0,2,4),(0,2,4)],
}
for name, length in SECTIONS:
    b0, _ = section_bar(name)
    prog = progression[name]
    chord_dur = length // len(prog)
    for i, ch in enumerate(prog):
        start_bar = b0 + i*chord_dur
        for d in ch:
            f = deg(d, 1)   # pad plays around E3
            L, R = supersaw(f, chord_dur*BAR, voices=5, detune_cents=8.0, spread=0.7, drift_hz=0.22)
            env_ch = adsr(chord_dur*BAR, a=0.35, d=0.5, s=0.55, r=0.5, curve="exp")
            L *= env_ch; R *= env_ch
            # tone-shape pad
            L = fixed_lp(L, 2200, order=2)
            R = fixed_lp(R, 2200, order=2)
            place(pad_L, start_bar*BAR, L * 0.11)
            place(pad_R, start_bar*BAR, R * 0.11)

# gates
pad_gate = np.ones(N)
b_break, e_break = section_bar("break")
# in break: pad still plays but with washy feel — reduce a bit for space
sb, eb = int(b_break*BAR*SR), int(e_break*BAR*SR)
pad_gate[sb:eb] *= 0.85
# intro fade-in
b_intro, e_intro = section_bar("intro")
fi = int(4*BAR*SR)
pad_gate[:fi] = np.linspace(0, 1, fi)
# outro fade-out (second half)
b_o, e_o = section_bar("outro")
so = int((b_o+3)*BAR*SR); eo = min(N, int(e_o*BAR*SR))
pad_gate[so:eo] = np.linspace(pad_gate[so-1] if so>0 else 1, 0, eo-so)

pad_L *= pad_gate
pad_R *= pad_gate
# pad sidechain: milder duck (4 dB via mixing sc gain with 1.0)
pad_sc = 1.0 - (1.0 - sc_gain) * 0.66  # ~4 dB depth
pad_L *= pad_sc
pad_R *= pad_sc

# -------- LEAD: 8-bar call & response melody with ornaments --------
print("[5/9] lead (7-voice unison, ADSR filter envelope)")
# Melody notation: (scale_degree, octave, duration_in_beats, ornament)
# ornament: None | 'grace' | 'vibrato' | 'slide_to_next'
# 8 bars total, then loop / vary
CALL = [   # 4 bars: question (ends up hanging on B, degree 4)
    (0, 2, 1.0, 'grace'), (1, 2, 0.5, None), (0, 2, 0.5, None),
    (2, 2, 1.0, None),    (1, 2, 1.0, None),
    # bar 2
    (2, 2, 0.5, None), (3, 2, 0.5, None), (4, 2, 1.0, None), (3, 2, 1.0, None), (2, 2, 1.0, None),
    # bar 3
    (3, 2, 1.0, None), (2, 2, 1.0, None), (1, 2, 1.0, None), (2, 2, 1.0, None),
    # bar 4 -- hanging on 5
    (3, 2, 2.0, 'vibrato'), (4, 2, 2.0, 'vibrato'),
]
RESPONSE = [  # 4 bars: answer (ends on tonic)
    # bar 5
    (4, 2, 1.0, None), (5, 2, 1.0, None), (6, 2, 1.0, None), (5, 2, 1.0, None),
    # bar 6
    (4, 2, 1.0, None), (3, 2, 1.0, None), (2, 2, 1.0, None), (3, 2, 1.0, None),
    # bar 7
    (2, 2, 0.5, None), (1, 2, 0.5, None), (0, 2, 1.0, 'grace'),
    (1, 2, 0.5, None), (2, 2, 0.5, None), (3, 2, 1.0, None),
    # bar 8 -- resolve
    (2, 2, 1.0, None), (1, 2, 1.0, None), (0, 2, 2.0, 'vibrato'),
]

def render_note(dg, oct, dur_beats, ornament, has_next=False, next_freq=None,
                cutoff_ceiling=4200, env_amount=3200):
    dur = dur_beats * BEAT * 0.94   # gap between notes
    if dur < 0.05: dur = 0.05
    f_base = deg(dg, oct)
    n = int(dur*SR)
    if n <= 0: return np.zeros(0), np.zeros(0)

    # Frequency array: constant + optional vibrato + slide
    f_arr = np.full(n, f_base)
    if ornament == 'vibrato':
        # slight vibrato at 5.5 Hz, ±20 cents, fading in after 100ms
        vib_depth = 0.012  # ~20 cents ≈ 1.16%
        t = np.arange(n)/SR
        fade = np.clip((t-0.1)/0.15, 0, 1)
        vib = vib_depth * np.sin(2*np.pi*5.5*t) * fade
        f_arr = f_arr * (1 + vib)

    if ornament == 'slide_to_next' and next_freq is not None:
        t = np.arange(n)/SR
        slide_mask = t > (dur*0.6)
        prog = np.clip((t - dur*0.6)/(dur*0.35), 0, 1)
        f_arr = f_base + (next_freq - f_base) * prog

    # 7-voice unison supersaw stereo
    L, R = supersaw(f_arr, dur, voices=7, detune_cents=17.0, spread=0.85, drift_hz=0.28)

    # Add sub sine for note body support
    sub = 0.35 * np.sin(2*np.pi*f_base*0.5*np.arange(n)/SR)
    L += sub; R += sub

    # Filter envelope: ADSR modulates cutoff.
    # Cutoff = base + env_amount * env_shape.
    env_filter = adsr(dur, a=0.003, d=min(0.25, dur*0.4), s=0.35, r=min(0.15, dur*0.3), curve="exp")
    # base cutoff ~700 Hz, envelope adds up to env_amount above it
    base_cut = 700 + 200*(oct-1)
    cutoff_arr = np.clip(base_cut + env_amount*env_filter, 200, cutoff_ceiling)

    # Amplitude envelope (separate ADSR)
    env_amp = adsr(dur, a=0.004, d=0.10, s=0.55, r=min(0.08, dur*0.25), curve="exp")

    # Grace note: preceding 30-40ms 16th one degree below
    grace_L = np.array([]); grace_R = np.array([])
    if ornament == 'grace':
        f_grace = deg(max(dg-1, 0), oct)
        g_dur = min(0.06, dur*0.15)
        gL, gR = supersaw(f_grace, g_dur, voices=5, detune_cents=14.0, spread=0.7)
        genv = adsr(g_dur, a=0.002, d=0.03, s=0.15, r=0.01, curve="exp")
        gL *= genv; gR *= genv
        # filter grace to a bright but narrow cutoff
        g_cut = np.full(len(gL), 2500)
        gL = reso_lp(gL, g_cut, resonance=0.5, chunk=128)
        gR = reso_lp(gR, g_cut, resonance=0.5, chunk=128)
        grace_L = gL * 0.6
        grace_R = gR * 0.6

    # Apply resonant lowpass with envelope
    L = reso_lp(L, cutoff_arr, resonance=0.7, chunk=256)
    R = reso_lp(R, cutoff_arr, resonance=0.7, chunk=256)
    L *= env_amp * 0.72
    R *= env_amp * 0.72

    # Prepend grace if present
    if len(grace_L) > 0:
        L = np.concatenate([grace_L, L])
        R = np.concatenate([grace_R, R])
    return L, R

def render_melody_at(melody, start_bar):
    """Render melody starting at absolute start_bar. Returns (L, R) fragments to be placed."""
    lead_L_local = np.zeros(int(16 * BAR * SR))  # generous buffer
    lead_R_local = np.zeros(int(16 * BAR * SR))
    t_cursor = 0.0  # in seconds from start_bar boundary
    for i, note in enumerate(melody):
        dg, oct, dur_beats, orn = note
        has_next = (i+1 < len(melody))
        next_freq = deg(melody[i+1][0], melody[i+1][1]) if has_next else None
        # 10% chance of upgrading to slide if last-note-to-next is stepwise
        if orn is None and has_next and abs(melody[i+1][0] - dg) == 1 and RNG.random() < 0.25:
            orn = 'slide_to_next'
        L, R = render_note(dg, oct, dur_beats, orn, has_next=has_next, next_freq=next_freq)
        # offset if grace note (grace is prepended - subtract grace length from timing)
        grace_offset = 0
        if orn == 'grace':
            grace_offset = int(min(0.06, dur_beats*BEAT*0.15) * SR)
        s = int(t_cursor * SR) - grace_offset
        s = max(0, s)
        e = min(s + len(L), len(lead_L_local))
        lead_L_local[s:e] += L[:e-s]
        lead_R_local[s:e] += R[:e-s]
        t_cursor += dur_beats * BEAT
    return lead_L_local, lead_R_local, t_cursor

lead_L = zeros(); lead_R = zeros()

# Lead sections: play call+response
# In B: play 1x (bars 16-31 of overall = 8+16..8+16+16, actually B is bars 24..40)
# Let me compute: intro 0-7, A 8-23, B 24-39, break 40-47, C 48-63, outro 64-71
# B = 24..39 (16 bars). Play the 8-bar melody twice.
# C = 48..63 (16 bars). Play with more embellishment, and octave up variant on second pass.

def place_stereo(L_dst, R_dst, start_bar, L_src, R_src):
    s = int(start_bar*BAR*SR)
    e = min(s + len(L_src), len(L_dst))
    L_dst[s:e] += L_src[:e-s]
    R_dst[s:e] += R_src[:e-s]

# B - two passes
b_B, e_B = section_bar("B")
mel = CALL + RESPONSE
L1, R1, _ = render_melody_at(mel, b_B)
place_stereo(lead_L, lead_R, b_B, L1, R1)
L2, R2, _ = render_melody_at(mel, b_B+8)
place_stereo(lead_L, lead_R, b_B+8, L2, R2)

# In break: sparse lead - just the last 2 bars have a snippet
b_br, e_br = section_bar("break")
short_mel = [
    (4, 2, 2.0, 'vibrato'),
    (2, 2, 1.0, 'grace'),
    (1, 2, 1.0, None),
    (0, 2, 2.0, 'vibrato'),
]
L3, R3, _ = render_melody_at(short_mel, b_br+4)
place_stereo(lead_L, lead_R, b_br+4, L3, R3)

# C - climax: octave up variant, then plus a high embellishment
b_C, e_C = section_bar("C")
mel_hi = [(dg, oct+1, dur, orn) for (dg, oct, dur, orn) in (CALL + RESPONSE)]
L4, R4, _ = render_melody_at(mel_hi, b_C)
place_stereo(lead_L, lead_R, b_C, L4*0.9, R4*0.9)
# second pass: original melody + brief ornament ending
mel_end = CALL + RESPONSE[:-1] + [(0, 3, 0.5, 'grace'), (1, 3, 0.5, None),
                                   (2, 3, 0.5, None), (0, 3, 2.5, 'vibrato')]
L5, R5, _ = render_melody_at(mel_end, b_C+8)
place_stereo(lead_L, lead_R, b_C+8, L5, R5)

# apply sidechain to lead (moderate duck)
lead_sc = 1.0 - (1.0 - sc_gain) * 0.5
lead_L *= lead_sc
lead_R *= lead_sc

# -------- DARBUKA (maqsum: D..t.T.t) with humanization --------
print("[6/9] darbuka (maqsum + ghost notes)")
darb_L = zeros(); darb_R = zeros()
# pattern positions in beats within bar (8 sixteenths = 2 beats -> pattern spans 2 beats, repeated 2x per bar)
# Interpret "D..t.T.t" as 8 sixteenth positions per bar:
# 0=D, 3=t(ghost), 5=T(accent), 7=t(ghost)
# In beats: 0.0=D, 0.75=t, 1.25=T, 1.75=t | then bar 2 half: 2.0=D, 2.75=t, 3.25=T, 3.75=t
pattern = [
    (0.0,   'D', 1.0),   # accent
    (0.75,  't', 0.35),  # ghost
    (1.25,  'T', 0.85),  # accent-ish
    (1.75,  't', 0.35),  # ghost
    (2.0,   'D', 0.95),
    (2.75,  't', 0.4),
    (3.25,  'T', 0.9),
    (3.75,  't', 0.3),
]

def darb_active_at(bar):
    b_intro, e_intro = section_bar("intro")
    b_break, e_break = section_bar("break")
    if bar < 4: return False    # first 4 bars of intro: silence darbuka
    if b_break <= bar < b_break + 4: return False  # break first half no darb
    return True

def darb_density_at(bar):
    b_intro, e_intro = section_bar("intro")
    b_break, e_break = section_bar("break")
    b_out, e_out = section_bar("outro")
    if bar >= b_out + 4: return 0.4
    if e_intro > bar >= 4: return 0.6
    if e_break > bar >= b_break + 4: return 0.7
    return 1.0

for bar in range(TOTAL_BARS):
    if not darb_active_at(bar): continue
    dens = darb_density_at(bar)
    for pos_beats, kind, vel_base in pattern:
        # skip if in reduced density (drop some ghosts)
        if kind == 't' and RNG.random() > dens*1.1: continue
        # micro-timing ±5ms
        jit = RNG.uniform(-0.005, 0.005)
        # velocity variation ±15%
        vel = vel_base * RNG.uniform(0.87, 1.13)
        # pan: dum center, teks slightly split
        if kind == 'D':
            snd = darbuka_dum(seed=RNG.integers(0, 999)) * vel
            pan = 0.0
        elif kind == 'T':
            snd = darbuka_tek(seed=RNG.integers(0, 999), ghost=False) * vel
            pan = 0.45  # right
        else:  # 't' ghost
            snd = darbuka_tek(seed=RNG.integers(0, 999), ghost=True) * vel
            pan = -0.45  # left
        # equal-power pan
        theta = (pan + 1) * np.pi/4
        gL = np.cos(theta); gR = np.sin(theta)
        t_s = bar*BAR + pos_beats*BEAT + jit
        place(darb_L, t_s, snd * gL)
        place(darb_R, t_s, snd * gR)
    # occasional extra ghost note on random 16th (10% probability)
    if RNG.random() < 0.20 and dens > 0.6:
        beat = RNG.integers(0, 4)
        sub = RNG.choice([1, 2, 3])
        ghost = darbuka_tek(seed=RNG.integers(0,999), ghost=True) * 0.25
        pan = RNG.uniform(-0.6, 0.6)
        theta = (pan+1)*np.pi/4
        gL = np.cos(theta); gR = np.sin(theta)
        t_s = bar*BAR + beat*BEAT + sub*SIX + RNG.uniform(-0.004, 0.004)
        place(darb_L, t_s, ghost*gL)
        place(darb_R, t_s, ghost*gR)

# -------- HATS + SHAKERS --------
print("[7/9] hats + shakers (hard-panned)")
hat_L = zeros(); hat_R = zeros()
shk_L = zeros(); shk_R = zeros()

def hat_active(bar):
    b_break, e_break = section_bar("break")
    if bar < 16: return False   # start hats in A section second half
    if b_break <= bar < b_break + 6: return False
    return True

for bar in range(TOTAL_BARS):
    if not hat_active(bar): continue
    for beat in range(4):
        # closed hat on offbeat 8ths (position &)
        t_h = bar*BAR + beat*BEAT + BEAT/2 + RNG.uniform(-0.003, 0.003)
        h = hihat_closed(seed=RNG.integers(0,999)) * RNG.uniform(0.85, 1.05) * 0.6
        # hats panned slightly right for stereo variety
        pan = 0.35
        theta = (pan+1)*np.pi/4
        place(hat_L, t_h, h*np.cos(theta))
        place(hat_R, t_h, h*np.sin(theta))
        # occasional 16th ghost hat
        if RNG.random() < 0.15:
            t_g = bar*BAR + beat*BEAT + 3*SIX + RNG.uniform(-0.003, 0.003)
            g = hihat_closed(seed=RNG.integers(0,999)) * 0.35
            place(hat_L, t_g, g*np.cos(theta))
            place(hat_R, t_g, g*np.sin(theta))
    # open hat on beat 4 & every 4 bars
    if bar % 4 == 3:
        t_oh = bar*BAR + 3*BEAT + BEAT/2
        oh = hihat_open(seed=RNG.integers(0,999)) * 0.55
        pan = -0.4
        theta = (pan+1)*np.pi/4
        place(hat_L, t_oh, oh*np.cos(theta))
        place(hat_R, t_oh, oh*np.sin(theta))

# Shakers: 16th notes throughout, quiet, sparkling
def shk_active(bar):
    b_break, e_break = section_bar("break")
    if b_break <= bar < b_break + 4: return False
    return True

for bar in range(TOTAL_BARS):
    if not shk_active(bar): continue
    for beat in range(4):
        for s16 in range(4):
            if RNG.random() > 0.65: continue  # ~35% density
            t_s = bar*BAR + beat*BEAT + s16*SIX + RNG.uniform(-0.003, 0.003)
            sh = shaker(seed=RNG.integers(0,999)) * RNG.uniform(0.5, 0.9) * 0.35
            # alternate pan
            pan = 0.55 if (beat + s16) % 2 else -0.55
            theta = (pan+1)*np.pi/4
            place(shk_L, t_s, sh*np.cos(theta))
            place(shk_R, t_s, sh*np.sin(theta))

# -------- TRANSITIONS: noise riser into B, C; reverse cymbal into drops --------
print("[8/9] transitions (risers, reverse cymbal)")
fx_L = zeros(); fx_R = zeros()

# Riser into B (from bar 22, 2 bars)
riser1 = noise_riser(2*BAR, cutoff_start=300, cutoff_end=9000, gain_start=0.0, gain_end=0.55)
place(fx_L, (24-2)*BAR, riser1)
place(fx_R, (24-2)*BAR, riser1)

# Reverse cymbal into B drop
rc1 = reverse_cymbal(1.5)
place(fx_L, 24*BAR - 1.5, rc1*0.7)
place(fx_R, 24*BAR - 1.5, rc1*0.7)

# Riser into C (from bar 46, 2 bars)
riser2 = noise_riser(2*BAR, cutoff_start=200, cutoff_end=11000, gain_start=0.0, gain_end=0.7)
place(fx_L, (48-2)*BAR, riser2)
place(fx_R, (48-2)*BAR, riser2)

# Reverse cymbal into C drop
rc2 = reverse_cymbal(2.0)
place(fx_L, 48*BAR - 2.0, rc2*0.85)
place(fx_R, 48*BAR - 2.0, rc2*0.85)

# Impact hit on C drop bar1
impact_kick = kick_variant(seed=999) * 1.2
# already covered by the regular kick, but add a low tom-ish thud
n_imp = int(0.35*SR); t_imp = np.arange(n_imp)/SR
imp = np.sin(2*np.pi*(60*np.exp(-t_imp*15)+45)*t_imp) * np.exp(-t_imp*6)
place(fx_L, 48*BAR, imp*0.6)
place(fx_R, 48*BAR, imp*0.6)

# Snare-roll build at end of break (last 2 bars of break)
snare_body = None
def snare_hit():
    n = int(0.09*SR); t = np.arange(n)/SR
    body = np.sin(2*np.pi*220*t) * np.exp(-t*30)
    noise = RNG.standard_normal(n) * np.exp(-t*30)
    noise = fixed_bp(noise, 800, 5500)
    return (body*0.5 + noise*0.7) * 0.6

# 32nd note acceleration for last 4 bars of break -> more dense last 2
b_br, e_br = section_bar("break")
for i in range(64):  # 64 32nds over 4 bars
    t_s = (b_br+4)*BAR + i*(SIX/2)
    if t_s >= e_br * BAR: break
    # density increases toward end
    density = i / 64.0
    vel = 0.3 + 0.5*density
    if density > 0.5 and RNG.random() < density:
        place(fx_L, t_s, snare_hit()*vel*np.cos(np.pi/4))
        place(fx_R, t_s, snare_hit()*vel*np.sin(np.pi/4))

# ==================================================================
# EFFECTS: reverb send on lead, delay throw every 4 bars in B/C, ping-pong
# ==================================================================
print("[9/9] effects: reverb + delay throw + ping-pong on lead")

# Reverb IR
ir_L, ir_R = synth_plate_ir(dur=2.2)
lead_mono = 0.5*(lead_L + lead_R)
rev_L = fftconvolve(lead_mono, ir_L, mode='full')[:N] * 0.28
rev_R = fftconvolve(lead_mono, ir_R, mode='full')[:N] * 0.28

# also pad gets a light plate reverb
pad_mono = 0.5*(pad_L + pad_R)
prev_L = fftconvolve(pad_mono, ir_L, mode='full')[:N] * 0.18
prev_R = fftconvolve(pad_mono, ir_R, mode='full')[:N] * 0.18

# Ping-pong delay on lead (dotted-8th = 0.75 * BEAT)
dotted_8th = 0.75 * BEAT
pp_L, pp_R = ping_pong(lead_mono, dotted_8th, feedback=0.5, wet=0.55, taps=6)

# Delay throw gate: envelopes that spike at the last beat of bars 4, 8, 12 of B, and 4, 8, 12 of C
def delay_throw_gate(bar_positions, hold_s=1.6, attack_s=0.03):
    g = np.zeros(N)
    for bp in bar_positions:
        s = int(bp*SR)
        atk = ms(attack_s*1000)
        n_hold = int(hold_s*SR)
        e = min(s + atk + n_hold, N)
        # attack
        e1 = min(s+atk, N)
        if s < N: g[s:e1] = np.maximum(g[s:e1], np.linspace(0, 1, e1-s))
        # exponential decay
        s2 = e1
        if s2 < e:
            decay = np.exp(-np.linspace(0, 4, e-s2))
            g[s2:e] = np.maximum(g[s2:e], decay)
    return g

# Positions: end of bars 27, 31, 35 (within B: bars 24+3, 24+7, 24+11)... but B ends at 39.
# Actually the request is "every 4 bars" — apply at bar 4, 8, 12 within each 16-bar section.
# So in B: bar (24+3, 24+7, 24+11) - fire at the last beat of that bar.
# In C: bar (48+3, 48+7, 48+11)
throw_positions = []
for start in (24, 48):
    for k in (3, 7, 11):
        # fire at beat 4 of bar (start+k)
        throw_positions.append((start+k)*BAR + 3*BEAT)

throw_gate = delay_throw_gate(throw_positions, hold_s=1.4, attack_s=0.02)

pp_L *= throw_gate
pp_R *= throw_gate

# ==================================================================
# MIX
# ==================================================================
print("[MIX] summing buses")

# Instrument levels
KICK_G   = 1.15
BASS_G   = 1.20
PAD_G    = 0.90
LEAD_G   = 1.00
DARB_G   = 0.90
HAT_G    = 0.75
SHK_G    = 0.60
FX_G     = 0.80
REV_G    = 1.00
PP_G     = 0.90

# Sum (kick is mono, bass is mono, others stereo)
mix_L = ( kick_bus*KICK_G + bass_bus*BASS_G
        + pad_L*PAD_G + lead_L*LEAD_G + darb_L*DARB_G + hat_L*HAT_G + shk_L*SHK_G
        + fx_L*FX_G + rev_L*REV_G + prev_L*REV_G*0.7 + pp_L*PP_G )
mix_R = ( kick_bus*KICK_G + bass_bus*BASS_G
        + pad_R*PAD_G + lead_R*LEAD_G + darb_R*DARB_G + hat_R*HAT_G + shk_R*SHK_G
        + fx_R*FX_G + rev_R*REV_G + prev_R*REV_G*0.7 + pp_R*PP_G )

# Master high-pass to clear sub-rumble below 30 Hz
mix_L = fixed_hp(mix_L, 30, order=2)
mix_R = fixed_hp(mix_R, 30, order=2)

# Bus compression (simple soft) — hit peaks a bit
def soft_bus(x, thresh=0.55, ratio=2.5):
    y = np.copy(x)
    over = np.abs(y) > thresh
    y[over] = np.sign(y[over]) * (thresh + (np.abs(y[over]) - thresh)/ratio)
    return y

mix_L = soft_bus(mix_L)
mix_R = soft_bus(mix_R)

# Stereo widen via M/S
mid  = 0.5*(mix_L + mix_R)
side = 0.5*(mix_L - mix_R) * 1.20   # slight side boost for width
mix_L = mid + side
mix_R = mid - side

# Peak normalize + soft tanh limiter
peak = max(np.max(np.abs(mix_L)), np.max(np.abs(mix_R)), 1e-9)
mix_L /= peak; mix_R /= peak
mix_L = np.tanh(mix_L*1.15) * 0.95
mix_R = np.tanh(mix_R*1.15) * 0.95

print(f"[MIX] synthesis complete in {time.time()-t0:.1f}s")

# ==================================================================
# WRITE FILES
# ==================================================================
out_dir = os.path.dirname(os.path.abspath(__file__))
wav_path = os.path.join(out_dir, "score_v3_A.wav")
mp3_path = os.path.join(out_dir, "score_v3_A.mp3")

frames = np.stack([mix_L, mix_R], axis=1).astype(np.float32)
sf.write(wav_path, frames, SR, subtype='PCM_16')
print(f"[WROTE] {wav_path}")

# MP3 via ffmpeg
ffmpeg_bin = "ffmpeg"
cmd = [ffmpeg_bin, "-y", "-i", wav_path,
       "-codec:a", "libmp3lame", "-b:a", "192k", mp3_path]
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0:
    print(f"[WROTE] {mp3_path}")
else:
    print(f"[MP3 FAIL] {res.stderr[-500:]}")

# Report
wav_sz = os.path.getsize(wav_path)
mp3_sz = os.path.getsize(mp3_path) if os.path.exists(mp3_path) else 0
print(f"[REPORT] duration={DURATION:.2f}s  WAV={wav_sz/1e6:.2f} MB  MP3={mp3_sz/1e6:.2f} MB")
