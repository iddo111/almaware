import sounddevice as sd
import numpy as np

# Test the default-input proxies that support blocking I/O.
# If the headset is the Windows default input, these route to it.
for idx, label in [(0, "MME Sound Mapper"), (7, "DirectSound Primary"), (None, "sd default")]:
    try:
        with sd.InputStream(samplerate=16000, channels=1, dtype="int16", device=idx) as st:
            block, _ = st.read(int(16000 * 1.5))
            rms = int(np.sqrt(np.mean(block.astype(np.float64) ** 2)))
            peak = int(np.abs(block).max())
        verdict = "LIVE" if peak >= 15 else "quiet"
        print("  device=%-5s %-22s OPENS-OK  rms=%d peak=%d  -> %s" % (str(idx), label, rms, peak, verdict))
    except Exception as e:
        print("  device=%-5s %-22s FAIL: %s" % (str(idx), label, str(e)[:70]))

print("\ndefault input device:", sd.default.device)
print("query default:", sd.query_devices(kind="input")["name"])
