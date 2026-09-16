#!/usr/bin/env python3
# ALMA Trance — "Freygish Circuit": original psytrance, Jewish+Eastern (Ahava-Rabbah / Hijaz).
# 100% ours: pure numpy synthesis. Score bed for "The Perceptron" documentary.
import numpy as np, wave, struct, os

SR = 44100
BPM = 145.0
BEAT = 60.0 / BPM            # seconds per beat
SIX = BEAT / 4.0             # sixteenth
BAR = BEAT * 4.0
N_BARS = 56
T = BAR * N_BARS
n = int(T * SR)
t = np.arange(n) / SR
rng = np.random.default_rng(11)   # seeded (Math.random unavailable elsewhere; fine here)

# --- Freygish / Ahava-Rabbah on E (the Jewish+Eastern mode): E F G# A B C D ---
ROOT = 41.20  # E1
SCALE = [0, 1, 4, 5, 7, 8, 10]      # semitone offsets
def hz(semi):  return ROOT * 2 ** (semi / 12.0)
def deg(i, octave=0):                # scale degree -> hz
    return hz(SCALE[i % 7] + 12 * (octave + i // 7))

out = np.zeros(n, dtype=np.float64)

def place(buf, start_s, sig):
    s = int(start_s * SR); e = min(s + len(sig), len(buf))
    if s < len(buf): buf[s:e] += sig[:e - s]

def env(dur, a=0.005, d=0.1, s=0.0, r=0.05, sus=0.6):
    N = int(dur * SR); e = np.zeros(N)
    ai, di, ri = int(a*SR), int(d*SR), int(r*SR)
    ai = max(ai,1); di = max(di,1); ri = max(ri,1)
    i = 0
    e[:ai] = np.linspace(0,1,ai); i=ai
    j = min(i+di, N); e[i:j] = np.linspace(1, sus, j-i); i=j
    hold = max(N-ri-i, 0); e[i:i+hold] = sus; i+=hold
    e[i:i+ri] = np.linspace(e[i-1] if i>0 else sus, 0, min(ri, N-i))
    return e

def saw(f, N):
    ph = np.cumsum(np.full(N, f/SR)); return 2*(ph - np.floor(ph+0.5))
def sine(f, N):
    return np.sin(2*np.pi*f/SR*np.arange(N))

def fft_lp(x, cutoff, res=1.0):
    X = np.fft.rfft(x); fr = np.fft.rfftfreq(len(x), 1/SR)
    m = np.ones(len(fr))
    m[fr>cutoff] = np.maximum(0, 1 - (fr[fr>cutoff]-cutoff)/(cutoff*1.5+1))
    if res>1.0:
        band = (fr>cutoff*0.7)&(fr<cutoff*1.3); m[band]*=res
    return np.fft.irfft(X*m, n=len(x))

# ---------- KICK (four on the floor) ----------
def kick():
    d=0.32; N=int(d*SR); tt=np.arange(N)/SR
    pitch=150*np.exp(-tt*35)+48
    body=np.sin(2*np.pi*np.cumsum(pitch)/SR)*np.exp(-tt*7.5)
    click=np.exp(-tt*350)*rng.standard_normal(N)*0.5
    return (body+click)*0.9
KICK=kick()
kick_env=np.zeros(n)
for b in range(N_BARS*4):
    place(out, b*BEAT, KICK)
    s=int(b*BEAT*SR); e=min(s+len(KICK),n)
    seg=np.exp(-np.arange(e-s)/ (0.18*SR))
    kick_env[s:e]=np.maximum(kick_env[s:e], seg)
sidechain = 1 - 0.85*kick_env       # duck everything on the kick

# ---------- OFFBEAT ROLLING BASS (the psytrance engine) ----------
bass=np.zeros(n)
for b in range(N_BARS*4):            # per beat: rest(kick), bass, bass, bass
    for s16 in (1,2,3):
        st=b*BEAT + s16*SIX
        note=deg(0,0) if (b%8)!=7 else deg(6,-1)   # mostly root, turnaround
        N=int(SIX*0.95*SR)
        sg=saw(note,N)+0.5*saw(note*1.005,N)
        sg=fft_lp(sg, 220, res=1.3)*env(SIX*0.95, a=0.004,d=0.06,sus=0.2,r=0.02)
        place(bass, st, sg*0.9)
bass*=sidechain

# ---------- PAD (Freygish chords, slow, atmospheric) ----------
pad=np.zeros(n)
prog=[(0,3,4),(0,3,6),(-1,2,3),(0,3,4)]   # scale-degree triads (Freygish color)
for bar in range(N_BARS):
    ch=prog[(bar//4)%len(prog)]
    N=int(BAR*SR)
    seg=np.zeros(N)
    for dg_ in ch:
        f=deg(dg_,2)
        seg+=saw(f,N)+saw(f*1.003,N)+0.6*sine(f*0.5,N)
    seg=fft_lp(seg, 1400)*env(BAR, a=0.35,d=0.4,sus=0.55,r=0.4)
    place(pad, bar*BAR, seg*0.14)
pad*=(0.6+0.4*sidechain)

# ---------- ACID LEAD (Freygish arpeggio, resonant, Eastern melody) ----------
lead=np.zeros(n)
motif=[0,2,1,4,3,6,4,7,6,4,3,2,1,0,1,2]   # a snaking Freygish/Hijaz phrase
for bar in range(N_BARS):
    for k in range(16):
        st=bar*BAR + k*SIX
        dgi=motif[k]
        f=deg(dgi,3)
        N=int(SIX*0.9*SR)
        cut=600+2600*(0.5+0.5*np.sin(bar*0.5+k*0.4))   # filter sweep = acid
        sg=saw(f,N)*0.7+saw(f*0.995,N)*0.3
        sg=fft_lp(sg, cut, res=2.2)*env(SIX*0.9, a=0.003,d=0.05,sus=0.25,r=0.03)
        place(lead, st, sg*0.5)
lead*=sidechain

# ---------- HATS (offbeat shimmer) ----------
hats=np.zeros(n)
for b in range(N_BARS*4):
    st=b*BEAT+BEAT/2; N=int(0.05*SR)
    h=fft_lp(rng.standard_normal(N),12000); h=h-fft_lp(h,7000)
    h*=np.exp(-np.arange(N)/(0.02*SR))
    place(hats, st, h*0.25)

# ---------- DARBUKA (maqsum: Dum . tek tek . Dum . tek .) ----------
perc=np.zeros(n)
def dum():
    N=int(0.14*SR); tt=np.arange(N)/SR
    return (np.sin(2*np.pi*(90*np.exp(-tt*22)+60)*tt)*np.exp(-tt*16))*0.8
def tek():
    N=int(0.06*SR); tt=np.arange(N)/SR
    return (fft_lp(rng.standard_normal(N),9000)*np.exp(-tt*45))*0.5
DUM,TEK=dum(),tek()
pat={0:DUM,1.5:TEK,2:TEK,3:DUM,3.5:TEK}   # positions in beats within a bar
for bar in range(N_BARS):
    for pos,snd in pat.items():
        place(perc, bar*BAR+pos*BEAT, snd)

# ---------- ARRANGEMENT (fade instruments in over sections) ----------
def ramp(a_bar,b_bar):
    g=np.zeros(n)
    sa,sb=int(a_bar*BAR*SR),int(b_bar*BAR*SR)
    g[sb:]=1.0; g[sa:sb]=np.linspace(0,1,max(sb-sa,1)); return g
g_pad=ramp(0,4); g_perc=ramp(4,8); g_kick=ramp(8,10)
g_bass=ramp(12,16); g_lead=ramp(24,28); g_hat=ramp(16,20)
# breakdown at bars 40-44: pull kick+bass
brk=np.ones(n); s,e=int(40*BAR*SR),int(44*BAR*SR); brk[s:e]=np.linspace(1,0.15,e-s)
brk2=np.ones(n); brk2[e:e+int(2*BAR*SR)]=np.linspace(0.15,1,int(2*BAR*SR))

mix = ( out*g_kick*brk*brk2*0.9
      + bass*g_bass*brk*brk2
      + pad*g_pad
      + lead*g_lead
      + hats*g_hat
      + perc*g_perc )

# light stereo + reverb tail (comb)
def reverb(x, dl=0.09, fb=0.3):
    d=int(dl*SR); y=x.copy()
    for k in range(1,4):
        s=d*k; y[s:]+=x[:-s]*(fb**k)
    return y
wet=reverb(mix)*0.25
L=mix+wet; R=mix+np.roll(wet, int(0.012*SR))
# soft limiter
def lim(x):
    x=x/ (np.max(np.abs(x))+1e-9); return np.tanh(x*1.4)*0.95
L,R=lim(L),lim(R)

# write 16-bit stereo WAV
path=os.path.join(os.path.dirname(__file__),"alma_freygish_psytrance.wav")
frames=np.empty(L.size*2); frames[0::2]=L; frames[1::2]=R
pcm=(frames*32767).astype(np.int16)
with wave.open(path,'w') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print(f"WROTE {path}  ({T:.1f}s, {BPM:.0f} BPM, Freygish/Ahava-Rabbah)")
