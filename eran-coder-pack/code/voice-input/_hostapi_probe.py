import sounddevice as sd
import numpy as np

ha = sd.query_hostapis()
print("HOST APIs:")
for i, h in enumerate(ha):
    print("  [%d] %s" % (i, h["name"]))

print("\nINPUT DEVICES (idx | hostapi | maxIn | name):")
headset_idx = []
for i, d in enumerate(sd.query_devices()):
    if d["max_input_channels"] > 0:
        hn = ha[d["hostapi"]]["name"]
        nm = d["name"]
        is_hs = ("1000xm4" in nm.lower()) or ("hands-free" in nm.lower()) or ("headset" in nm.lower())
        mark = "  <== HEADSET" if is_hs else ""
        print("  [%2d] %-24s ch=%d  %s%s" % (i, hn, d["max_input_channels"], nm[:50], mark))
        if is_hs:
            headset_idx.append((i, hn))

print("\nBLOCKING InputStream test on each headset instance (1.2s):")
for i, hn in headset_idx:
    try:
        with sd.InputStream(samplerate=16000, channels=1, dtype="int16", device=i) as st:
            block, _ = st.read(int(16000 * 1.2))
            rms = int(np.sqrt(np.mean(block.astype(np.float64) ** 2)))
            peak = int(np.abs(block).max())
        print("  [%2d] %-24s OPENS-OK  rms=%d peak=%d" % (i, hn, rms, peak))
    except Exception as e:
        print("  [%2d] %-24s FAIL: %s" % (i, hn, str(e)[:70]))
