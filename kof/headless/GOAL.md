> 🪟 BROKEN WINDOWS LAW: if it's not working, fix it immediately. Test the REAL output, not a proxy.

# GOAL — KESHEV 7 / קשב 7

## מה זה / What it is
**עברית:** עידו מדבר עברית (ולפעמים אנגלית) למיקרופון במחשב שלו, והטקסט מופיע איפה שהסמן שלו עומד. זה הכלי שהוא תלוי בו כל יום. קשב 7 נבנה מאפס — 100% שלנו.
**English:** Iddo speaks Hebrew (sometimes English) into a microphone on his Windows PC and the text appears wherever his cursor is. He depends on it every day. KESHEV 7 is built from scratch, 100% ours.

## The contract you must deliver (stage 1 — the model)
```
python3 transcribe.py <path/to/clip.wav>     # run from the sandbox root {{SANDBOX}}
  -> prints the transcript (Hebrew text, as Iddo speaks) to stdout
```
- Input: WAV, PCM 16 kHz, mono, 16-bit, 0.3–30 s.
- The hidden evaluator runs it once per held-out clip, CPU only, no network, timeout **{{CLIP_TIMEOUT}} s per clip including python start-up**. A crash or timeout counts as an empty transcript.
- Keep transcribe.py fast to start: load one small checkpoint, no training inside it.

## The bar
- Metric: CER (character error rate) and WER after Hebrew normalization (niqqud removed, final letters folded, punctuation removed) on **{{HELDOUT_CLIPS}} held-out clips from recording sessions you never see**.
- **DONE-ACCEPTED when CER ≤ {{BAR}}** (and ≤ 5% clips failing). That is "a first working mic".
- Baselines on the same held-out set, so you know what nothing looks like: empty output CER = **{{BASE_EMPTY}}**; always printing the most frequent word ("{{MFW_WORD}}") CER = **{{BASE_MFW}}**.
- When you reply `DONE:` the runner runs the eval and tells you the score. It also runs it every {{EVAL_EVERY}} rounds once transcribe.py exists. The loop never stops on DONE — after acceptance keep lowering CER.

