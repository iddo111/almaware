import sys
from huggingface_hub import snapshot_download
for r in ["facebook/mms-tts-heb",
          "facebook/wav2vec2-xlsr-53-espeak-cv-ft",
          "ivrit-ai/whisper-large-v3-turbo"]:
    try:
        p = snapshot_download(r, ignore_patterns=["*.msgpack","*.h5","*.onnx","*.tflite"])
        print("OK", r, p, flush=True)
    except Exception as e:
        print("FAIL", r, type(e).__name__, str(e)[:200], flush=True)
