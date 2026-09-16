import os, sys, time, wave, numpy as np
PY=os.path.dirname(sys.executable)
for sub in ("cublas","cudnn","cuda_runtime","cuda_nvrtc"):
    p=os.path.join(PY,"Lib","site-packages","nvidia",sub,"bin")
    if os.path.isdir(p): os.add_dll_directory(p)
from faster_whisper import WhisperModel
t0=time.time()
m=WhisperModel("ivrit-ai/whisper-large-v3-turbo-ct2", device="cuda", compute_type="int8_float16")
print("load_s", round(time.time()-t0,1), flush=True)
import subprocess
free=subprocess.run(["nvidia-smi","--query-gpu=memory.free","--format=csv,noheader"],capture_output=True,text=True).stdout.strip()
print("free_after_load", free, flush=True)
wav=sys.argv[1]
with wave.open(wav) as w:
    a=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768.0
    print("dur_s", round(w.getnframes()/w.getframerate(),2), "sr", w.getframerate())
t0=time.time()
segs,info=m.transcribe(a, language="he", beam_size=5, condition_on_previous_text=False, without_timestamps=True, temperature=[0.0,0.2])
txt=" ".join(s.text.strip() for s in segs)
print("decode_s", round(time.time()-t0,2))
print("TEXT:", txt)
free=subprocess.run(["nvidia-smi","--query-gpu=memory.free","--format=csv,noheader"],capture_output=True,text=True).stdout.strip()
print("free_after_decode", free)