## RUNNER NOTES 2026-09-15 — tools that work / כלים
**עברית:** אין כאן כלי apply_patch — כדי ליצור או לשנות קובץ שלח `WRITE:` עם הקובץ כולו. חומת הייבוא מתירה את torch.optim (תוקן ב-07:03, נבדק על פתיון; שום פקודה של הראלי עוד לא השתמשה בו). ההקלטות ב-`data/unlabeled/cafe/` קריאות.
**English:**
- **There is no `apply_patch` (or `patch`) tool here.** A `RUN` that calls `apply_patch` or holds a `*** Begin Patch` block is NOT run. To create or change a file reply `WRITE: <relative/path>` and then the ENTIRE file in a ``` fence; the runner writes it for you.
- **`torch.optim` is allowed by the import wall** (AdamW, SGD, lr schedulers). The earlier crash when an optimizer was built (an ImportError naming `onnx`) was a runner bug, fixed at 07:03; a full AdamW step passes under the wall in the runner's decoy test. No rally command has used it yet. Hand-written SGD is no longer needed.
- **`data/unlabeled/cafe/` is readable**: {{UNLABELED_FILES}} WAV files, {{UNLABELED_HOURS}} hours, 16 kHz mono 16-bit. Read it with the stdlib `wave` module in chunks + numpy. No command has read it yet.
- Every eval so far scored CER 1.000, the same as empty output. First make `python3 transcribe.py data/train/wav/<one clip>.wav` print non-empty text, from a checkpoint whose tensor shapes match the model that transcribe.py builds.

## RUNNER NOTE — memory floor / רצפת זיכרון
**עברית:** כשהזיכרון הפנוי במכונה נמוך מ-{{MEM_FLOOR}} GiB, כל RUN נדחה (`REFUSED [mem-floor]`) וגם ההערכה נדחית (`DEFERRED [mem-floor]`). זה לא בידיים שלך: הרנר מחכה לזיכרון (עד {{MEM_WAIT_MIN}} דקות) לפני הסבב הבא. אל תשלח DONE כדי למלא זמן, ואל תבקש להוריד את הרצפה או למחוק קבצים.
**English:**
- When host MemAvailable is below **{{MEM_FLOOR}} GiB**, every `RUN` is refused (`REFUSED [mem-floor]`) and the eval is deferred (`DEFERRED [mem-floor]`). The floor protects Iddo's live jobs on this shared machine. It is not yours to change, and asking will not change it.
- The runner then waits up to {{MEM_WAIT_MIN}} minutes for memory before your next round. Use a round like that for `WRITE` only: make transcribe.py and the checkpoint code right, so they work the first time a RUN is allowed. Do not reply `DONE` to fill the time.

## Your data (Iddo's own voice)
- `data/train/train.jsonl` — one JSON per line: `id`, `wav` (relative to data/train), `text` (what Iddo accepted), `ms`, `sid` (session), `ts`.
- `data/train/wav/*.wav` — **{{TRAIN_CLIPS}} clips, {{TRAIN_HOURS}} hours, {{TRAIN_SESSIONS}} sessions, {{HEBREW_CLIPS}} contain Hebrew letters.** Read `data/train/STATS.json`.
- data/train and data/unlabeled are read-only. Put features, checkpoints and logs in your own folders (e.g. `feats/`, `ckpt/`, `logs/`). Use `tmp/` for temporary files (TMPDIR points there).
- This is very little LABELED data (about two hours). Say so honestly in DONE/ASK if the bar looks out of reach; do not fake it.
- Hold out a validation slice of the TRAIN sessions yourself to track progress between evals.

## UNLABELED audio — קפה קלוד / Café Claude (NO text)
**עברית:** ב-`data/unlabeled/cafe/` יש **{{UNLABELED_FILES}} הקלטות, {{UNLABELED_HOURS}} שעות** של הקול של עידו עצמו (WAV 16 kHz מונו 16-bit) — **בלי שום טקסט**. אמן עליהן קודם את המקודד האקוסטי באימון עצמי (self-supervised) מאתחול אקראי, ואחר כך כוונן עם CTC על `data/train`. אסור לתייג אותן בשום מודל חיצוני. ה-eval, הרף והחוזה לא השתנו.
**English:**
- `data/unlabeled/cafe/*.wav` — **{{UNLABELED_FILES}} recordings, {{UNLABELED_HOURS}} hours of Iddo's own voice**, 16 kHz mono 16-bit, **no transcripts**. Details in `data/unlabeled/cafe/STATS.json`. About ten times more audio than data/train.
- Use it in two steps: (1) **pretrain the acoustic encoder from random init** with a self-supervised objective you write yourself (e.g. masked-frame prediction/reconstruction on your own log-mel features, or contrastive predictive coding); (2) **then add the CTC head and fine-tune on `data/train`**. Check on your own train-session validation slice that pretraining helps; keep whichever is better.
- Files are long (minutes to over an hour, with pauses): cut them into short segments yourself (your own energy VAD) and read them in chunks. Checkpoint the pretraining like any trainer (AUTOSAVE LAW).
- Pseudo-labels, if you want them, may come ONLY from your own KESHEV 7 model. Never label this audio with any outside model or program (no KESHEV 6, no Whisper, no ASR of any kind).
- The held-out eval, the bar and the contract are unchanged.

## "No open source" — the exact rule (Iddo may tighten it)
- **Allowed:** bash, the Python 3.12 standard library, numpy, PyTorch used as tensor math (tensors, autograd, nn layers, optimizers, CTCLoss), scipy, a C compiler for your own C. All already installed.
- **Forbidden:** any pretrained model or weights; any speech/ASR/audio-ML library or code (whisper, faster-whisper, ctranslate2, vosk, kaldi, espnet, speechbrain, wav2vec, NeMo, torchaudio, librosa, HuggingFace transformers/datasets/hub, sentencepiece, tiktoken, ready-made CER/WER libraries); any git clone; any pip/conda/apt install or download.
- **Every model is trained from random initialization on the data above.** Write the feature extraction (framing, window, FFT, mel filterbank, log), the model, the loss use, the decoder and the metrics yourself.
- Python imports from your code are walled at runtime to: stdlib, numpy, torch, scipy and your own files.

## Machine rules (enforced by the runner in code, not by trust)
- Working directory = the sandbox. Relative paths only. No `..`. No absolute paths outside the sandbox. No `~` or `$HOME` except the sandbox itself.
- Each command: memory cap **{{MEM_MAX}}** (exceed it and the kernel kills the command), CPU quota **{{CPU}}**, nice 19, **timeout {{CMD_TIMEOUT}} s**. GPU: **{{GPU}}**. The sandbox may use at most **{{DISK_CAP}} GiB**.
- Therefore every trainer MUST save a checkpoint atomically (write `x.tmp`, then rename) at least every few minutes and on SIGTERM, and MUST resume from the latest checkpoint (weights, optimizer, step counter) when started again. Run long training as a sequence of commands that each resume. (This is Iddo's AUTOSAVE LAW.)
- No network at all from your commands or code — not from python, and not from C, perl or awk either. No servers, no ports.
- **No command substitution `$(...)` or backticks, and no `perl` / `awk` / `make` / `node`.** You are in a ping-pong loop: run a command, then read its output in your NEXT reply. Use `{1..N}` for ranges and `$((a+b))` for arithmetic. Put real logic in python files you WRITE, not in shell.
- **`kill` only `$!`** — a background job you started on THIS command line with `&` (e.g. `sleep 5 & kill $!`). Never `kill` a PID, a variable, or `$(pgrep ...)`; never touch a process you did not start (Iddo's live training runs on this box).
- Your python may **read** the sandbox + the installed libraries, and **write** only inside the sandbox. Reading anywhere else (home, the evaluator) is refused at the syscall.
- No sudo, systemctl (except `--user status`), docker, ssh/scp/rsync, cron, mount.
- This machine runs Iddo's live jobs. Be small and patient; never try to get around a cap. A refused command is not run — read the reason and adapt.

## Stages
1. Look at the data (durations, text alphabet, Hebrew vs English share). Decide the output alphabet (Hebrew letters, space, maybe Latin letters and digits).
2. Features from scratch (numpy or torch): 25 ms window, 10 ms hop, ~80 log-mel bands, per-utterance normalization. Cache them.
3. Self-supervised pretraining of the encoder on `data/unlabeled/cafe` (random init, no labels), then the CTC fine-tune below. A small acoustic model trained from random init with CTC over characters (e.g. conv subsampling + a few BiGRU or transformer layers, 5–20 M parameters). Heavy augmentation written by you (speed/tempo, noise, SpecAugment-style masking) — two hours is tiny.
4. Greedy CTC decoding first; later your own beam search and your own character n-gram language model trained only on the train transcripts.
5. `transcribe.py` meeting the contract. Say `DONE:` to get scored. Iterate on what the score tells you.
6. **Only after DONE-ACCEPTED:** keep improving CER, and write the PC side from scratch in `pc/` — Windows microphone capture through the Win32 API (ctypes: waveIn or WASAPI), voice-activity detection, sending audio to the model, typing text at the cursor with SendInput. **Write it, do not run it here.** It must be a separate new program that never touches KESHEV 6's files, its folders or its microphone while KESHEV 6 runs. Iddo and Claude deploy it later.

## Files the runner keeps for Iddo
- `PROGRESS.md` (rewritten every 10 rounds) and `QUESTIONS.md` (your ASKs and the assumptions you made). Keep your own notes in `NOTES.md` if you want.
