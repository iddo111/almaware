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


# Known Whisper "silence hallucinations" — phrases the model invents on
# silence / noise / non-speech because they're over-represented in its YouTube
# training data (subtitle credits, channel sign-offs, subtitler watermarks).
# Matching is done case-insensitively on a whitespace-normalised copy of the
# text, so list canonical forms here. Multilingual on purpose: the bug shows up
# as Arabic / Russian / Japanese / Portuguese / English garbage.
_HALLUCINATION_BLOCKLIST = [
    # --- Arabic (the #1 reported one: "subscribe to the channel") ---
    "اشتركوا في القناة", "اشتراك في القناة", "لا تنسوا الاشتراك",
    "شكرا للمشاهدة", "شكرا على المشاهدة", "ترجمة",
    # --- English subtitle/credit junk ---
    "subscribe", "please subscribe", "thanks for watching",
    "thank you for watching", "thank you for your watching",
    "thank you", "thank you very much", "see you next time",
    "like and subscribe", "don't forget to subscribe",
    "subtitles by", "subtitles by the amara.org community", "amara.org",
    "transcription", "transcription by", "captions by", "closed captions",
    "www.", ".com", "http",
    # --- CJK ---
    "請訂閱", "請訂閱我的頻道", "字幕", "字幕由", "字幕志愿者", "中文字幕",
    "ご視聴ありがとうございました", "ご視聴ありがとうございます",
    "チャンネル登録", "ご清聴ありがとうございました", "おやすみなさい",
    # --- Russian ---
    "продолжение следует", "субтитры", "субтитры сделал",
    "спасибо за просмотр", "подписывайтесь на канал",
    # --- Portuguese / Spanish ---
    "obrigado por assistir", "inscreva-se no canal", "legendas pela comunidade",
    "gracias por ver el video", "suscríbete al canal",
    # --- Hebrew (silence / near-silence hallucinations Whisper emits on this mic) ---
    "תודה", "תודה רבה", "תודה על הצפייה", "תודה שצפיתם", "תודה רבה לכם",
    "כתוביות", "עריכת כתוביות", "כתוביות בעברית", "תרגום וכתוביות",
    "הקליקו על כפתור המנוי", "אל תשכחו להירשם לערוץ", "בהצלחה",
    # --- branding watermarks Whisper emits ---
    "mbc", "ndtv", "translated by", "translation by",
]
_BLOCKLIST_NORM = [re.sub(r"\s+", " ", p).strip().lower() for p in _HALLUCINATION_BLOCKLIST]


def _is_blocklisted(text: str) -> bool:
    """True if the (whole, stripped) text is a known hallucination phrase, or is
    dominated by one. We match the FULL normalised text against the blocklist and
    also catch the case where the segment is just a blocklist phrase plus
    punctuation/emoji — the typical 'subscribe!' / 'תודה רבה.' silence output."""
    norm = re.sub(r"\s+", " ", (text or "")).strip().lower()
    if not norm:
        return False
    # strip surrounding punctuation/symbols for the equality test
    bare = re.sub(r"^[^\w֐-׿؀-ۿ]+|[^\w֐-׿؀-ۿ]+$", "", norm)
    for p in _BLOCKLIST_NORM:
        if bare == p or norm == p:
            return True
        # short segment that is essentially just the phrase (+ a few chars)
        if p in norm and len(norm) <= len(p) + 4:
            return True
    return False


