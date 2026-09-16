"""alma-mic / train_lora.py — train OUR Hebrew LoRA on Iddo's own voice.

ALMAWARE-pure: our training code. The base (Whisper) and the result (a LoRA = OUR
weights) are the model-not-app category — allowed under the purity law, like Eran.

WHAT IT DOES
  Fine-tunes a small LoRA adapter on top of Whisper using (audio, text) pairs of
  Iddo's voice, so recognition gets better at *his* Hebrew specifically.

HONEST PREREQUISITES (this is the next stage, not a one-click today)
  1. pip install  peft transformers datasets accelerate evaluate jiwer soundfile torch
     (on this PC `peft` is MISSING and torch has no CUDA — run this on the DGX.)
  2. A dataset: DATA_DIR/*.wav  each with a sibling *.txt (the exact Hebrew said).
     Even 30-60 minutes of his clean voice already helps.
  3. A GPU (DGX your-gpu-host/your-gpu-host). Large-v3 LoRA on CPU is impractical.

AFTER TRAINING (to use it fast in stt.py)
  Merge the LoRA into the base, then convert to CTranslate2:
     ct2-transformers-converter --model <merged_dir> --output_dir <ct2_dir> --quantization int8
  Then in the app's settings set  "לורה עברית" = <ct2_dir>  (config.lora_dir).
"""
from __future__ import annotations
import os
import sys
import glob

BASE_MODEL = "openai/whisper-large-v3-turbo"   # same family as the ivrit-ai inference model
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_data")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lora_he")
LANGUAGE = "he"


def _require():
    missing = []
    for m in ("torch", "transformers", "peft", "datasets", "soundfile"):
        try:
            __import__(m)
        except Exception:
            missing.append(m)
    if missing:
        sys.exit("missing packages: " + ", ".join(missing) +
                 "\n  pip install peft transformers datasets accelerate evaluate jiwer soundfile torch")


def _pairs():
    wavs = sorted(glob.glob(os.path.join(DATA_DIR, "*.wav")))
    pairs = [(w, w[:-4] + ".txt") for w in wavs if os.path.exists(w[:-4] + ".txt")]
    if not pairs:
        sys.exit(f"no (wav, txt) pairs in {DATA_DIR}\n"
                 "  put Iddo's clips there: clip1.wav + clip1.txt (the Hebrew said), etc.")
    return pairs


def main():
    _require()
    pairs = _pairs()
    import torch, soundfile as sf
    from datasets import Dataset, Audio
    from transformers import (WhisperProcessor, WhisperForConditionalGeneration,
                              Seq2SeqTrainer, Seq2SeqTrainingArguments)
    from peft import LoraConfig, get_peft_model

    print(f"[alma-mic] {len(pairs)} clips  base={BASE_MODEL}  device="
          f"{'cuda' if torch.cuda.is_available() else 'cpu (slow!)'}")

    processor = WhisperProcessor.from_pretrained(BASE_MODEL, language=LANGUAGE, task="transcribe")

    def row(wav, txt):
        with open(txt, encoding="utf-8") as f:
            text = f.read().strip()
        return {"audio": wav, "text": text}

    ds = Dataset.from_list([row(w, t) for w, t in pairs]).cast_column("audio", Audio(sampling_rate=16000))

    def prep(b):
        a = b["audio"]
        b["input_features"] = processor.feature_extractor(
            a["array"], sampling_rate=16000).input_features[0]
        b["labels"] = processor.tokenizer(b["text"]).input_ids
        return b

    ds = ds.map(prep, remove_columns=ds.column_names)

    model = WhisperForConditionalGeneration.from_pretrained(BASE_MODEL)
    model = get_peft_model(model, LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        target_modules=["q_proj", "v_proj"]))
    model.print_trainable_parameters()

    def collate(feats):
        import torch
        x = processor.feature_extractor.pad(
            [{"input_features": f["input_features"]} for f in feats], return_tensors="pt")
        y = processor.tokenizer.pad(
            [{"input_ids": f["labels"]} for f in feats], return_tensors="pt")
        labels = y["input_ids"].masked_fill(y.attention_mask.ne(1), -100)
        x["labels"] = labels
        return x

    args = Seq2SeqTrainingArguments(
        output_dir=OUT_DIR, per_device_train_batch_size=4, gradient_accumulation_steps=2,
        learning_rate=1e-3, warmup_steps=20, num_train_epochs=8, fp16=torch.cuda.is_available(),
        logging_steps=10, save_strategy="epoch", report_to=[])
    Seq2SeqTrainer(model=model, args=args, train_dataset=ds, data_collator=collate).train()
    model.save_pretrained(OUT_DIR)
    print(f"[alma-mic] LoRA saved -> {OUT_DIR}\n"
          "  next: merge + ct2-transformers-converter, then set config.lora_dir (see header).")


if __name__ == "__main__":
    main()
