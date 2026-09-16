"""learner.py — voice profile + adaptive LoRA fine-tuning for the Hebrew mic app.

Manages per-user WAV sample collections, correction logs, and LoRA fine-tuning
of openai/whisper-large-v3 via the peft library. Trained adapters are exported
to CTranslate2 format so voice_input.py can load them in place of the stock model.

"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("voiceinput.learner")

# ── paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent.resolve()
_PROFILES_DIR = _HERE / "profiles"

# training thresholds
MIN_SAMPLES_FOR_TRAIN = 10
AUTO_TRAIN_CORRECTIONS = 20

# LoRA hyperparameters
LORA_R = 8
LORA_ALPHA = 16
LORA_TARGET_MODULES = ["q_proj", "v_proj"]
BASE_WHISPER_MODEL = "openai/whisper-large-v3"
TRAIN_EPOCHS = 3
TRAIN_BATCH = 2
TRAIN_LR = 1e-4

# ─────────────────────────────────────────────────────────────────────────────
# VoiceProfile
# ─────────────────────────────────────────────────────────────────────────────

class VoiceProfile:
    """Per-user voice profile: sample storage, correction log, training trigger."""

    def __init__(self, username: str | None = None, profiles_dir: str | None = None):
        if username is None:
            username = (
                os.getenv("USERNAME")
                or os.getenv("USER")
                or "default"
            )
        self.username = username
        base = Path(profiles_dir) if profiles_dir else _PROFILES_DIR
        self._profile_dir = base / username
        self._samples_dir = self._profile_dir / "samples"
        self._samples_jsonl = self._profile_dir / "samples.jsonl"
        self._corrections_jsonl = self._profile_dir / "corrections.jsonl"
        self._adapter_dir = self._profile_dir / "adapter"
        self._ct2_dir = self._profile_dir / "ct2_model"
        self._training_log = self._profile_dir / "training.log"
        self._ready_marker = self._adapter_dir / "READY"
        # ensure directories exist
        self._samples_dir.mkdir(parents=True, exist_ok=True)
        self._adapter_dir.mkdir(parents=True, exist_ok=True)

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def profile_dir(self) -> str:
        return str(self._profile_dir)

    # ── sample logging ────────────────────────────────────────────────────────

    def log_sample(self, wav_path: str, transcription: str, confidence: float = 1.0):
        """Copy WAV to profiles/<user>/samples/ and append metadata to samples.jsonl."""
        src = Path(wav_path)
        if not src.exists():
            logger.warning("log_sample: wav not found: %s", wav_path)
            return
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        dest = self._samples_dir / f"{ts}_{src.name}"
        shutil.copy2(src, dest)
        record = {
            "wav": str(dest),
            "text": transcription,
            "confidence": round(float(confidence), 4),
            "ts": ts,
        }
        with open(self._samples_jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.debug("logged sample: %s -> %s", src.name, dest.name)

    # ── correction logging ────────────────────────────────────────────────────

    def log_correction(self, original: str, corrected: str):
        """Log a user correction. Triggers async training when >= AUTO_TRAIN_CORRECTIONS."""
        record = {
            "original": original,
            "corrected": corrected,
            "ts": datetime.utcnow().isoformat(),
        }
        with open(self._corrections_jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info("correction logged (%d total)", self.correction_count())
        if self.correction_count() >= AUTO_TRAIN_CORRECTIONS:
            logger.info("correction threshold reached — triggering async training")
            self.trigger_training_async()

    # ── counts ────────────────────────────────────────────────────────────────

    def correction_count(self) -> int:
        """Number of corrections logged."""
        return _count_lines(self._corrections_jsonl)

    def sample_count(self) -> int:
        """Number of WAV samples logged."""
        return _count_lines(self._samples_jsonl)

    # ── adapter ───────────────────────────────────────────────────────────────

    def get_adapter_path(self) -> str | None:
        """Return path to trained LoRA adapter .pt if READY, else None."""
        lora_pt = self._adapter_dir / "whisper_lora.pt"
        if self._ready_marker.exists() and lora_pt.exists():
            return str(lora_pt)
        return None

    def get_ct2_model_path(self) -> str | None:
        """Return path to exported CTranslate2 model directory if present."""
        ready = self._ct2_dir / "model.bin"
        if ready.exists():
            return str(self._ct2_dir)
        return None

    # ── training trigger ──────────────────────────────────────────────────────

    def trigger_training_async(self):
        """Spawn a background subprocess: python learner.py --train --user <username>.

        Non-blocking. Stdout/stderr go to training.log.
        """
        script = str(Path(__file__).resolve())
        cmd = [sys.executable, script, "--train", "--user", self.username,
               "--profiles-dir", str(self._profile_dir.parent)]
        log_fh = open(self._training_log, "a", encoding="utf-8")
        log_fh.write(f"\n=== trigger_training_async at {datetime.utcnow().isoformat()} ===\n")
        log_fh.flush()
        try:
            subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=log_fh,
                close_fds=True,
                # detached on Windows so it survives parent exit
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            logger.info("training subprocess spawned for user=%s", self.username)
        except Exception as exc:
            logger.error("failed to spawn training subprocess: %s", exc)
            log_fh.write(f"spawn failed: {exc}\n")
        # NOTE: intentionally NOT closing log_fh — subprocess inherits it

    # ── summary ───────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        return {
            "user": self.username,
            "samples": self.sample_count(),
            "corrections": self.correction_count(),
            "adapter": self.get_adapter_path() is not None,
            "ct2_model": self.get_ct2_model_path() is not None,
            "profile_dir": self.profile_dir,
        }

# ─────────────────────────────────────────────────────────────────────────────
# Training
# ─────────────────────────────────────────────────────────────────────────────

def train(username: str, profiles_dir: str | None = None):
    """Fine-tune Whisper with LoRA on collected samples + corrections.

    Uses openai-whisper (NOT CTranslate2) for fine-tuning.
    Base model: openai/whisper-large-v3 (downloaded from HuggingFace if needed).
    LoRA via peft: r=8, alpha=16, target_modules=["q_proj","v_proj"].
    Training data: samples.jsonl (WAV + text pairs).

    Saves:
      profiles/<user>/adapter/whisper_lora.pt   — LoRA adapter weights
      profiles/<user>/adapter/READY             — marker file on success
      profiles/<user>/ct2_model/                — CTranslate2-exported merged model
    """
    # ── setup logger to stdout (captured by trigger_training_async) ───────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("learner.train")
    log.info("=== LoRA training started for user=%s ===", username)

    # ── check dependencies ────────────────────────────────────────────────────
    missing = _check_deps()
    if missing:
        log.error("Missing dependencies: %s", ", ".join(missing))
        log.error("Install with:")
        log.error("  pip install %s", " ".join(missing))
        sys.exit(1)

    # ── lazy imports (only after dep check) ───────────────────────────────────
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, TaskType
    from transformers import (
        WhisperForConditionalGeneration,
        WhisperProcessor,
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
    )
    import numpy as np
    import soundfile as sf

    # ── profile ───────────────────────────────────────────────────────────────
    profile = VoiceProfile(username=username, profiles_dir=profiles_dir)
    n_samples = profile.sample_count()
    log.info("samples available: %d (minimum: %d)", n_samples, MIN_SAMPLES_FOR_TRAIN)
    if n_samples < MIN_SAMPLES_FOR_TRAIN:
        log.error(
            "Not enough samples to train. Have %d, need at least %d. "
            "Keep using the mic and corrections will build up the dataset.",
            n_samples, MIN_SAMPLES_FOR_TRAIN,
        )
        sys.exit(1)

    # ── load samples.jsonl ────────────────────────────────────────────────────
    samples_path = Path(profile.profile_dir) / "samples.jsonl"
    records = _load_jsonl(samples_path)
    log.info("loaded %d sample records from %s", len(records), samples_path)

    # ── load processor + model ────────────────────────────────────────────────
    log.info("loading processor from %s …", BASE_WHISPER_MODEL)
    processor = WhisperProcessor.from_pretrained(BASE_WHISPER_MODEL)
    log.info("loading base model %s …", BASE_WHISPER_MODEL)
    model = WhisperForConditionalGeneration.from_pretrained(
        BASE_WHISPER_MODEL,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )
    model.config.forced_decoder_ids = processor.get_decoder_prompt_ids(
        language="hebrew", task="transcribe"
    )

    # ── apply LoRA ────────────────────────────────────────────────────────────
    lora_cfg = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        target_modules=LORA_TARGET_MODULES,
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.SEQ_2_SEQ_LM,
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    # ── build HuggingFace Dataset from WAV files ───────────────────────────────
    log.info("building dataset …")

    def _load_audio(wav_path: str):
        audio, sr = sf.read(wav_path)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != 16000:
            # simple resample via scipy if available
            try:
                from scipy.signal import resample_poly
                from math import gcd
                g = gcd(16000, sr)
                audio = resample_poly(audio, 16000 // g, sr // g).astype(np.float32)
            except ImportError:
                log.warning("scipy not installed — skipping resample for %s (sr=%d)", wav_path, sr)
        return audio.astype(np.float32)

    def _preprocess(record):
        try:
            audio = _load_audio(record["wav"])
        except Exception as exc:
            log.warning("skipping %s: %s", record.get("wav"), exc)
            return None
        inputs = processor(audio, sampling_rate=16000, return_tensors="pt")
        input_features = inputs.input_features[0]  # (80, 3000)
        labels = processor.tokenizer(record["text"]).input_ids
        return {
            "input_features": input_features.numpy(),
            "labels": labels,
        }

    processed = [r for rec in records if (r := _preprocess(rec)) is not None]
    log.info("preprocessed %d/%d samples successfully", len(processed), len(records))
    if len(processed) < MIN_SAMPLES_FOR_TRAIN:
        log.error("too many skipped samples; only %d usable. Aborting.", len(processed))
        sys.exit(1)

    hf_dataset = Dataset.from_list(processed)

    # ── data collator ─────────────────────────────────────────────────────────
    import torch.nn.functional as F
    from dataclasses import dataclass
    from typing import Any

    @dataclass
    class WhisperDataCollator:
        processor: Any

        def __call__(self, features):
            input_features = torch.tensor(
                np.array([f["input_features"] for f in features]), dtype=torch.float32
            )
            label_list = [f["labels"] for f in features]
            max_len = max(len(l) for l in label_list)
            labels_padded = []
            for lab in label_list:
                pad = [-100] * (max_len - len(lab))
                labels_padded.append(lab + pad)
            labels = torch.tensor(labels_padded, dtype=torch.long)
            return {"input_features": input_features, "labels": labels}

    collator = WhisperDataCollator(processor=processor)

    # ── training args ─────────────────────────────────────────────────────────
    output_dir = str(profile._adapter_dir / "checkpoints")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("training on device: %s", device)
    if device == "cuda":
        model = model.half()
    model = model.to(device)

    training_args = Seq2SeqTrainingArguments(
        output_dir=output_dir,
        num_train_epochs=TRAIN_EPOCHS,
        per_device_train_batch_size=TRAIN_BATCH,
        learning_rate=TRAIN_LR,
        warmup_steps=max(1, len(processed) // 4),
        gradient_accumulation_steps=4,
        fp16=torch.cuda.is_available(),
        save_strategy="epoch",
        logging_steps=5,
        predict_with_generate=False,
        report_to="none",
        dataloader_num_workers=0,
        remove_unused_columns=False,
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=hf_dataset,
        data_collator=collator,
    )

    # ── train ─────────────────────────────────────────────────────────────────
    log.info("starting training …")
    t0 = time.monotonic()
    trainer.train()
    elapsed = time.monotonic() - t0
    log.info("training complete in %.1fs", elapsed)

    # ── save LoRA adapter ─────────────────────────────────────────────────────
    adapter_pt = profile._adapter_dir / "whisper_lora.pt"
    torch.save(model.state_dict(), str(adapter_pt))
    log.info("LoRA adapter saved to %s", adapter_pt)

    # also save via peft (for merge_and_unload)
    peft_save_dir = str(profile._adapter_dir / "peft")
    model.save_pretrained(peft_save_dir)
    processor.save_pretrained(peft_save_dir)
    log.info("peft adapter saved to %s", peft_save_dir)

    # ── write READY marker ────────────────────────────────────────────────────
    profile._ready_marker.write_text(
        f"trained at {datetime.utcnow().isoformat()} "
        f"on {len(processed)} samples in {elapsed:.1f}s\n",
        encoding="utf-8",
    )
    log.info("READY marker written")

    # ── export to CTranslate2 ─────────────────────────────────────────────────
    _export_ct2(model, processor, profile, log)

    log.info("=== training pipeline complete for user=%s ===", username)

# ─────────────────────────────────────────────────────────────────────────────
# CTranslate2 export
# ─────────────────────────────────────────────────────────────────────────────

def _export_ct2(model, processor, profile: "VoiceProfile", log):
    """Merge LoRA into base weights and export to CTranslate2 format.

    Requires `ctranslate2` and `ctranslate2[torch]` (ct2-opus-mt-converter style).
    Falls back gracefully if not installed.
    """
    try:
        import ctranslate2.converters
    except ImportError:
        log.warning(
            "ctranslate2 not installed — skipping CT2 export. "
            "Install with: pip install ctranslate2"
        )
        return

    try:
        from peft import PeftModel
        import tempfile

        log.info("merging LoRA into base weights for CT2 export …")
        merged = model.merge_and_unload()

        with tempfile.TemporaryDirectory() as tmp:
            merged.save_pretrained(tmp)
            processor.save_pretrained(tmp)

            ct2_out = str(profile._ct2_dir)
            profile._ct2_dir.mkdir(parents=True, exist_ok=True)

            converter = ctranslate2.converters.OpusMTConverter(tmp)
            # Whisper converter
            try:
                from ctranslate2.converters import OpenAIWhisperConverter
                converter = OpenAIWhisperConverter(tmp)
            except ImportError:
                log.warning("OpenAIWhisperConverter not found in ctranslate2; trying generic")

            converter.convert(ct2_out, quantization="float16", force=True)
            log.info("CT2 model exported to %s", ct2_out)
    except Exception as exc:
        log.error("CT2 export failed: %s", exc)
        log.error("You can export manually: ct2-whisper-converter --model <merged_dir> --output %s",
                  profile._ct2_dir)

def export_ct2(username: str, profiles_dir: str | None = None):
    """CLI export command — merge LoRA + export CT2 without re-training."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("learner.export")

    missing = _check_deps()
    if missing:
        print(f"[learner] Missing deps: {', '.join(missing)}")
        print(f"[learner] Install: pip install {' '.join(missing)}")
        sys.exit(1)

    profile = VoiceProfile(username=username, profiles_dir=profiles_dir)
    adapter_path = profile.get_adapter_path()
    if adapter_path is None:
        print(f"[learner] No trained adapter found for user={username}. Run --train first.")
        sys.exit(1)

    import torch
    from peft import PeftModel
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    log.info("loading base model %s …", BASE_WHISPER_MODEL)
    processor = WhisperProcessor.from_pretrained(BASE_WHISPER_MODEL)
    base = WhisperForConditionalGeneration.from_pretrained(
        BASE_WHISPER_MODEL,
        torch_dtype=torch.float32,
    )
    peft_dir = str(profile._adapter_dir / "peft")
    log.info("loading peft adapter from %s …", peft_dir)
    model = PeftModel.from_pretrained(base, peft_dir)
    _export_ct2(model, processor, profile, log)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _count_lines(path: Path) -> int:
    """Count non-empty lines in a file; returns 0 if file doesn't exist."""
    if not path.exists():
        return 0
    count = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
    except OSError:
        pass
    return count

