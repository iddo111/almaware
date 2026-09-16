#!/usr/bin/env python3
# "כאן חללית האם" v2 — karaoke + transmission. Intro-solo + 2-min mid guitar-solo space.
import numpy as np, wave, os, sys
SR=44100; BPM=182.0; BEAT=60/BPM; BAR=BEAT*4; EI=BEAT/2
HERE=os.path.dirname(__file__)
def hz(m): return 440*2**((m-69)/12)
PROG=[hz(47),hz(50),hz(43),hz(45)]   # Bm D G A per bar

# section plan (name, bars)
SECTIONS=[("intro_solo",22),("verse1",8),("chorus1",8),("verse2",8),
          ("chorus2",8),("guitar_solo",90),("chorus3",8),("outro",4)]
bar0={}; b=0
for nm,nb in SECTIONS: bar0[nm]=b; b+=nb
TOTAL=b
n=int(TOTAL*BAR*SR); out=np.zeros(n); rng=np.random.default_rng(7)
def place(buf,s,sig):
    i=int(s*SR); e=min(i+len(sig),len(buf))
    if i<len(buf): buf[i:e]+=sig[:e-i]
def saw(f,N): ph=np.cumsum(np.full(N,f/SR)); return 2*(ph-np.floor(ph+0.5))
def dist(x,d=6.0): return np.tanh(x*d)
def strum_env(N,a=0.002,d=0.14):
    e=np.ones(N); ai=max(int(a*SR),1); e[:ai]=np.linspace(0,1,ai)
    return e*np.exp(-np.arange(N)/(d*SR))
def powerchord(root,N):
    x=saw(root,N)+0.9*saw(root*2**(7/12),N)+0.7*saw(root*2,N)+0.5*saw(root*0.5,N)
    return dist(x*0.4,7.0)
# rhythm guitar + bass across ALL bars (backing you sing/solo over)
gtr=np.zeros(n); bass=np.zeros(n)
for bar in range(TOTAL):
    root=PROG[bar%4]
    for e8 in range(8):
        st=bar*BAR+e8*EI; N=int(EI*0.92*SR)
        acc=1.0 if e8%2==0 else 0.6
        place(gtr,st,powerchord(root,N)*strum_env(N)*0.30*acc)
        place(bass,st,dist(saw(root/2,N)*0.6,3)*strum_env(N,d=0.16)*0.28)
# drums
def kick():
    N=int(0.22*SR);tt=np.arange(N)/SR
    return (np.sin(2*np.pi*(120*np.exp(-tt*32)+50)*tt)*np.exp(-tt*9))*0.95
def snare():
    N=int(0.18*SR);tt=np.arange(N)/SR
    return (0.5*np.sin(2*np.pi*190*tt)*np.exp(-tt*22)+0.9*rng.standard_normal(N)*np.exp(-tt*16))*0.7
def hat():
    N=int(0.05*SR);tt=np.arange(N)/SR
    return (rng.standard_normal(N)*np.exp(-tt/0.012))*0.22
K,S,H=kick(),snare(),hat()
drum=np.zeros(n)
for bar in range(TOTAL):
    intro=bar<bar0["verse1"]
    for bt in range(4):
        place(drum,bar*BAR+bt*BEAT,K)
        if bt in(1,3): place(drum,bar*BAR+bt*BEAT,S)
    for e8 in range(8): place(drum,bar*BAR+e8*EI,H*(0.7 if intro else 1.0))
# arrangement gain: intro builds guitars in
g=np.ones(n)
gi=int(bar0["verse1"]*BAR*SR)
g[:gi]*=np.linspace(0.15,0.9,gi)  # intro: quieter rhythm (room for intro solo)
mix=drum*0.9+(gtr+bass)*g
mix=mix/(np.max(np.abs(mix))+1e-9); mix=np.tanh(mix*1.5)*0.95
def write(path,L,R):
    fr=np.empty(L.size*2); fr[0::2]=L; fr[1::2]=R[:L.size]
    pcm=(np.clip(fr,-1,1)*32767).astype(np.int16)
    with wave.open(path,'w') as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes(pcm.tobytes())
R=np.concatenate([[0,0],mix[:-2]])*0.85+mix*0.15
write(os.path.join(HERE,"anthem_karaoke.wav"),mix,R)
print(f"KARAOKE {TOTAL*BAR:.1f}s  intro_solo~{22*BAR:.0f}s  guitar_solo~{90*BAR:.0f}s")

# ---- TRANSMISSION: overlay robotic vocal wavs if present in ./vocals ----
VOX=os.path.join(HERE,"vocals")
# (line_index -> bar position). one line per listed bar.
LINES=[("v1",bar0["verse1"]+0),("v1b",bar0["verse1"]+2),("v1c",bar0["verse1"]+4),("v1d",bar0["verse1"]+6),
       ("c1",bar0["chorus1"]+0),("c1b",bar0["chorus1"]+3),("c1c",bar0["chorus1"]+5),
       ("v2",bar0["verse2"]+0),("v2b",bar0["verse2"]+2),("v2c",bar0["verse2"]+4),("v2d",bar0["verse2"]+6),
       ("c2",bar0["chorus2"]+0),("c2b",bar0["chorus2"]+3),("c2c",bar0["chorus2"]+5),
       ("c3",bar0["chorus3"]+0),("c3b",bar0["chorus3"]+3),("c3c",bar0["chorus3"]+5),
       ("end",bar0["outro"]+0)]
def radio(x):  # radio/transmission effect: bandpass-ish + slight drive + tremolo
    X=np.fft.rfft(x); fr=np.fft.rfftfreq(len(x),1/SR)
    m=np.ones(len(fr)); m[fr<300]*=0.2; m[fr>3400]*=0.15
    y=np.fft.irfft(X*m,n=len(x))
    trem=0.85+0.15*np.sin(2*np.pi*7*np.arange(len(y))/SR)
    return np.tanh(y*2.2)*trem
def load_wav(p):
    with wave.open(p,'r') as w:
        fr=w.getframerate();ch=w.getnchannels();d=np.frombuffer(w.readframes(w.getnframes()),np.int16).astype(np.float64)/32768
    if ch>1: d=d[0::ch]
    if fr!=SR: d=np.interp(np.linspace(0,len(d),int(len(d)*SR/fr)),np.arange(len(d)),d)
    return d
if os.path.isdir(VOX) and any(f.endswith('.wav') for f in os.listdir(VOX)):
    vmix=mix.copy()
    for name,barpos in LINES:
        fp=os.path.join(VOX,name+".wav")
        if os.path.exists(fp):
            v=radio(load_wav(fp))*0.9
            place(vmix,barpos*BAR+0.05,v)
    vmix=vmix/(np.max(np.abs(vmix))+1e-9); vmix=np.tanh(vmix*1.3)*0.95
    Rv=np.concatenate([[0,0],vmix[:-2]])*0.85+vmix*0.15
    write(os.path.join(HERE,"anthem_transmission.wav"),vmix,Rv)
    print("TRANSMISSION written")
else:
    print("no vocals/ dir yet — karaoke only (run vocal gen first)")
