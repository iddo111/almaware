# KESHEV-LORA — a personal voice LoRA with a "helps and does not harm" gate

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**עברית:** צינור שלם לאמן לורה אישית ל-Whisper על הקול של עידו — ולבדוק בכנות שהיא **מועילה ולא מזיקה**. הלורה נפרסת **רק אם היא מנצחת** את המודל העברי הקיים על הקול של עידו (שגיאת-תווים נמוכה יותר **וגם** לא פחות שמות-פרויקט נכונים). תיקו או הפסד = הפסד, וזורקים אותה.

**English:** A full pipeline to fine-tune a personal Whisper LoRA on Iddo's voice and honestly test that it **helps and does not harm**. The LoRA deploys **only if it beats** the current Hebrew model on Iddo's own held-out voice (lower CER **and** no fewer correct project names). A tie or a loss is a loss — it gets discarded.

---

## Why this exists / למה זה קיים

A previous personal LoRA was already tried and **LOST** to the `ivrit-ai/whisper-large-v3-turbo` baseline:
`:8738` ivrit-ai → **13** correct project names, **CER 18.0%**; the old LoRA `:8737` → **0** names, **CER 28.5%**.
It lost because it was trained on **circular labels** — transcripts the old mic pipeline itself typed (hallucinations included). Training on your own errors teaches the errors.

This pipeline fixes the root cause: **clean labelled data**. Iddo reads known text aloud, so the correct transcript is exact before a single sample is cut.

הלורה הקודמת הפסידה כי אומנה על תמלולים שהמיקרופון עצמו הקליד — כולל הזיות. כאן עידו קורא טקסט ידוע, כך שהתמלול הנכון מדויק מראש.

---

## The four steps / ארבעת השלבים

### 1. Record (Iddo — on the PC) / הקלטה
```bat
setx PYTHONIOENCODING utf-8        REM once, if not already set
cd D:\CLAUDE\keshev-lora
python record.py
```
- Uses the **Logitech BRIO** (USB) only. It **refuses** any Bluetooth headset mic (Sacred Audio Law) and never touches audio output.
- Shows 150 lines to read (~20–28 min): project vocabulary, general Hebrew, and your real command phrases.
- Controls: **ENTER** start/stop · **r** redo · **s** skip · **q** save & quit. Progress saves after every clip — stop and resume any time.
- Output: `data/clips/*.wav` (16 kHz mono) + `data/manifest.jsonl` (the ground truth).
- You can edit any line's spelling in `script_he.py` **before** recording it — what you read is what the model is graded on.

**עברית:** מריצים `python record.py`, קוראים 150 שורות בקול (רבע שעה עד חצי שעה) מול ה-BRIO. אפשר לעצור עם `q` ולהמשיך אחר כך. אוזניות בלוטות' לא נפתחות אף פעם.

### 2. Train (on a FLEET GPU — not the PC) / אימון
The PC's torch is CPU-only and project law forbids training on the PC. Stage `data/` to a fleet box that has torch+cuda, transformers, peft, and `ct2-transformers-converter`.
```bash
# eran3 is OFF LIMITS (coder training ~7 days). Prefer a free window on eran4/eran1.
PYTHONIOENCODING=utf-8 python train_lora.py \
    --data ./data --out ./data/lora-adapter --ct2-out ./data/lora-ct2 \
    --epochs 6 --batch 4 --rank 16 --lr 1e-3
```
This trains a LoRA (r=16, q/v proj) on the **train split only**, then **merges** it into the base and **converts to CTranslate2** (`data/lora-ct2/`) — the exact format the live decoder serves. A raw PEFT adapter cannot be served by faster-whisper; only the merged+converted model can, so that is what we test.

