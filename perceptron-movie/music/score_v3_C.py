#!/usr/bin/env python3
# ==============================================================
# SCORE TAKE C — Progressive Psy for The Perceptron (tech portions)
# 128 BPM. Bayati-like mode on D (neutral 2nd + neutral 3rd).
# Progressive structure: sparse intro, layers add every 16 bars,
# big drop at bar 65, filter opens 16 bars then closes 8 bars.
# Fast 16th-note bass arpeggios. Western-friendly modal color.
# ==============================================================
import numpy as np
import wave, subprocess, sys, time
from pathlib import Path
from scipy.signal import iirfilter, lfilter, iirpeak, butter, sosfilt, fftconvolve

t0 = time.time()

SR = 44100
BPM = 128.0
BEAT = 60.0 / BPM            # 0.46875 s
SIX  = BEAT / 4.0
BAR  = BEAT * 4.0            # 1.875 s
N_BARS   = 96                # ~ 3 min
DROP_BAR = 65                # 1-indexed
T_TOTAL  = BAR * N_BARS
n = int(T_TOTAL * SR)
t = np.arange(n) / SR
bar_pos = t / BAR + 1.0      # 1-indexed bar position (float)
rng = np.random.default_rng(3)

# ---------- Bayati mode on D ----------
# Cents from root: D=0, Eb+ (neutral 2nd)=150, F+ (neutral 3rd)=350,
# G=500, A=700, Bb=800, C=1000
ROOT = 36.7081  # D1
BAYATI = [0, 150, 350, 500, 700, 800, 1000]

def hz(deg_idx, octave=0):
    d = deg_idx % 7
    o = octave + deg_idx // 7
    cents = BAYATI[d] + 1200 * o
    return ROOT * 2 ** (cents / 1200.0)

# ---------- Oscillators ----------
def saw_wave(f, N, phase0=0.0):
    if np.isscalar(f):
        ph = phase0 + np.cumsum(np.full(N, f/SR))
    else:
        ph = phase0 + np.cumsum(np.asarray(f)/SR)
    return 2*(ph - np.floor(ph+0.5))

def sine_wave(f, N, phase0=0.0):
    if np.isscalar(f):
        return np.sin(2*np.pi*f/SR*np.arange(N) + phase0)
    ph = phase0 + 2*np.pi*np.cumsum(np.asarray(f)/SR)
    return np.sin(ph)

def supersaw(f, N, voices=5, cents=8):
    """N-voice detuned saw with random phase per voice — real width."""
    x = np.zeros(N)
    for k in range(voices):
        c = cents * (k - (voices-1)/2) / max(1, (voices-1)/2)
        ff = f * 2**(c/1200.0)
        p0 = rng.uniform(0, 2*np.pi)
        x += saw_wave(ff, N, p0)
    return x / voices

# ---------- Envelope ----------
def adsr(N, a=0.005, d=0.05, s=0.5, r=0.05):
    e = np.zeros(N)
    ai = max(1, int(a*SR))
    di = max(1, int(d*SR))
    ri = max(1, int(r*SR))
    if ai >= N: ai = N-1
    e[:ai] = np.linspace(0, 1, ai)
    j = min(ai+di, N); e[ai:j] = np.linspace(1, s, j-ai)
    ri_start = max(j, N - ri)
    if ri_start > j: e[j:ri_start] = s
    tail_n = N - ri_start
    if tail_n > 0:
        prev = e[ri_start-1] if ri_start > 0 else s
        e[ri_start:] = np.linspace(prev, 0, tail_n)
    return e

