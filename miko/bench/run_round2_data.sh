#!/bin/bash
# Round 2 DATA pipeline, one shot, on eran2. Stops on the first failure.
set -e
cd /home/eran2/miko-bench
export PYTHONUNBUFFERED=1

echo "=================== 1. merge the question pool ==================="
python3 merge_questions.py 2>&1 | tee merge2.log

echo "=================== 2. BM25 over 166,425 real pages ==============="
python3 rank2.py 2>&1 | tail -20 | tee rank2.log

echo "=================== 3. build the (question,page) pairs ============"
python3 build_pairs2.py 2>&1 | tee build_pairs2.log

echo "=================== 4. judge, rubric A (the label) ================"
python3 judge.py --inp data/pairs2_unscored.jsonl --out data/pairs2.jsonl \
        --rubric A --bs 64 2>&1 | grep -av "it/s\]" | tee judge2_A.log

echo "=================== 5. judge, rubric B (validity subsample) ======="
python3 judge.py --inp data/pairs2_unscored.jsonl --out data/pairs2_rubricB.jsonl \
        --rubric B --bs 64 --stride 12 2>&1 | grep -av "it/s\]" | tee judge2_B.log

echo "=================== 6. label validity at the new scale ============"
python3 validity2.py 2>&1 | tee validity2.log

echo "=================== 7. coverage filter ============================"
python3 filter_pairs2.py 2>&1 | tee filter2.log

echo "=================== DATA PIPELINE DONE ============================"
date
wc -l data/pairs2.jsonl data/pairs2f.jsonl data/questions2.jsonl