### 3. The gate (on the fleet) / השער
```bash
PYTHONIOENCODING=utf-8 python eval_gate.py \
    --data ./data \
    --baseline-ct2 ivrit-ai/whisper-large-v3-turbo-ct2 \
    --lora-ct2 ./data/lora-ct2
```
Decodes the **held-out** eval clips with both models under keshev-6-identical settings and prints:
```
CER:   baseline 0.xxxx  ->  lora 0.xxxx   (better / NOT better)
names: baseline a/N     ->  lora b/N      (ok / REGRESSED)
VERDICT:  PASS / FAIL
```
**PASS iff** `lora CER < baseline CER` **AND** `lora names >= baseline names`. Otherwise **FAIL**.

### 4. Decide (Iddo) / החלטה
This pipeline **never swaps the live decoder.** On PASS, Iddo sees the numbers and decides whether to deploy. Deployment would convert `data/lora-ct2` into the served model and point `KESHEV_STT_URL` at it — a separate, deliberate act, his call.

---

## Where things are / איפה הדברים

| what | path |
|---|---|
| recording harness + script | `record.py`, `script_he.py` |
| training + merge + CT2 convert | `train_lora.py` |
| the go/no-go gate | `eval_gate.py` |
| recorded data (Iddo makes this) | `data/clips/*.wav`, `data/manifest.jsonl` |
| trained adapter / served CT2 | `data/lora-adapter/`, `data/lora-ct2/` |
| baseline model (already on disk) | `ivrit-ai/whisper-large-v3-turbo-ct2` (HF cache) or `D:\CLAUDE\mic-rebuild\models\large-v3-turbo-ct2` |
| the honest state + assessment | `FINDINGS.md` |

## The split is sacred / הפיצול קדוש

`script_he.is_eval()` is the single, permanent rule: every `vocab_eval` line **plus** every 5th prompt is held out. Training (`train_lora.py`) never reads eval rows; the gate (`eval_gate.py`) only reads eval rows. The eval set is never trained on — that is what makes the verdict trustworthy.

---

## Current state, blockers, and the honest assessment / מצב, חסמים, והערכה כנה

**Built and tested (2026-09-04):** all four scripts. Verified on the PC: `pick_mic()` chooses the BRIO and **refuses** a Bluetooth-only machine; the script splits 150 → 104 train / 46 eval; the gate's CER/WER/name math is unit-tested (CER identical=0, 1/4 chars=0.25; the name scorer credits `צ'ינצ'ילה`/`סונט` and gives 0 to the broken `צ'רלי וחצי`/`סונת`). `train_lora.py` needs a fleet GPU (PC torch is CPU-only).

**Blocked on two things, neither is compute capability:**
1. **Clean data — needs Iddo.** No clean labelled data exists yet. The 15,780-clip `alma-mic/voice_corpus` is the circular, pseudo-labelled set that sank the last LoRA; it was **not** reused as truth. The only honest source is Iddo reading `script_he.py` aloud — ~20–28 min, once.
2. **A GPU window.** Measured: **eran3 OFF LIMITS** (coder training ~7 days); **eran4 busy** (96% util, ollama 50 GB); **eran1 idle compute + ~83 GB free** but it runs the live ERAN organism — needs Iddo's OK, not to be started uninvited. The training job itself is small (r=16, ~100 clips ⇒ 10–30 min on a GB10).

**Will a LoRA actually win?** Honestly, **probably not on general Hebrew, maybe narrowly on names.** The ivrit-ai baseline is strong; the prior personal LoRA lost badly (0/13 names, CER 28.5% vs 18.0%) on circular labels; and keshev-6's names-only prompt already fixes most project names **for free**, so a LoRA must beat *baseline + prompt*, not raw baseline. Clean data gives it a fair shot at your specific articulation and any name the prompt still misses — a real but narrow upside. The gate exists so a tie-or-loss is discarded, not shipped. No claim of success until `eval_gate.py` prints **PASS** on real held-out voice; a **FAIL** ("keep ivrit-ai + prompt") is a legitimate, valuable result.

**What I did NOT do:** touch the mic, the live decoders (:8737/:8738), audio devices, or eran3; train anything (no data, no green-lit GPU); reuse the circular corpus as truth; or swap the live model.
