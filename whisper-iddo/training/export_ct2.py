"""Convert the fine-tuned HF checkpoint to CTranslate2 for the mic app.

alma-mic/stt.py runs faster-whisper (CTranslate2), not transformers, so an HF
checkpoint cannot be dropped in as-is.

SAFETY: this writes a NEW model directory and changes nothing that is currently
being served. Switching the app over is a one-line edit to alma-mic/config.json
(`model` -> the new path), left for a human to make deliberately.

DECODE SETTINGS THIS MODEL EXPECTS -- these are part of the deliverable, not
optional tuning:

  language: "auto"        keep it. The fine-tune trains the language token on
                          Iddo's own code-switched speech; forcing language=he
                          scored 134.78% WER on his English in the prior
                          diagnosis and is still the wrong thing to do.
  log_prob_threshold      raise from -1.0. The prior diagnosis attributed 5.0%
                          of ALL utterances to real speech being deleted by this
                          gate alone. Fine-tuning does not touch it -- it is a
                          post-decode filter -- so the 13.5% silent-deletion
                          defect survives training unless this is changed.
  without_timestamps      the fine-tune keeps the timestamp path alive (20% of
                          training samples retain clip-level timestamps), so
                          either setting works. True is marginally safer.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hf", required=True, help="fine-tuned HF checkpoint dir")
    ap.add_argument("--out", required=True, help="destination CT2 dir (must not exist)")
    ap.add_argument("--quant", default="float16",
                    help="float16 matches the current production model")
    args = ap.parse_args()

    if os.path.exists(args.out):
        sys.exit(f"refusing to overwrite existing {args.out}")

    cmd = ["ct2-transformers-converter", "--model", args.hf,
           "--output_dir", args.out, "--copy_files",
           "tokenizer.json", "preprocessor_config.json",
           "--quantization", args.quant]
    print(" ".join(cmd), flush=True)
    subprocess.check_call(cmd)

    print("\nconverted. verify before switching the app over:")
    print(f"  py -3.13 -c \"from faster_whisper import WhisperModel; "
          f"m=WhisperModel(r'{args.out}', device='cuda', compute_type='float16'); "
          f"print(list(m.transcribe('some.wav', language='he')[0]))\"")


if __name__ == "__main__":
    main()
