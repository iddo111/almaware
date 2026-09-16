#!/bin/bash
# ALMA-MIC LoRA chain 2 on eran4: teacher relabel -> run2 train -> eval.
# nohup-launched so ssh cleanups can't kill it. Numbers-only logs.
cd ~/lora-iddo || exit 1
V=.venv/bin/python
export TOKENIZERS_PARALLELISM=false
echo "STAGE teacher start $(date +%H:%M:%S)" > logs/chain2_status.txt

$V transcribe_teacher.py --data data/voice_corpus --out data/teacher_corpus.jsonl \
    --batch 8 > logs/teacher.log 2>&1
if ! grep -q "\[teacher\] DONE" logs/teacher.log; then
  echo "TEACHER FAILED $(date +%H:%M:%S)" >> logs/chain2_status.txt; exit 1
fi
echo "STAGE train start $(date +%H:%M:%S)" >> logs/chain2_status.txt

$V train_lora_iddo.py train --data data/voice_corpus \
    --labels data/teacher_corpus.jsonl --out lora_r16_run2 \
    --slice 0 --epochs 1 --batch 8 --lr 1e-4 --workers 0 > logs/train_run3.log 2>&1
if ! grep -q "\[train\] DONE" logs/train_run3.log; then
  echo "TRAIN FAILED $(date +%H:%M:%S)" >> logs/chain2_status.txt; exit 1
fi
echo "STAGE eval start $(date +%H:%M:%S)" >> logs/chain2_status.txt

$V train_lora_iddo.py eval --data data/voice_corpus --lora lora_r16_run2 \
    --limit 150 --batch 8 > logs/eval_run2.log 2>&1
if ! grep -q "\[eval\] DONE" logs/eval_run2.log; then
  echo "EVAL FAILED $(date +%H:%M:%S)" >> logs/chain2_status.txt; exit 1
fi
echo "CHAIN2 COMPLETE $(date +%H:%M:%S)" >> logs/chain2_status.txt