def _is_repetitive(text: str) -> bool:
    """Loop / repeated-phrase detection — the 'ма ма ма' / 'amma amma' spirals and
    repeated-word hallucinations that survive the compression-ratio threshold."""
    norm = re.sub(r"\s+", " ", (text or "")).strip()
    if not norm:
        return False
    toks = norm.split()
    # same word repeated >=3x dominating the output
    if len(toks) >= 3:
        from collections import Counter
        top, cnt = Counter(toks).most_common(1)[0]
        if cnt >= 3 and cnt >= 0.6 * len(toks):
            return True
    # the WHOLE string is one short fragment repeated back-to-back (no spaces)
    t = re.sub(r"\s+", "", norm)
    for unit in (2, 3, 4):
        if len(t) >= unit * 4 and len(set(t[i:i + unit] for i in range(0, len(t) - unit, unit))) <= 2:
            seg = t[:unit]
            if seg * (len(t) // unit) == t[: unit * (len(t) // unit)]:
                return True
    return False


def _is_hallucinated(text: str) -> bool:
    """Decide whether a transcript is a Whisper-on-silence hallucination and
    should be DROPPED. Catches:
      (a) known multilingual blocklist phrases (subscribe / شكرا / 字幕 / …),
      (b) long single-char or low-variety runs ('אההההה…'),
      (c) repeated-token / repeated-fragment loops ('ма ма ма'),
      (d) ultra-short 1-2 char junk.
    Real Hebrew/English speech sails through untouched."""
    raw = (text or "").strip()
    if not raw:
        return False
    t = re.sub(r"\s+", "", raw)
    # (d) ultra-short junk: 1–2 chars and not a real one/two-letter word
    if len(t) <= 2 and not re.search(r"[A-Za-z֐-׿]{2}", raw):
        return True
    # (a) known hallucination phrases
    if _is_blocklisted(raw):
        return True
    # (b) char-run / low-variety garbage
    if len(t) >= 6:
        longest = max((len(m.group(0)) for m in re.finditer(r"(.)\1+", t)), default=0)
        if longest >= 8:                       # 8+ of the SAME char in a row
            return True
        if len(t) >= 12 and len(set(t)) <= 3:  # long string, almost no variety
            return True
    # (c) repetition loops
    if _is_repetitive(raw):
        return True
    return False


def _rms(audio) -> float:
    a = np.asarray(audio, dtype=np.float32)
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(a * a)) + 1e-12)


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

    def _decode_confidence(self, audio, lang) -> float:
        """Decode the clip under a FORCED language and return a length-weighted
        avg log-prob (higher = the model is more 'at home' in this language).
        Used as a tie-breaker when the cheap detector is unsure."""
        try:
            segs, _ = self._model.transcribe(
                audio, language=lang, beam_size=5, temperature=0.0,
                condition_on_previous_text=False, vad_filter=False)
            segs = list(segs)
        except Exception:
            return -9.0
        if not segs:
            return -9.0
        dur = sum((s.end - s.start) for s in segs) or 1.0
        return sum(s.avg_logprob * (s.end - s.start) for s in segs) / dur

    def _auto_language(self, audio):
        """First-pass language ID for the 'auto' case. Returns (language, prob, all_probs).

        Strategy (measured on Iddo's own he/en/mixed corpus):
          1) detect_language() votes over `auto_detect_langs` segments (more robust
             than Whisper's default first-second-only guess).
          2) With `lang_lock` ON (the default), the result is CONSTRAINED to the
             whitelist (he/en). This is the anti-hallucination fix: on silent/noisy
             audio Whisper's language detector drifts to Arabic/Russian/Japanese and
             then invents text in that language. Locking detection to he+en stops the
             cross-language garbage at the source. We pick whichever whitelist
             language the model is genuinely more confident in (re-decode tie-break,
             which is also what makes short Hebrew accurate).
          3) With `lang_lock` OFF, a CONFIDENT guess (>= lang_confidence) is trusted
             as-is so other languages keep working; only an UNSURE guess falls back
             to the whitelist re-decode router.
        """
        try:
            lang, prob, all_probs = self._model.detect_language(
                audio,
                language_detection_segments=max(1, int(self.cfg.auto_detect_langs)),
                language_detection_threshold=float(self.cfg.lang_confidence),
            )
        except Exception:
            # Detection FAILED. Returning None here used to hand Whisper a free
            # choice of every language it knows - which is exactly how noise came
            # back as Icelandic and Arabic while lang_lock was ON. A failed
            # detection must fall back INSIDE the whitelist, never outside it.
            wl0 = [l for l in (self.cfg.lang_whitelist or []) if l]
            if bool(getattr(self.cfg, "lang_lock", True)) and wl0:
                return wl0[0], 0.0, {}
            return None, 0.0, {}
        probs = dict(all_probs or [])
        wl = [l for l in (self.cfg.lang_whitelist or []) if l]
        thr = float(self.cfg.lang_confidence)
        lock = bool(getattr(self.cfg, "lang_lock", True))

        # no usable whitelist → nothing to constrain to, trust the detector
        if len(wl) < 2:
            return lang, prob, probs

        # LOCKED: never leave the whitelist. If the detector already chose a
        # whitelist language confidently, keep it; otherwise re-decode among the
        # whitelist and pick the model's most-confident one. The detector's
        # off-whitelist pick (ar/ru/ja/…) is discarded — that's the bug fix.
        if lock:
            if lang in wl and prob >= thr:
                return lang, prob, probs
            scored = [(self._decode_confidence(audio, l), l) for l in wl]
            _, best_lang = max(scored)
            return best_lang, max(prob, probs.get(best_lang, 0.0)), probs

        # UNLOCKED (legacy): confident → trust the detector even off-whitelist
        if prob >= thr:
            return lang, prob, probs
        # unsure → re-decode router among whitelist
        scored = [(self._decode_confidence(audio, l), l) for l in wl]
        _, best_lang = max(scored)
        return best_lang, max(prob, probs.get(best_lang, 0.0)), probs

    def transcribe(self, audio: np.ndarray, return_info: bool = False):
        """audio = mono float32 @16k. Returns (text, detected_language), or
        (text, language, info_dict) when return_info=True (for the test harness)."""
        if self._model is None:
            raise RuntimeError("STT model not loaded")
        audio = np.ascontiguousarray(np.asarray(audio, dtype=np.float32))
        task = "translate" if self.cfg.translate_to_english else "transcribe"
        auto = self.cfg.language == "auto"

        # ENERGY GATE (fix #2): if the whole clip is below the speech RMS floor it's
        # silence/noise — never even hand it to the model (where it would hallucinate).
        seg_rms = _rms(audio)
        gate = float(getattr(self.cfg, "speech_rms_gate", 0.0) or 0.0)
        if gate > 0.0 and seg_rms < gate:
            empty = "", (self.cfg.language if not auto else None)
            return (empty[0], empty[1], {"language_probability": 0.0,
                                         "all_language_probs": {}, "multilingual": False,
                                         "gated": True, "dropped": "rms_gate",
                                         "rms": seg_rms}) if return_info else empty

        det_lang, det_prob, all_probs = (None, 0.0, {})
        if auto:
            det_lang, det_prob, all_probs = self._auto_language(audio)
            language = det_lang            # may be None if detection failed
        else:
            language = self.cfg.language

        # Code-switching: when auto + enabled, let Whisper re-detect the language of
        # EACH segment during decode (he<->en within one breath). We still pass the
        # first-pass `language` as the starting prior. With a forced language we keep
        # multilingual off so the user's choice is honoured everywhere. With the
        # language LOCK on, per-segment re-detect can still drift off-whitelist, so we
        # only enable it when the user has explicitly turned the lock off.
        lock = bool(getattr(self.cfg, "lang_lock", True))
        multilingual = bool(auto and self.cfg.code_switch and not lock)

        # Belt and braces: whatever happened above, a LOCKED decode must never be
        # handed language=None or an off-whitelist language. language=None means
        # "Whisper, pick anything" - the single line that let noise come back as
        # Icelandic. Clamp it here so no future path can reopen the hole.
        if lock:
            _wl = [l for l in (self.cfg.lang_whitelist or []) if l]
            if _wl and (language is None or language not in _wl):
                language = _wl[0]

        # Decode guards (fix #3) — tunable from config, with the anti-hallucination
        # defaults baked in. temperature=0.0 (greedy) plus a fallback ladder; the
        # standard thresholds drop degenerate / no-speech / repetitive decodes.
        no_speech_thr = float(getattr(self.cfg, "no_speech_threshold", 0.6))
        logprob_thr = float(getattr(self.cfg, "log_prob_threshold", -1.0))
        compress_thr = float(getattr(self.cfg, "compression_ratio_threshold", 2.4))

        # Quality-first decode: Silero VAD strips non-speech inside the segment
        # (kills most hallucinations at the source); beam search + temperature
        # fallback + the standard thresholds drop degenerate / no-speech decodes.
        kw = dict(
            language=language, task=task, multilingual=multilingual, beam_size=5,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            compression_ratio_threshold=compress_thr,  # repetitive junk → high ratio → rejected
            log_prob_threshold=logprob_thr,
            no_speech_threshold=no_speech_thr,
            condition_on_previous_text=False,   # each utterance independent → no drift
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=int(getattr(self.cfg, "vad_min_silence_ms", 500)),
                speech_pad_ms=int(getattr(self.cfg, "vad_speech_pad_ms", 100)),
                threshold=float(getattr(self.cfg, "vad_threshold", 0.5)),
            ),
        )
        try:
            segments, info = self._model.transcribe(audio, **kw)
            seglist = list(segments)
            text = "".join(s.text for s in seglist).strip()
        except Exception:
            # if the bundled Silero VAD isn't available, retry once without it
            kw.pop("vad_filter", None); kw.pop("vad_parameters", None)
            segments, info = self._model.transcribe(audio, **kw)
            seglist = list(segments)
            text = "".join(s.text for s in seglist).strip()

        # report the language: prefer our first-pass detection (it voted over more
        # audio); fall back to whatever the decoder settled on.
        lang = det_lang or getattr(info, "language", None)
        if det_prob <= 0.0:
            det_prob = float(getattr(info, "language_probability", 0.0) or 0.0)

        # avg log-prob across the produced segments (length-weighted). A very low
        # value means the model wasn't "at home" — typical of a forced hallucination.
        avg_lp = 0.0
        if seglist:
            dur = sum((s.end - s.start) for s in seglist) or 1.0
            avg_lp = sum(getattr(s, "avg_logprob", 0.0) * (s.end - s.start) for s in seglist) / dur

        dropped = ""
        # confidence drop (fix #3): low avg-logprob decode → treat as hallucination
        lp_floor = float(getattr(self.cfg, "log_prob_threshold", -1.0))
        if text and avg_lp < lp_floor:
            dropped, text = "low_logprob", ""
        # strengthened multilingual / repetition / char-run filter (fix #4)
        if text and _is_hallucinated(text):
            dropped, text = "filter", ""
        # whitelist enforcement (fix #5): in auto+lock mode, a transcript whose
        # detected language is off-whitelist is cross-language garbage → drop it.
        if text and auto and bool(getattr(self.cfg, "lang_lock", True)):
            wl = [l for l in (self.cfg.lang_whitelist or []) if l]
            if wl and lang and lang not in wl:
                dropped, text = "off_whitelist", ""

        if return_info:
            return text, lang, {"language_probability": det_prob,
                                "all_language_probs": all_probs,
                                "multilingual": multilingual,
                                "avg_logprob": avg_lp, "rms": seg_rms,
                                "dropped": dropped}
        return text, lang
