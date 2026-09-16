import sys, numpy as np, sounddevice as sd

DUR = 1.2
SR = 16000
print("Probing live RMS of every input device (speak now / tap headset)...\n")
devs = sd.query_devices()
results = []
for i, d in enumerate(devs):
    if d.get("max_input_channels", 0) < 1:
        continue
    name = d["name"]
    try:
        rec = sd.rec(int(DUR * SR), samplerate=SR, channels=1, dtype="float32", device=i)
        sd.wait()
        a = rec.flatten()
        rms = float(np.sqrt(np.mean(a**2)) * 1000)   # scaled like the app
        peak = float(np.max(np.abs(a)) * 1000)
        results.append((rms, peak, i, name))
        flag = "  <<< LIVE" if rms > 30 else ""
        print(f"  [{i:2d}] RMS={rms:7.1f} PEAK={peak:7.1f}  {name}{flag}")
    except Exception as e:
        print(f"  [{i:2d}] ERR {str(e)[:60]}  {name}")

print("\n--- verdict ---")
results.sort(reverse=True)
if results and results[0][0] > 30:
    r = results[0]
    print(f"LIVE device: [{r[2]}] {r[3]}  (RMS={r[0]:.1f})")
else:
    print("NO device above RMS 30 — everything is silent right now (no speech / headset off/muted).")
