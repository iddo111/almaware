"""Per-dataset hours, and ABSOLUTE /a/-token estimates (open corpus vs Iddo's)."""
import io, json, os, wave, random, collections
import numpy as np
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_open_corpus import lpc_formants   # reuse the same LPC code

OUT = r"D:\CLAUDE\voice-ant-farm\corpus-big\open"
M = json.load(io.open(os.path.join(OUT, "manifest.json"), encoding="utf-8"))
clips = M["clips"]

print("=== per-dataset / per-split hours ===")
agg = collections.defaultdict(lambda: [0, 0.0])
for c in clips:
    a = agg[(c["split"], c["dataset"])]
    a[0] += 1; a[1] += c["duration_s"]
for k in sorted(agg):
    n, d = agg[k]
    print(f"  {k[0]:8s} {k[1]:14s} clips={n:5d} hours={d/3600:6.3f}")
tot = sum(v[1] for v in agg.values())
print(f"  TOTAL hours={tot/3600:.3f}")


def rate(paths, label, total_seconds):
    """Uncapped /a/-frame rate on a sample, scaled to the whole set."""
    voiced = 0; alike = 0; secs = 0.0
    for p in paths:
        with wave.open(p, "rb") as w:
            raw = w.readframes(w.getnframes()); secs += w.getnframes() / 16000
        x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
        for f1, f2 in lpc_formants(x):
            voiced += 1
            if 650 <= f1 <= 850 and 1100 <= f2 <= 1600:
                alike += 1
    if secs == 0:
        return
    per_sec = alike / secs
    print(f"  {label:28s} sampled {secs/60:6.1f} min -> {alike:6d} /a/-frames "
          f"({per_sec:5.2f}/s)  ==> whole set ~{int(per_sec*total_seconds):7d} /a/-frames "
          f"(~{per_sec*total_seconds/100:.0f} s of /a/)")


print("\n=== absolute /a/ availability (F1 650-850, F2 1100-1600) ===")
rng = random.Random(7039)
for ds in ("fleurs_he_il", "cv17_he"):
    ps = [os.path.join(OUT, c["path"].replace("/", os.sep))
          for c in clips if c["dataset"] == ds]
    secs = sum(c["duration_s"] for c in clips if c["dataset"] == ds)
    rate(rng.sample(ps, min(250, len(ps))), ds, secs)

allp = [os.path.join(OUT, c["path"].replace("/", os.sep)) for c in clips]
rate(rng.sample(allp, 400), "OPEN CORPUS (combined)", tot)

OLD = r"D:\CLAUDE\voice-ant-farm\recordings"
old = [os.path.join(r, f) for r, _, fs in os.walk(OLD) for f in fs if f.endswith(".wav")]
osec = 0.0
for p in old:
    with wave.open(p, "rb") as w:
        osec += w.getnframes() / w.getframerate()
print(f"\n  (Iddo corpus = {len(old)} wavs, {osec:.0f} s total)")
rate(old, "IDDO recordings", osec)
