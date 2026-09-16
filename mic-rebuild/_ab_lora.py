"""_ab_lora.py -- the mic mangles Hebrew and passes English through clean.
scar-29 routes ENGLISH to the stock model and HEBREW to the LoRA, always, so
the LoRA is the only thing in the Hebrew path that is not in the English path.

Decode the same audio with both and print them side by side. One model is
loaded at a time and freed before the next, so this never holds two extra
copies alongside the live server.
"""
import sys, time, glob, gc
from pathlib import Path
from faster_whisper import WhisperModel

STOCK = "D:/CLAUDE/mic-rebuild/models/large-v3-turbo-ct2"
LORA = "D:/CLAUDE/mic-rebuild/models/iddo-lora-run2-ct2"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 8

PAT = sys.argv[2] if len(sys.argv) > 2 else "D:/CLAUDE/mic-rebuild/_langtest/*.wav"
wavs = sorted(glob.glob(PAT))[-N:]
if not wavs:
    print("no wavs"); sys.exit(1)
print("clips: %d" % len(wavs), flush=True)


def dec(m, w):
    segs, info = m.transcribe(w, language="he", vad_filter=False, beam_size=5)
    return "".join(x.text for x in segs).strip()


def run(path, tag):
    print("loading %s ..." % tag, flush=True)
    t = time.time()
    m = WhisperModel(path, device="cuda", compute_type="int8_float16")
    print("  loaded in %.1fs" % (time.time() - t), flush=True)
    out = {}
    for w in wavs:
        out[Path(w).name] = dec(m, w)
    del m
    gc.collect()
    return out


A = run(STOCK, "STOCK")
B = run(LORA, "LORA")
agree = 0
for k in A:
    same = A[k] == B[k]
    agree += same
    print("\n--- %s %s" % (k, "(identical)" if same else ""))
    print("  STOCK: %s" % A[k][:170])
    print("  LORA : %s" % B[k][:170])
print("\n===== %d/%d identical =====" % (agree, len(A)))