def _load_jsonl(path: Path) -> list[dict]:
    records = []
    if not path.exists():
        return records
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("skipping malformed line %d in %s: %s", i, path, exc)
    return records

def _check_deps() -> list[str]:
    """Return list of missing pip packages needed for training."""
    missing = []
    checks = [
        ("torch", "torch"),
        ("transformers", "transformers"),
        ("peft", "peft"),
        ("datasets", "datasets"),
        ("soundfile", "soundfile"),
        ("numpy", "numpy"),
    ]
    for mod, pkg in checks:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    return missing

def _all_profiles(profiles_dir: Path | None = None) -> list[VoiceProfile]:
    base = profiles_dir or _PROFILES_DIR
    if not base.exists():
        return []
    return [VoiceProfile(username=d.name, profiles_dir=str(base))
            for d in sorted(base.iterdir()) if d.is_dir()]

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(
        description="Voice profile + LoRA fine-tuning for Hebrew mic.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python learner.py --status
  python learner.py --train --user iddo1
  python learner.py --export --user iddo1
  python learner.py --log-sample recording.wav "שלום עולם" --user iddo1
  python learner.py --log-correction "שלם" "שלום" --user iddo1
        """,
    )
    parser.add_argument("--status", action="store_true", help="show all profiles")
    parser.add_argument("--train", action="store_true", help="run LoRA training for --user")
    parser.add_argument("--export", action="store_true", help="export CT2 model for --user")
    parser.add_argument("--user", default=None, help="username (default: $USERNAME)")
    parser.add_argument("--profiles-dir", default=None, help="override profiles directory")
    parser.add_argument("--log-sample", nargs=2, metavar=("WAV", "TEXT"),
                        help="log a WAV sample with its transcription")
    parser.add_argument("--log-correction", nargs=2, metavar=("ORIGINAL", "CORRECTED"),
                        help="log a user correction pair")
    parser.add_argument("--summary", action="store_true", help="print JSON summary for --user")

    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    profiles_dir = args.profiles_dir

    if args.status:
        profiles = _all_profiles(Path(profiles_dir) if profiles_dir else None)
        if not profiles:
            print("[learner] No profiles found.")
            return
        print(f"[learner] {len(profiles)} profile(s):\n")
        for p in profiles:
            s = p.summary()
            adapter_tag = "adapter=YES" if s["adapter"] else "adapter=no"
            ct2_tag = "ct2=YES" if s["ct2_model"] else "ct2=no"
            print(f"  {s['user']:20s}  samples={s['samples']:4d}  "
                  f"corrections={s['corrections']:4d}  {adapter_tag}  {ct2_tag}")
            print(f"    dir: {s['profile_dir']}")
        return

    if args.train:
        if not args.user:
            args.user = os.getenv("USERNAME") or "default"
        train(username=args.user, profiles_dir=profiles_dir)
        return

    if args.export:
        if not args.user:
            args.user = os.getenv("USERNAME") or "default"
        export_ct2(username=args.user, profiles_dir=profiles_dir)
        return

    if args.log_sample:
        wav, text = args.log_sample
        p = VoiceProfile(username=args.user, profiles_dir=profiles_dir)
        p.log_sample(wav, text)
        print(f"[learner] sample logged for {p.username} ({p.sample_count()} total)")
        return

    if args.log_correction:
        orig, corrected = args.log_correction
        p = VoiceProfile(username=args.user, profiles_dir=profiles_dir)
        p.log_correction(orig, corrected)
        print(f"[learner] correction logged for {p.username} ({p.correction_count()} total)")
        return

    if args.summary:
        p = VoiceProfile(username=args.user, profiles_dir=profiles_dir)
        print(json.dumps(p.summary(), ensure_ascii=False, indent=2))
        return

    parser.print_help()

if __name__ == "__main__":
    _cli()
