"""Independent verification of corpus-big/open + an LPC formant survey.

Verification does NOT trust the builder: it re-walks the directory, re-hashes,
re-reads wav headers, and re-checks speaker disjointness from the manifest.

The formant survey answers the question that actually matters: does this corpus
contain clean /a/ vowels (F1 650-850 Hz) that Iddo's own 253 s corpus lacks?
"""
import io, json, os, hashlib, wave, random, collections
import numpy as np

OUT = r"D:\CLAUDE\voice-ant-farm\corpus-big\open"
M = json.load(io.open(os.path.join(OUT, "manifest.json"), encoding="utf-8"))
clips = M["clips"]
print(f"manifest clips: {len(clips)}")

# ---------------------------------------------------------------- 1. integrity
on_disk = set()
for sp in ("train", "heldout"):
    for fn in os.listdir(os.path.join(OUT, sp)):
        if fn.endswith(".wav"):
            on_disk.add(f"{sp}/{fn}")
listed = {c["path"] for c in clips}
print(f"wav on disk: {len(on_disk)}  | in manifest: {len(listed)}")
print(f"  on disk not in manifest: {len(on_disk - listed)}")
print(f"  in manifest not on disk: {len(listed - on_disk)}")

rng = random.Random(7007)
sample = rng.sample(clips, 300)
bad_hash, bad_fmt = [], []
for c in sample:
    p = os.path.join(OUT, c["path"].replace("/", os.sep))
    with wave.open(p, "rb") as w:
        if (w.getnchannels(), w.getframerate(), w.getsampwidth()) != (1, 16000, 2):
            bad_fmt.append(c["path"])
        dur = w.getnframes() / 16000.0
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for ch in iter(lambda: fh.read(1 << 20), b""):
            h.update(ch)
    if h.hexdigest() != c["sha256"]:
        bad_hash.append(c["path"])
    if abs(dur - c["duration_s"]) > 0.01:
        bad_fmt.append(c["path"] + " duration-mismatch")
print(f"re-hashed {len(sample)} sampled clips: hash mismatches={len(bad_hash)} format/duration problems={len(bad_fmt)}")

# ------------------------------------------------- 2. duplicate / leak by sha256
by_sha = collections.defaultdict(set)
for c in clips:
    by_sha[c["sha256"]].add(c["split"])
cross = [s for s, sp in by_sha.items() if len(sp) > 1]
dupes = len(clips) - len(by_sha)
print(f"identical audio present in BOTH train and heldout: {len(cross)}")
print(f"duplicate audio anywhere in corpus: {dupes}")

# ------------------------------------------------------ 3. speaker disjointness
tr = {c["speaker_id"] for c in clips if c["split"] == "train"}
ho = {c["speaker_id"] for c in clips if c["split"] == "heldout"}
print(f"train speaker-keys={len(tr)} heldout speaker-keys={len(ho)} INTERSECTION={sorted(tr & ho)}")

lab = collections.Counter(c["speaker_id"] for c in clips if c["speaker_id_known"])
dur = collections.Counter()
for c in clips:
    dur[c["speaker_id"]] += c["duration_s"]
print(f"labelled CV speakers: {len(lab)}")
for sp in ("train", "heldout"):
    ks = sorted({c["speaker_id"] for c in clips if c["split"] == sp and c["speaker_id_known"]},
                key=lambda k: -dur[k])
    print(f"  {sp}: {len(ks)} CV speakers, minutes each: "
          + ", ".join(f"{dur[k]/60:.1f}" for k in ks))

# ----------------------------------------------------------- 4. formant survey
def lpc_formants(x, fs=16000, order=16):
    """Return (F1,F2) per voiced frame via LPC root solving. Pure numpy."""
    x = x - x.mean()
    if x.size < 400:
        return []
    x = np.append(x[0], x[1:] - 0.97 * x[:-1])          # pre-emphasis
    win, hop = 400, 160                                  # 25 ms / 10 ms
    n = 1 + (x.size - win) // hop
    if n <= 0:
        return []
    frames = np.lib.stride_tricks.as_strided(
        x, shape=(n, win), strides=(x.strides[0] * hop, x.strides[0])).copy()
    frames *= np.hamming(win)
    energy = (frames ** 2).sum(1)
    if energy.max() <= 0:
        return []
    keep = energy > np.percentile(energy[energy > 0], 70)  # loud -> likely vowel
    out = []
    for fr in frames[keep]:
        r = np.correlate(fr, fr, "full")[win - 1:win - 1 + order + 1]
        if r[0] <= 0:
            continue
        # Levinson-Durbin
        a = np.zeros(order + 1); a[0] = 1.0; e = r[0]
        ok = True
        for i in range(1, order + 1):
            acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1]) if i > 1 else r[1]
            k = -acc / e
            if not np.isfinite(k) or abs(k) >= 1:
                ok = False; break
            a[1:i + 1] = a[1:i + 1] + k * a[i - 1::-1][:i]
            e *= (1 - k * k)
            if e <= 0:
                ok = False; break
        if not ok:
            continue
        try:
            rts = np.roots(a)
        except Exception:
            continue
        rts = rts[np.imag(rts) > 1e-6]
        if rts.size == 0:
            continue
        f = np.angle(rts) * fs / (2 * np.pi)
        bw = -0.5 * (fs / (2 * np.pi)) * np.log(np.abs(rts) + 1e-12)
        sel = (f > 90) & (f < 5000) & (bw < 400)
        f = np.sort(f[sel])
        if f.size >= 2:
            out.append((f[0], f[1]))
    return out


def survey(paths, label, cap_frames=60):
    F = []
    for p in paths:
        with wave.open(p, "rb") as w:
            raw = w.readframes(w.getnframes())
        x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
        fr = lpc_formants(x)
        F.extend(fr[:cap_frames])
    if not F:
        print(f"{label}: no frames"); return
    F = np.array(F)
    f1, f2 = F[:, 0], F[:, 1]
    # Hebrew /a/: F1 650-850, F2 roughly 1100-1600
    a_like = ((f1 >= 650) & (f1 <= 850) & (f2 >= 1100) & (f2 <= 1600)).mean()
    f1_hi = (f1 >= 650).mean()
    print(f"{label:26s} frames={len(F):6d} "
          f"F1 med={np.median(f1):6.0f} p90={np.percentile(f1,90):6.0f} | "
          f"F2 med={np.median(f2):6.0f} | "
          f"F1>=650: {f1_hi*100:5.1f}%  /a/-box: {a_like*100:5.1f}%")


print("\n--- LPC formant survey (open corpus vs Iddo's own recordings) ---")
rng2 = random.Random(7019)
for sp in ("train", "heldout"):
    for ds in ("fleurs_he_il", "cv17_he"):
        ps = [os.path.join(OUT, c["path"].replace("/", os.sep))
              for c in clips if c["split"] == sp and c["dataset"] == ds]
        if not ps:
            continue
        survey(rng2.sample(ps, min(120, len(ps))), f"{ds} [{sp}]")

OLD = r"D:\CLAUDE\voice-ant-farm\recordings"
old = []
for root, _, fs in os.walk(OLD):
    for fn in fs:
        if fn.endswith(".wav"):
            old.append(os.path.join(root, fn))
if old:
    survey(old, "IDDO recordings (all 24)")