# ---------- Real time-varying LP with resonance peak ----------
def modulated_lp(x, cutoff_arr, res=0.5, order=4, chunk_ms=15, peak=True):
    """Per-chunk cutoff, state-continuous. res in [0,1] boosts peak Q."""
    N = len(x)
    if np.isscalar(cutoff_arr):
        cutoff_arr = np.full(N, cutoff_arr)
    chunk = max(1, int(chunk_ms * SR / 1000))
    y_lp = np.zeros(N)
    y_pk = np.zeros(N)
    state_lp = np.zeros(order)
    state_pk = np.zeros(2)
    Q = 1.0 + res * 12
    for i in range(0, N, chunk):
        j = min(i + chunk, N)
        c = float(np.clip(np.mean(cutoff_arr[i:j]), 40, SR*0.45))
        w = c / (SR/2)
        b, a = iirfilter(order, w, btype='low', ftype='butter', output='ba')
        # pad/truncate state if needed
        if len(state_lp) != len(a)-1:
            state_lp = np.zeros(len(a)-1)
        y_lp[i:j], state_lp = lfilter(b, a, x[i:j], zi=state_lp)
        if peak and res > 0.05:
            try:
                b2, a2 = iirpeak(w, Q)
                y_pk[i:j], state_pk = lfilter(b2, a2, x[i:j], zi=state_pk)
            except Exception:
                pass
    return y_lp + y_pk * res * 0.45

# ---------- Placement helper ----------
def place(buf, start_s, sig):
    s = int(start_s * SR)
    e = min(s + len(sig), len(buf))
    if s < len(buf) and e > s:
        buf[s:e] += sig[:e-s]

def bar_start(bar1):
    return (bar1 - 1) * BAR

def piecewise(bar_pos_arr, points):
    xs = np.array([p[0] for p in points], dtype=np.float64)
    ys = np.array([p[1] for p in points], dtype=np.float64)
    return np.interp(bar_pos_arr, xs, ys)

# ---------- Drum synth ----------
def kick():
    d = 0.35
    N = int(d*SR)
    tt = np.arange(N)/SR
    pitch = 130*np.exp(-tt*38) + 46
    body = np.sin(2*np.pi*np.cumsum(pitch)/SR) * np.exp(-tt*8)
    click = np.exp(-tt*400)*rng.standard_normal(N)*0.55
    sub = np.sin(2*np.pi*38*tt) * np.exp(-tt*3.5) * 0.35
    x = (body + click + sub) * 0.85
    return np.tanh(x * 1.4) * 0.9  # mild saturation

def snare():
    N = int(0.19*SR)
    tt = np.arange(N)/SR
    body = np.sin(2*np.pi*200*tt) * np.exp(-tt*32) * 0.3
    noise = rng.standard_normal(N) * np.exp(-tt*22) * 0.65
    sos = butter(2, [800/(SR/2), 6500/(SR/2)], btype='band', output='sos')
    noise = sosfilt(sos, noise)
    return (body + noise) * 0.75

def hihat_closed():
    N = int(0.055*SR)
    tt = np.arange(N)/SR
    x = rng.standard_normal(N) * np.exp(-tt*100)
    sos = butter(4, 8500/(SR/2), btype='high', output='sos')
    return sosfilt(sos, x) * 0.35

def hihat_open():
    N = int(0.24*SR)
    tt = np.arange(N)/SR
    x = rng.standard_normal(N) * np.exp(-tt*11)
    sos = butter(4, 7200/(SR/2), btype='high', output='sos')
    return sosfilt(sos, x) * 0.32

KICK = kick()
SNAR = snare()
HH_C = hihat_closed()
HH_O = hihat_open()

# ============================================================
# STEMS
# ============================================================
print(f"[TAKE C] {N_BARS} bars @ {BPM} BPM = {T_TOTAL:.1f} s, drop at bar {DROP_BAR}")

out_pad   = np.zeros(n)
out_sub   = np.zeros(n)
out_bass  = np.zeros(n)
out_lead  = np.zeros(n)
out_kick  = np.zeros(n)
out_perc  = np.zeros(n)
out_riser = np.zeros(n)

