# _mic_diag.py — controlled, exit-when-done diagnostic of the dictation pipeline.
# Exercises each stage and PRINTS results. No keyboard hooks, no typing loop.
import json, sys, time, traceback
sys.path.insert(0, r'D:\CLAUDE\voice-input')
import numpy as np

cfg = json.load(open(r'D:\CLAUDE\voice-input\config.json', encoding='utf-8'))
def line(): print("-"*60, flush=True)

print("### MIC PIPELINE DIAGNOSTIC ###", flush=True)

# 1) sounddevice input devices
line(); print("[1] sounddevice INPUT devices:", flush=True)
idx = None
try:
    import sounddevice as sd
    for i, d in enumerate(sd.query_devices()):
        if d.get('max_input_channels', 0) > 0:
            print(f"    [{i}] {d['name']}  (in={d['max_input_channels']}, sr={int(d['default_samplerate'])})", flush=True)
except Exception as e:
    print("    sounddevice ERROR:", e, flush=True); traceback.print_exc()

# 2) which device does the app's resolver pick?
line(); print("[2] mic.resolve_device(...) ->", flush=True)
try:
    import mic
    idx, name, note = mic.resolve_device(cfg.get('input_device'), cfg.get('fallback_devices', []),
                                          never_use=cfg.get('never_use_devices'),
                                          idle_if_no_good_mic=cfg.get('idle_if_no_good_mic', True))
    print(f"    resolved: idx={idx}  name={name!r}", flush=True)
    print(f"    note: {note!r}", flush=True)
    if idx is None:
        print("    >>> RESOLVER RETURNED NO DEVICE -> the app goes IDLE (this would be the bug)", flush=True)
except Exception as e:
    print("    resolve_device ERROR:", e, flush=True); traceback.print_exc()

# 3) actually capture 3s and measure level (is the mic giving signal?)
line(); print("[3] record 3s from resolved device + level:", flush=True)
rec = None
try:
    import sounddevice as sd
    sr = 16000
    dev = idx if idx is not None else None
    rec = sd.rec(int(3*sr), samplerate=sr, channels=1, dtype='float32', device=dev)
    sd.wait()
    rms = float(np.sqrt(np.mean(rec**2))); peak = float(np.max(np.abs(rec)))
    print(f"    captured 3s on device={dev}  RMS={rms:.5f}  peak={peak:.5f}", flush=True)
    print("    >>> RMS≈0 means NO audio is reaching the app (wrong/dead device)" if rms < 1e-4
          else "    >>> mic IS capturing audio", flush=True)
except Exception as e:
    print("    record ERROR:", e, flush=True); traceback.print_exc()

# 4) load whisper on cuda + transcribe the 3s
line(); print("[4] load whisper model on CUDA + transcribe:", flush=True)
try:
    from faster_whisper import WhisperModel
    t = time.time()
    try:
        m = WhisperModel(cfg['model'], device='cuda', compute_type='float16')
    except Exception as e1:
        print("    float16 load failed, retrying int8_float16:", e1, flush=True)
        m = WhisperModel(cfg['model'], device='cuda', compute_type='int8_float16')
    print(f"    model '{cfg['model']}' loaded in {time.time()-t:.1f}s", flush=True)
    if rec is not None:
        segs, info = m.transcribe(rec[:,0], language=None, vad_filter=False)
        txt = ' '.join(s.text for s in segs).strip()
        print(f"    transcribe -> lang={info.language} prob={info.language_probability:.2f} text={txt!r}", flush=True)
except Exception as e:
    print("    model/transcribe ERROR:", e, flush=True); traceback.print_exc()

line(); print("### DONE ###", flush=True)
