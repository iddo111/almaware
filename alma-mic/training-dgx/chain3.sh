#!/bin/bash
# ALMA-MIC chain 3 on eran4 (Iddo order 18:27 - Cafe-Claude):
#   D) teacher-label the permanent 628 heldout (refs only, never training)
#   E) re-eval run2 vs BASE against teacher refs (style-bias-aware second metric)
#   A) long-form teacher transcription of ALL Cafe-Claude audio
#   C) Cafe-Claude proxy eval on the RESERVED dates (20260625, 20260701)
# nohup-launched; numbers-only logs.
cd ~/lora-iddo || exit 1
V=.venv/bin/python
export TOKENIZERS_PARALLELISM=false
S=logs/chain3_status.txt
echo "STAGE heldout-teacher start $(date +%H:%M:%S)" > $S

$V transcribe_teacher.py --data data/voice_corpus --out data/teacher_heldout.jsonl \
    --pool heldout --batch 8 > logs/teacher_heldout.log 2>&1
grep -q "\[teacher\] DONE" logs/teacher_heldout.log || { echo "HELDOUT-TEACHER FAILED $(date +%H:%M:%S)" >> $S; exit 1; }
echo "STAGE teacherref-eval start $(date +%H:%M:%S)" >> $S

$V train_lora_iddo.py eval --data data/voice_corpus --lora lora_r16_run2 \
    --limit 150 --batch 8 --gold data/teacher_heldout.jsonl --gold-only \
    > logs/eval_run2_teacherref.log 2>&1
grep -q "\[eval\] DONE" logs/eval_run2_teacherref.log || { echo "TEACHERREF-EVAL FAILED $(date +%H:%M:%S)" >> $S; exit 1; }
echo "STAGE cafe-transcribe start $(date +%H:%M:%S)" >> $S

$V cafe_teacher.py --audio cafe/audio --out cafe/transcripts --batch 8 \
    > logs/cafe_teacher.log 2>&1
grep -q "\[cafe\] DONE" logs/cafe_teacher.log || { echo "CAFE-TRANSCRIBE FAILED $(date +%H:%M:%S)" >> $S; exit 1; }
echo "STAGE cafe-eval start $(date +%H:%M:%S)" >> $S

$V cafe_eval.py --audio cafe/audio --refs cafe/transcripts --lora lora_r16_run2 \
    --batch 8 > logs/cafe_eval.log 2>&1
grep -q "\[cafe-eval\] DONE" logs/cafe_eval.log || { echo "CAFE-EVAL FAILED $(date +%H:%M:%S)" >> $S; exit 1; }
echo "CHAIN3 COMPLETE $(date +%H:%M:%S)" >> $S
