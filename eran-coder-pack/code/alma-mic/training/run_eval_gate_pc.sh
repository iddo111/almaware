PY="C:/Users/<user>/AppData/Local/Programs/Python/Python313/python.exe"
CHAMP="deepdml/faster-whisper-large-v3-turbo-ct2"
CHAL="runs/iddo-20260806/epoch3-ct2"
for split in eval_voice eval_retain; do
  echo "### champion / $split"
  "$PY" evaluate.py --model "$CHAMP" --split $split.jsonl --tag champion 2>&1 | grep -E "^WER|^repetition|wrote"
  echo "### challenger / $split"
  "$PY" evaluate.py --model "$CHAL" --split $split.jsonl --tag epoch3 2>&1 | grep -E "^WER|^repetition|wrote"
done
echo "### GATE"
"$PY" promote.py --challenger epoch3 --champion champion 2>&1
echo "GATE_DONE_PC"
