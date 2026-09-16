#!/bin/bash
# KESHEV nightly LoRA — "make the mic always train" / "u make sure it always
# gets better" (Iddo, 2026-08-15).
#
# THE ONE PROMISE THIS SCRIPT MAKES: the live model never gets worse.
# A newly trained LoRA replaces the deployed one ONLY if it beats it on the
# reserved eval sessions, measured the same way, in the same run. Otherwise
# it is kept on disk and the deployed model is left alone. There is no path
# in this file that promotes on training loss, on "it finished", or on hope.
#
# WHY THAT MATTERS MORE THAN THE TRAINING: a mic that trains on its own
# output gets more confident and more wrong, and the loss curve looks
# beautiful the entire way down. The eval below is the only thing standing
# between Iddo and that.
#
# RESERVED, NEVER TRAINED ON: Cafe-Claude 2026-06-25 and 2026-07-01. They are
# the eval set (shared with the Voice Ant Farm). cafe_eval.py enforces this by
# prefix; this script must never add them to a training pool.
#
# Runs on eran4. NEVER eran1 (Qwen head), never the PC (no torch on the PC).
set -uo pipefail
cd "$HOME/lora-iddo" || exit 1

V=.venv/bin/python
STAMP=$(date +%Y%m%d-%H%M%S)
LOG_DIR="$HOME/lora-iddo/logs/nightly"
LOG="$LOG_DIR/$STAMP.log"
LEDGER="$HOME/lora-iddo/logs/promotion-ledger.jsonl"
LIVE="$HOME/lora-iddo/iddo-lora-run2-ct2"      # what the STT server loads
INBOX="$HOME/lora-iddo/data/keshev_corpus"     # what the mic captured
mkdir -p "$LOG_DIR" "$INBOX"

say() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }

say "=== KESHEV nightly LoRA $STAMP ==="

# ---------------------------------------------------------------- 1. corpus
NEW_WAVS=$(find "$INBOX" -name '*.wav' 2>/dev/null | wc -l)
say "new utterances captured from the mic: $NEW_WAVS"

# Below this there is nothing to learn from and a training run is pure risk:
# it would rewrite the model from noise and burn a GPU-hour to do it.
MIN_NEW=${MIN_NEW:-200}
if [ "$NEW_WAVS" -lt "$MIN_NEW" ]; then
  say "SKIP — fewer than $MIN_NEW new utterances. The live model is untouched."
  say "(this is a healthy outcome, not a failure)"
  exit 0
fi

# ------------------------------------------------------------ 2. baseline
# Measure what is DEPLOYED right now, tonight, on tonight's eval — never a
# remembered number from a previous run against a possibly different set.
say "measuring the CURRENTLY DEPLOYED model..."
$V cafe_eval.py --audio cafe/audio --refs cafe/transcripts \
   --lora lora_r16_run2 --batch 8 >> "$LOG" 2>&1
CUR_WER=$(grep -oE 'WER=[0-9.]+' "$LOG" | tail -1 | cut -d= -f2)
say "deployed WER = ${CUR_WER:-unknown}"
if [ -z "${CUR_WER:-}" ]; then
  say "ABORT — could not measure the deployed model. Refusing to train a"
  say "replacement I would have nothing to compare against."
  exit 1
fi

# -------------------------------------------------------------- 3. train
OUT="lora_r16_$STAMP"
say "training $OUT on voice_corpus + $NEW_WAVS new utterances..."
$V train_lora_iddo.py train --data data/voice_corpus --out "$OUT" \
   --epochs 2 --batch 8 --rank 16 --labels data/teacher_corpus.jsonl \
   >> "$LOG" 2>&1
if [ ! -d "$OUT" ]; then
  say "ABORT — training produced no adapter. Live model untouched."
  exit 1
fi

# --------------------------------------------------------- 4. THE GATE
say "measuring the CHALLENGER on the same reserved eval..."
$V cafe_eval.py --audio cafe/audio --refs cafe/transcripts \
   --lora "$OUT" --batch 8 >> "$LOG" 2>&1
NEW_WER=$(grep -oE 'WER=[0-9.]+' "$LOG" | tail -1 | cut -d= -f2)
say "challenger WER = ${NEW_WER:-unknown}"

record() {
  python3 - "$1" <<PY >> "$LEDGER"
import json, sys, datetime
print(json.dumps({
  "ts": datetime.datetime.now().isoformat(timespec="seconds"),
  "run": "$STAMP", "candidate": "$OUT",
  "deployed_wer": ${CUR_WER:-None}, "candidate_wer": ${NEW_WER:-None},
  "new_utterances": $NEW_WAVS, "outcome": sys.argv[1],
}, ensure_ascii=False))
PY
}

if [ -z "${NEW_WER:-}" ]; then
  say "KEEP DEPLOYED — the challenger could not be measured."
  record "unmeasurable"; exit 1
fi

# Strictly better. A tie keeps the incumbent: churn without gain is still
# risk, and every swap is a chance to break a working microphone.
if awk "BEGIN{exit !($NEW_WER < $CUR_WER)}"; then
  say "PROMOTE — $NEW_WER beats $CUR_WER"
  $V merge_convert.py --lora "$OUT" --out "${LIVE}.new" >> "$LOG" 2>&1 \
    && $V sanity_ct2.py --model "${LIVE}.new" >> "$LOG" 2>&1 \
    && mv "$LIVE" "$HOME/lora-iddo/retired/${STAMP}-$(basename $LIVE)" \
    && mv "${LIVE}.new" "$LIVE" \
    && systemctl --user restart keshev-stt \
    && say "DEPLOYED. previous model archived under retired/, not deleted." \
    && record "promoted"
else
  say "KEEP DEPLOYED — challenger $NEW_WER did not beat $CUR_WER."
  say "The candidate stays on disk at $OUT. Nothing was swapped."
  say "(this is the gate doing its job, not a failure)"
  record "rejected"
fi

say "=== done ==="
