#!/usr/bin/env python3
# "כאן חללית האם" — Cafe Clod anthem. 90s skate-punk, Bm-D-G-A. 100% ours (numpy).
import numpy as np, wave, os
SR=44100; BPM=182.0; BEAT=60/BPM; BAR=BEAT*4; EI=BEAT/2  # eighth
def hz(m): return 440*2**((m-69)/12)
# roots: B2 D3 G2 A2  (power-chord skate-punk progression, i III VI VII)
PROG=[hz(47), hz(50), hz(43), hz(45)]   # Bm D G A
N_LOOPS=13
song_bars=[]
# arrangement: intro(drums only 2) -> half-gain 4 -> full loops
total_bars=2+N_LOOPS*4
n=int(total_bars*BAR*SR); t=np.arange(n)/SR
out=np.zeros(n); rng=np.random.default_rng(7)
def place(buf,s,sig):
    i=int(s*SR); e=min(i+len(sig),len(buf))
    if i<len(buf): buf[i:e]+=sig[:e-i]
def saw(f,N): ph=np.cumsum(np.full(N,f/SR)); return 2*(ph-np.floor(ph+0.5))
def dist(x,drive=6.0): return np.tanh(x*drive)
def powerchord(root,N):
    fifth=root*2**(7/12); oct_=root*2
    x=saw(root,N)+0.9*saw(fifth,N)+0.7*saw(oct_,N)+0.5*saw(root*0.5,N)
    return dist(x*0.4,7.0)
def strum_env(N,a=0.002,d=0.14):
    e=np.ones(N); ai=int(a*SR); e[:ai]=np.linspace(0,1,ai)
    e*=np.exp(-np.arange(N)/(d*SR)); return e
# ---- guitars: down-picked 8th notes, palm-mute chug ----
gtr=np.zeros(n)
for bar in range(2,total_bars):
    root=PROG[(bar-2)%4]
    for e8 in range(8):
        st=bar*BAR+e8*EI
        dur=EI*0.92; N=int(dur*SR)
        mute=0.55 if e8%2==1 else 1.0     # accent downbeats
        sig=powerchord(root,N)*strum_env(N)*0.32*mute
        place(gtr,st,sig)
# ---- lead octave riff on chorus loops (last 6 loops) ----
lead=np.zeros(n)
riff=[0,0,7,0,10,7,0,-2]  # semitone offsets over root, snotty
for bar in range(2+7*4,total_bars):
    root=PROG[(bar-2)%4]
    for k in range(8):
        st=bar*BAR+k*EI; N=int(EI*0.9*SR)
        f=root*2*2**(riff[k]/12)
        sig=dist(saw(f,N)*0.5,4)*strum_env(N,d=0.1)*0.16
        place(lead,st,sig)
# ---- drums ----
def kick():
    N=int(0.22*SR);tt=np.arange(N)/SR
    return (np.sin(2*np.pi*(120*np.exp(-tt*32)+50)*tt)*np.exp(-tt*9))*0.95
def snare():
    N=int(0.18*SR);tt=np.arange(N)/SR
    tone=np.sin(2*np.pi*190*tt)*np.exp(-tt*22)
    nz=rng.standard_normal(N)*np.exp(-tt*16)
    return (0.5*tone+0.9*nz)*0.7
def hat(op=False):
    N=int((0.05 if not op else 0.12)*SR);tt=np.arange(N)/SR
    return (rng.standard_normal(N)*np.exp(-tt/(0.012 if not op else 0.05)))*0.22
K,S,H=kick(),snare(),hat()
drum=np.zeros(n)
for bar in range(total_bars):
    for b in range(4):
        place(drum,bar*BAR+b*BEAT,K)                 # four-on-floor punk kick
        if b in (1,3): place(drum,bar*BAR+b*BEAT,S)  # backbeat snare
    for e8 in range(8):
        place(drum,bar*BAR+e8*EI,H)                  # driving 8th hats
# ---- bass follows root ----
bass=np.zeros(n)
for bar in range(2,total_bars):
    root=PROG[(bar-2)%4]/2
    for e8 in range(8):
        st=bar*BAR+e8*EI;N=int(EI*0.95*SR)
        sig=dist(saw(root,N)*0.6,3)*strum_env(N,d=0.16)*0.3
        place(bass,st,sig)
# ---- arrangement gains ----
g=np.ones(n)
s2=int(2*BAR*SR); g[:s2]=0.0                 # bars 0-1 drums only
s6=int(6*BAR*SR); g[s2:s6]*=np.linspace(0.5,1,s6-s2)
mix = drum*0.9 + (gtr+bass)*g + lead
# master: light bus compression + limiter
mix=mix/(np.max(np.abs(mix))+1e-9)
mix=np.tanh(mix*1.5)*0.95
L=mix; R=np.concatenate([[0,0],mix[:-2]])*0.85+mix*0.15   # tiny width
frames=np.empty(L.size*2);frames[0::2]=L;frames[1::2]=R[:L.size]
pcm=(np.clip(frames,-1,1)*32767).astype(np.int16)
p=os.path.join(os.path.dirname(__file__),"cafe_clod_anthem.wav")
with wave.open(p,'w') as w:
    w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes(pcm.tobytes())
print(f"WROTE {p}  ({total_bars*BAR:.1f}s, {BPM:.0f} BPM, Bm-D-G-A skate punk)")