# ============================================================
# PAD — throughout, chord progression in Bayati color
# ============================================================
# Scale-degree triads: i, VII, VI, i variant
CHORDS = [
    (0, 2, 4),  # D F+ A
    (6, 1, 3),  # C Eb+ G
    (5, 0, 2),  # Bb D F+
    (0, 2, 4),  # D F+ A
]
pad_bar_len = int(BAR * SR)
for bar in range(N_BARS):
    ch = CHORDS[(bar // 4) % len(CHORDS)]
    seg = np.zeros(pad_bar_len)
    for dg in ch:
        f = hz(dg, 1)
        seg += supersaw(f, pad_bar_len, voices=5, cents=10)
        seg += 0.28 * sine_wave(f * 0.5, pad_bar_len)
    seg /= max(1, len(ch))
    fade = int(0.025 * SR)
    seg[:fade] *= np.linspace(0, 1, fade)
    seg[-fade:] *= np.linspace(1, 0, fade)
    place(out_pad, bar_start(bar+1), seg)

# Pad cutoff: slow open through intro & buildup, wide open at drop, close at outro
cut_pad = piecewise(bar_pos, [
    (1, 350), (17, 900), (33, 1400), (49, 2000),
    (65, 3200), (81, 3600), (89, 900), (97, 300)
])
print(f"[TAKE C] filtering pad… ({time.time()-t0:.1f}s)")
out_pad = modulated_lp(out_pad, cut_pad, res=0.2, order=4)

# ============================================================
# SUB — long drone, layers in bar 17
# ============================================================
sub_start_bar = 17
sub_end_bar   = 93
sub_s0 = bar_start(sub_start_bar)
sub_s1 = bar_start(sub_end_bar+1)
sub_i0 = int(sub_s0 * SR)
sub_i1 = int(sub_s1 * SR)
sub_len = sub_i1 - sub_i0
if sub_len > 0:
    seg = sine_wave(ROOT, sub_len) * 0.55
    seg += 0.15 * sine_wave(ROOT * 2, sub_len)  # gentle first harmonic
    tt = np.arange(sub_len)/SR
    seg *= 0.7 + 0.3*np.sin(2*np.pi*0.15*tt)  # slow AM
    fi = int(8*BAR*SR); fo = int(4*BAR*SR)
    seg[:fi] *= np.linspace(0, 1, fi)
    seg[-fo:] *= np.linspace(1, 0, fo)
    place(out_sub, sub_s0, seg)

# ============================================================
# 16th-NOTE BASS ARPEGGIO — layers in bar 33, sweeps at drop
# ============================================================
# Scale-degree pattern per 16th (16 hits per bar). Root-heavy, octave stabs.
PAT_A = [0, 0, 0, 7, 0, 0, 4, 0, 0, 0, 7, 0, 0, 2, 4, 0]
PAT_B = [0, 7, 0, 0, 4, 0, 7, 0, 0, 3, 0, 7, 0, 0, 4, 0]
PAT_C = [0, 0, 7, 0, 0, 4, 0, 0, 7, 0, 0, 2, 0, 4, 0, 7]  # variation

arp_start_bar = 33
arp_end_bar   = 88
for bar in range(arp_start_bar, arp_end_bar + 1):
    blk = (bar - arp_start_bar) // 4
    pat = [PAT_A, PAT_B, PAT_A, PAT_C][blk % 4]
    for k in range(16):
        st = bar_start(bar) + k * SIX
        dg = pat[k]
        f = hz(dg, 0)
        N16 = int(SIX * 0.9 * SR)
        sg = saw_wave(f, N16) + 0.5*saw_wave(f*1.005, N16)
        sg += 0.35 * sine_wave(f, N16)  # sub layer
        # Velocity ramp during buildup — bars 33->64 grow from 0.35 -> 0.7
        # Drop 65->80 = 0.85; taper 81->88 = 0.85 -> 0.35
        if bar < 49:
            vel = 0.4 + (bar - 33)/16 * 0.15
        elif bar < 65:
            vel = 0.55 + (bar - 49)/16 * 0.2
        elif bar < 81:
            vel = 0.85
        else:
            vel = 0.85 - (bar - 80)/8 * 0.5
        sg *= adsr(N16, a=0.002, d=0.03, s=0.35, r=0.02) * vel
        place(out_bass, st, sg * 0.55)

# Bass filter — closed during quiet, opens through buildup, fully open at drop
cut_bass = piecewise(bar_pos, [
    (1, 90), (33, 250), (49, 500), (65, 1100), (81, 900), (89, 400), (97, 150)
])
print(f"[TAKE C] filtering bass… ({time.time()-t0:.1f}s)")
out_bass = modulated_lp(out_bass, cut_bass, res=0.35, order=4)

# ============================================================
# LEAD — Bayati motif, enters bar 49 (sparse), full at drop
# Filter opens over 16 bars post-drop (65->81), closes over 8 (81->89)
# ============================================================
# 16-note motifs
MOT_A = [0, 2, 4, 6, 4, 2, 0, 1, 0, 2, 3, 4, 3, 2, 1, 0]
MOT_B = [4, 6, 7, 6, 4, 3, 2, 4, 0, 3, 5, 7, 5, 3, 2, 0]
MOT_C = [7, 4, 6, 4, 2, 4, 0, 2, 0, 1, 2, 3, 4, 3, 2, 0]

lead_start_bar = 49
lead_end_bar   = 88
for bar in range(lead_start_bar, lead_end_bar + 1):
    blk = (bar - lead_start_bar) // 4
    motif = [MOT_A, MOT_B, MOT_A, MOT_C][blk % 4]
    sparse = bar < 65  # in the buildup, only every other 16th
    for k in range(16):
        if sparse and k % 2 == 1:
            continue
        dg = motif[k]
        f = hz(dg, 2)  # up 2 octaves = mid/high lead
        N16 = int(SIX * 0.9 * SR)
        sg = supersaw(f, N16, voices=5, cents=8)
        sg *= adsr(N16, a=0.003, d=0.04, s=0.4, r=0.03)
        vol = 0.4 if sparse else 0.6
        place(out_lead, bar_start(bar) + k*SIX, sg * vol)

# Lead cutoff — the DRAMA
# Bars 49-63 (buildup): 800 (moderate)
# Bar 64: dip to 300 (tension)
# Bar 65 (drop) -> Bar 81: opens 400 -> 5500 over 16 bars
# Bar 81 -> Bar 89: closes 5500 -> 400 over 8 bars
# Bar 89 -> outro: 400 -> 200
cut_lead = piecewise(bar_pos, [
    (1, 500), (49, 800), (63, 800), (64, 350),
    (65, 450), (81, 5500), (89, 400), (97, 200)
])
print(f"[TAKE C] filtering lead… ({time.time()-t0:.1f}s)")
out_lead = modulated_lp(out_lead, cut_lead, res=0.75, order=4)

# ============================================================
# KICK — four-on-floor bars 49..88, with lift on beat 4 of bar 64
# ============================================================
for bar in range(49, 89):
    for beat in range(4):
        if bar == 64 and beat == 3:
            continue  # gap for the lift
        v = 1.0 + rng.uniform(-0.04, 0.04)
        jitter = rng.uniform(-0.003, 0.003)
        place(out_kick, bar_start(bar) + beat*BEAT + jitter, KICK * v)

# ============================================================
# HATS — closed 16ths from bar 33 (offbeats emphasized), open every 8 hits
# ============================================================
for bar in range(33, 89):
    for k in range(16):
        if k == 0:
            continue  # skip downbeat (kick territory)
        v = 0.28 + rng.uniform(-0.05, 0.05)
        jitter = rng.uniform(-0.003, 0.003)
        st = bar_start(bar) + k*SIX + jitter
        if k == 8:
            place(out_perc, st, HH_O * v * 0.7)
        else:
            place(out_perc, st, HH_C * v)

# ============================================================
# SNARE — backbeat during drop (65-88), plus roll at bar 64 buildup climax
# ============================================================
for bar in range(65, 89):
    for beat in [1, 3]:
        v = 0.85 + rng.uniform(-0.08, 0.08)
        jitter = rng.uniform(-0.003, 0.003)
        place(out_perc, bar_start(bar) + beat*BEAT + jitter, SNAR * v)

# Snare roll at bar 64 — accelerating
roll_bar = 64
# beat 1: 8ths (2 hits)
for k in range(2):
    place(out_perc, bar_start(roll_bar) + 0*BEAT + k*(BEAT/2), SNAR * (0.55 + k*0.05))
# beat 2: 16ths (4 hits)
for k in range(4):
    place(out_perc, bar_start(roll_bar) + 1*BEAT + k*(BEAT/4), SNAR * (0.65 + k*0.04))
# beat 3: 32nds (8 hits) accelerating vol
for k in range(8):
    place(out_perc, bar_start(roll_bar) + 2*BEAT + k*(BEAT/8), SNAR * (0.75 + k*0.03))
# beat 4: silence (lift)

# ============================================================
# RISER — white-noise sweep bars 60-64 into drop
# + reverse cymbal 2s pre-drop + impact hit on drop
# ============================================================
riser_i0 = int(bar_start(60) * SR)
riser_i1 = int(bar_start(65) * SR)
riser_n = riser_i1 - riser_i0
if riser_n > 0:
    noise = rng.standard_normal(riser_n) * 0.5
    cut_ris = np.linspace(300, 11000, riser_n)
    vol_ris = np.linspace(0.05, 0.65, riser_n) ** 1.4
    print(f"[TAKE C] filtering riser… ({time.time()-t0:.1f}s)")
    filt = modulated_lp(noise, cut_ris, res=0.2, order=2, chunk_ms=30, peak=False)
    out_riser[riser_i0:riser_i1] += filt * vol_ris

# Reverse cymbal 2s -> drop
rc_end = int(bar_start(DROP_BAR) * SR)
rc_dur = 2.0
rc_i0  = max(0, rc_end - int(rc_dur * SR))
rc_n   = rc_end - rc_i0
if rc_n > 0:
    cym = rng.standard_normal(rc_n)
    sos = butter(4, 6000/(SR/2), btype='high', output='sos')
    cym = sosfilt(sos, cym)
    cym *= np.linspace(0, 0.42, rc_n)
    out_riser[rc_i0:rc_end] += cym

# Impact hit
imp_i0 = int(bar_start(DROP_BAR) * SR)
imp_n  = int(0.6 * SR)
if imp_i0 + imp_n < n:
    imp = rng.standard_normal(imp_n)
    sos = butter(2, 2800/(SR/2), btype='low', output='sos')
    imp = sosfilt(sos, imp)
    imp *= np.exp(-np.arange(imp_n)/(0.14*SR)) * 0.55
    out_riser[imp_i0:imp_i0+imp_n] += imp

# ============================================================
# SIDECHAIN — build kick envelope, duck bass/lead/pad/sub
# ============================================================
print(f"[TAKE C] sidechain… ({time.time()-t0:.1f}s)")
kick_env = np.zeros(n)
atk_n = int(0.005 * SR)
rel_n = int(0.20 * SR)
for bar in range(49, 89):
    beats = [0, 1, 2] if bar == 64 else [0, 1, 2, 3]
    for beat in beats:
        s = int((bar_start(bar) + beat * BEAT) * SR)
        # Attack rise (short)
        if s + atk_n < n:
            kick_env[s:s+atk_n] = np.maximum(kick_env[s:s+atk_n],
                                              np.linspace(0, 1, atk_n))
        # Exponential release
        if s + atk_n + rel_n < n:
            rel = np.exp(-np.arange(rel_n)/(0.055*SR))
            kick_env[s+atk_n:s+atk_n+rel_n] = np.maximum(
                kick_env[s+atk_n:s+atk_n+rel_n], rel)

sidechain      = 1 - 0.65 * kick_env
sidechain_soft = 1 - 0.35 * kick_env

out_bass = out_bass * sidechain
out_lead = out_lead * sidechain
out_pad  = out_pad  * sidechain_soft
out_sub  = out_sub  * (1 - 0.75*kick_env)  # sub fights kick hardest -> duck hard

# ============================================================
# REVERB — synthetic plate IR, applied to pad/lead/perc
# ============================================================
def make_ir(dur_s=1.4, hp=280, lp=7500, decay_tau=0.45):
    N = int(dur_s * SR)
    ir = rng.standard_normal(N)
    ir *= np.exp(-np.arange(N)/(decay_tau*SR))
    sos = butter(2, [hp/(SR/2), lp/(SR/2)], btype='band', output='sos')
    ir = sosfilt(sos, ir)
    ir /= (np.max(np.abs(ir))+1e-9)
    return ir * 0.5

IR = make_ir(1.3, 300, 7200, 0.42)

def conv_rev(x, ir, wet=0.3):
    y = fftconvolve(x, ir)[:len(x)]
    return x * (1-wet) + y * wet

print(f"[TAKE C] reverb… ({time.time()-t0:.1f}s)")
out_lead = conv_rev(out_lead, IR, wet=0.32)
out_pad  = conv_rev(out_pad,  IR, wet=0.4)
out_perc = conv_rev(out_perc, IR, wet=0.18)

# ============================================================
# MIX
# ============================================================
mix = (out_pad   * 0.42 +
       out_sub   * 0.55 +
       out_bass  * 0.65 +
       out_lead  * 0.5  +
       out_kick  * 0.95 +
       out_perc  * 0.55 +
       out_riser * 0.5)

# Master chain — sat + subsonic HPF + gentle high shelf + normalize
mix = np.tanh(mix * 0.55) * 1.35

sos_hp = butter(2, 30/(SR/2), btype='high', output='sos')
mix = sosfilt(sos_hp, mix)

# Gentle presence boost around 3kHz (bandpass, mix in)
sos_pr = butter(2, [2500/(SR/2), 4500/(SR/2)], btype='band', output='sos')
mix = mix + 0.08 * sosfilt(sos_pr, mix)

# Air boost above 8kHz (highpass, mix in low amount)
sos_air = butter(2, 9000/(SR/2), btype='high', output='sos')
mix = mix + 0.08 * sosfilt(sos_air, mix)

# Normalize
peak = np.max(np.abs(mix))
if peak > 0:
    mix = mix / peak * 0.95

# Stereo widening via mid + Haas offset on right + small decorrelation
delay_samples = int(0.009 * SR)
R = np.zeros_like(mix)
R[delay_samples:] = mix[:-delay_samples]
R[:delay_samples] = mix[:delay_samples]
# Slight EQ diff L vs R for width
sos_lr = butter(2, 4000/(SR/2), btype='high', output='sos')
R = R + 0.05 * sosfilt(sos_lr, R)
L = mix - 0.03 * sosfilt(sos_lr, mix)

# Re-normalize stereo
mx = max(np.max(np.abs(L)), np.max(np.abs(R)), 1e-9)
L = L / mx * 0.95
R = R / mx * 0.95

stereo = np.stack([L, R], axis=1)

# ============================================================
# WRITE WAV + MP3
# ============================================================
out_dir = Path(__file__).resolve().parent
wav_path = out_dir / "score_v3_C.wav"
mp3_path = out_dir / "score_v3_C.mp3"

pcm = np.clip(stereo * 32767.0, -32768, 32767).astype(np.int16)
with wave.open(str(wav_path), 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(pcm.tobytes())

print(f"[TAKE C] WAV: {wav_path}  ({wav_path.stat().st_size/1024/1024:.2f} MB)")

# MP3
try:
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path),
         "-codec:a", "libmp3lame", "-b:a", "192k",
         "-ar", str(SR), str(mp3_path)],
        check=True, capture_output=True, text=True)
    print(f"[TAKE C] MP3: {mp3_path}  ({mp3_path.stat().st_size/1024/1024:.2f} MB)")
except subprocess.CalledProcessError as e:
    print(f"[TAKE C] MP3 conversion failed: {e.stderr[-500:] if e.stderr else e}", file=sys.stderr)

print(f"[TAKE C] Total time: {time.time()-t0:.1f}s")
print(f"[TAKE C] Structure summary:")
print(f"  bars 1-16  intro:      pad only, filter slowly opening")
print(f"  bars 17-32 layer 1:    +sub bass drone")
print(f"  bars 33-48 layer 2:    +16th arp bass, +hats, filter opens")
print(f"  bars 49-63 buildup:    +kick 4-on-floor, +lead motif (sparse)")
print(f"  bar  64    lift:       snare roll accelerating, kick gap on beat 4")
print(f"  bars 65-80 DROP:       full band, lead filter opens over 16 bars")
print(f"  bars 81-88 close:      lead filter closes over 8 bars")
print(f"  bars 89-96 outro:      elements fade, pad filter closes")
