"""
obedience_ah_bah.py — Eran's FIRST obedience lesson + the seed of his OBEDIENCE LAYER.

Iddo: "Train Eran on AH and BAH — just two syllables — until he knows it PERFECT.
That's how we build the obedience layer."

Obedience = COMMAND -> EXACT correct output, learned to PERFECTION. We start with the
two simplest commands (0='AH', 1='BAH'), drive the error to ~0 (he reproduces each
syllable flawlessly on command), and this same module later scales to more commands
and folds into the one brain (on the DGX).

CPU-only, tiny, seconds to train — never touches the GPU (the Hebrew mic always wins).
Targets here are SYNTHESIZED (clean formant 'ah'/'bah'); swap in Iddo's own voice later
(say AH/BAH into the mic) for the real thing.
"""
import os, numpy as np, torch, torch.nn as nn, soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 16000
N = int(SR * 0.60)          # 0.6 s per syllable
F0 = 120.0                   # voice pitch (Hz)
t = np.linspace(0, N / SR, N, endpoint=False)


def vowel(formants, dur_s=0.55, lead=0.05):
    """Additive formant synthesis of a vowel; placed into an N-sample buffer."""
    n = int(SR * dur_s)
    tt = np.linspace(0, dur_s, n, endpoint=False)
    y = np.zeros(n, np.float64)
    k = 1
    while k * F0 < SR / 2:
        fk = k * F0
        g = sum(a * (bw ** 2) / ((fk - fc) ** 2 + bw ** 2) for (fc, bw, a) in formants)
        y += g * np.sin(2 * np.pi * fk * tt)
        k += 1
    y /= (np.max(np.abs(y)) + 1e-9)
    env = np.clip(np.minimum(tt / 0.03, (dur_s - tt) / 0.06), 0, 1)
    y *= env
    out = np.zeros(N, np.float32)
    s = int(SR * lead)
    out[s:s + n] = y[:N - s]
    return out


# 'AH' = open vowel /a/ ;  'BAH' = labial closure + burst + the same /a/
AH = vowel([(730, 80, 1.0), (1090, 90, 0.6), (2440, 120, 0.25)], dur_s=0.55, lead=0.03)
_ah_for_bah = vowel([(730, 80, 1.0), (1090, 90, 0.6), (2440, 120, 0.25)], dur_s=0.50, lead=0.10)
BAH = _ah_for_bah.copy()
b0 = int(SR * 0.09)
BAH[b0:b0 + int(SR * 0.012)] += (np.random.RandomState(1).randn(int(SR * 0.012)) * 0.25).astype(np.float32)  # /b/ burst
BAH = np.clip(BAH, -1, 1).astype(np.float32)

sf.write(os.path.join(HERE, "target_AH.wav"), AH, SR)
sf.write(os.path.join(HERE, "target_BAH.wav"), BAH, SR)

# --- the obedience module: command (one-hot 2) -> exact waveform ---
torch.manual_seed(0)
X = torch.eye(2)                                  # command 0 = AH, 1 = BAH
Y = torch.tensor(np.stack([AH, BAH]), dtype=torch.float32)
model = nn.Sequential(nn.Linear(2, 512), nn.GELU(), nn.Linear(512, 1024), nn.GELU(), nn.Linear(1024, N))
opt = torch.optim.Adam(model.parameters(), lr=1e-3)
loss = None
for step in range(4000):
    pred = model(X)
    loss = ((pred - Y) ** 2).mean()
    opt.zero_grad(); loss.backward(); opt.step()
    if step % 500 == 0:
        print(f"step {step:4d}  err {loss.item():.6f}", flush=True)
print(f"FINAL obedience error: {loss.item():.8f}  ({'PERFECT' if loss.item() < 1e-4 else 'still learning'})", flush=True)

# --- OBEY: on command, produce the exact syllable ---
model.eval()
with torch.no_grad():
    ah_out = model(torch.tensor([[1., 0.]]))[0].numpy()
    bah_out = model(torch.tensor([[0., 1.]]))[0].numpy()
sf.write(os.path.join(HERE, "eran_obey_AH.wav"), np.clip(ah_out, -1, 1), SR)
sf.write(os.path.join(HERE, "eran_obey_BAH.wav"), np.clip(bah_out, -1, 1), SR)
torch.save(model.state_dict(), os.path.join(HERE, "obedience_layer.pt"))
# fidelity of obedience (how exactly he reproduces the command)
ah_err = float(np.mean((ah_out - AH) ** 2)); bah_err = float(np.mean((bah_out - BAH) ** 2))
print(f"OBEY AH err {ah_err:.8f} | OBEY BAH err {bah_err:.8f}", flush=True)
print("saved: eran_obey_AH.wav, eran_obey_BAH.wav, obedience_layer.pt", flush=True)
