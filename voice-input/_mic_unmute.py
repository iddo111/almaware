# _mic_unmute.py — unmute + max ALL active capture (mic) endpoints, then re-measure level.
import sys, traceback
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

print("== unmute + max all active microphone endpoints ==", flush=True)
try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL, CoCreateInstance, CLSCTX_INPROC_SERVER
    from pycaw.pycaw import IAudioEndpointVolume, IMMDeviceEnumerator
    from pycaw.constants import CLSID_MMDeviceEnumerator
    enum = CoCreateInstance(CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, CLSCTX_INPROC_SERVER)
    EDATAFLOW_CAPTURE = 1
    STATE_ACTIVE = 1
    coll = enum.EnumAudioEndpoints(EDATAFLOW_CAPTURE, STATE_ACTIVE)
    n = coll.GetCount()
    print(f"  active capture endpoints: {n}", flush=True)
    for i in range(n):
        try:
            dev = coll.Item(i)
            iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(iface, POINTER(IAudioEndpointVolume))
            bm = vol.GetMute(); bv = vol.GetMasterVolumeLevelScalar()
            vol.SetMute(0, None)
            vol.SetMasterVolumeLevelScalar(1.0, None)
            print(f"  ep{i}: mute {bm} -> 0   level {bv:.2f} -> 1.00", flush=True)
        except Exception as e:
            print(f"  ep{i}: ERROR {e}", flush=True)
except Exception as e:
    print("  pycaw unmute FAILED:", e, flush=True)
    traceback.print_exc()

print("== re-measure level after unmute (3s) ==", flush=True)
try:
    import json, numpy as np, sounddevice as sd
    sys.path.insert(0, r'D:\CLAUDE\voice-input')
    import mic
    cfg = json.load(open(r'D:\CLAUDE\voice-input\config.json', encoding='utf-8'))
    idx, name, note = mic.resolve_device(cfg.get('input_device'), cfg.get('fallback_devices', []),
                                         never_use=cfg.get('never_use_devices'), idle_if_no_good_mic=True)
    rec = sd.rec(int(3*16000), samplerate=16000, channels=1, dtype='float32', device=idx); sd.wait()
    rms = float(np.sqrt(np.mean(rec**2)))
    verdict = "SOUND IS NOW REACHING THE MIC" if rms > 1e-4 else "STILL SILENT -> hardware/privacy issue, not software"
    print(f"  device={name}  RMS={rms:.5f}  -> {verdict}", flush=True)
except Exception as e:
    print("  re-measure error:", e, flush=True)
print("== DONE ==", flush=True)
