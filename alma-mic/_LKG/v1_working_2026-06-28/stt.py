"""alma-mic / stt.py — speech-to-text adapter.

ALMAWARE-pure APP code: our own thin interface. The recognition MODEL itself
(Whisper, Hebrew-finetuned by ivrit-ai, plus OUR Hebrew LoRA) is the model-not-app
category — allowed under the purity law, exactly like Eran.

One clear interface:
    t = Transcriber(cfg); t.load(log); text, lang = t.transcribe(audio_16k_mono_f32)

Honors the user's settings: language ("auto"/he/en), translate-to-English toggle,
device (auto->cuda then cpu), and an optional path to OUR trained LoRA (merged to ct2).
"""
from __future__ import annotations
import os
import re
import numpy as np


def _is_hallucinated(text: str) -> bool:
    """Whisper emits long single-char/few-char runs on non-speech (breath, hum,
    silence) — the 'אההההה…' garbage. Detect that so we can drop it."""
    t = re.sub(r"\s+", "", text or "")
    if len(t) < 6:
        return False
    longest = max((len(m.group(0)) for m in re.finditer(r"(.)\1+", t)), default=0)
    if longest >= 8:                      # 8+ of the SAME char in a row
        return True
    if len(t) >= 12 and len(set(t)) <= 3:  # long string, almost no variety
        return True
    return False


def _enable_cuda_dlls() -> None:
    """Let ctranslate2 find cuBLAS/cuDNN shipped as pip wheels (Windows GPU path).
    No-op if they aren't installed — we then fall back to CPU cleanly."""
    try:
        import nvidia.cublas
        import nvidia.cudnn
        bases = list(nvidia.cublas.__path__) + list(nvidia.cudnn.__path__)
    except Exception:
        return
    for base in bases:
        bin_dir = os.path.join(base, "bin")
        if os.path.isdir(bin_dir):
            try:
                os.add_dll_directory(bin_dir)
            except Exception:
                pass
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


class Transcriber:
    def __init__(self, cfg):
        self.cfg = cfg
        self._model = None
        self.desc = ""

    # which model: our LoRA build if set, else the Hebrew Whisper base
    def _model_id(self) -> str:
        return self.cfg.lora_dir.strip() or self.cfg.model

    def _plan(self):
        ct = self.cfg.compute_type
        dev = self.cfg.device
        if dev == "auto":
            return [("cuda", "float16" if ct == "auto" else ct),
                    ("cpu", "int8" if ct == "auto" else ct)]
        if dev == "cuda":
            return [("cuda", "float16" if ct == "auto" else ct),
                    ("cpu", "int8")]
        return [("cpu", "int8" if ct == "auto" else ct)]

    def load(self, log=print) -> None:
        import numpy as _np
        _enable_cuda_dlls()
        from faster_whisper import WhisperModel  # the MODEL runtime
        model_id = self._model_id()
        threads = max(4, (os.cpu_count() or 8) - 2)
        last = None
        for device, compute in self._plan():
            try:
                log(f"loading {model_id} on {device}/{compute} …")
                m = WhisperModel(model_id, device=device, compute_type=compute,
                                 cpu_threads=threads)
                # VALIDATE the device actually runs an inference (catches a CUDA device
                # that loads but has no cuBLAS/cuDNN DLLs — common on Windows CPU-torch).
                list(m.transcribe(_np.zeros(16000, dtype=_np.float32),
                                  language="he", beam_size=1, temperature=0)[0])
                self._model = m
                self.desc = f"{model_id.split('/')[-1]} [{device}/{compute}]"
                log(f"model ready: {self.desc}")
                return
            except Exception as e:
                last = e
                log(f"  {device}/{compute} unavailable: {type(e).__name__}: {e}")
        raise RuntimeError(f"could not load STT model {model_id}: {last}")

    def transcribe(self, audio: np.ndarray):
        """audio = mono float32 @16k. Returns (text, detected_language)."""
        if self._model is None:
            raise RuntimeError("STT model not loaded")
        audio = np.ascontiguousarray(np.asarray(audio, dtype=np.float32))
        language = None if self.cfg.language == "auto" else self.cfg.language
        task = "translate" if self.cfg.translate_to_english else "transcribe"
        # Quality-first decode: Silero VAD strips non-speech inside the segment
        # (kills most hallucinations at the source); beam search + temperature
        # fallback + the standard thresholds drop degenerate / no-speech decodes.
        kw = dict(
            language=language, task=task, beam_size=5,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            compression_ratio_threshold=2.4,   # repetitive junk → high ratio → rejected
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            condition_on_previous_text=False,   # each utterance independent → no drift
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=120),
        )
        try:
            segments, info = self._model.transcribe(audio, **kw)
            text = "".join(s.text for s in segments).strip()
        except Exception:
            # if the bundled Silero VAD isn't available, retry once without it
            kw.pop("vad_filter", None); kw.pop("vad_parameters", None)
            segments, info = self._model.transcribe(audio, **kw)
            text = "".join(s.text for s in segments).strip()
        if _is_hallucinated(text):
            return "", getattr(info, "language", None)
        return text, getattr(info, "language", None)
