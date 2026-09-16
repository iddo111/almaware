# Almaware Voice Typer 🎙️

A native Windows dictation app: speak, and it types into whatever window has focus.
Hebrew + English, local-first. Part of the **ALMAWARE** ecosystem.

אפליקציית הכתבה לווינדוס: מדברים — והטקסט מוקלד לחלון הפעיל. עברית + אנגלית, הכול מקומי.

## What it does
- Captures the mic, detects speech (VAD), transcribes locally, and types the text for you.
- **Speech recognition runs on YOUR computer** (faster-whisper + the
  [ivrit-ai](https://huggingface.co/ivrit-ai) Hebrew-finetuned Whisper model).
  No audio ever leaves your machine. Works on CPU; uses an NVIDIA GPU automatically if you have one.
- Native tkinter GUI (settings, live transcript) — not a web app.

## Install (from source) · התקנה
1. Install **Python 3.10–3.12** from [python.org](https://www.python.org/downloads/)
   (check "Add python.exe to PATH" in the installer).
2. In this folder:
   ```
   pip install -r requirements.txt
   python gui.py
   ```
3. **First run only:** the app downloads the recognition model (~1.5 GB) from
   Hugging Face. This takes a few minutes and needs internet **once** — after
   that everything is offline.

בהרצה הראשונה האפליקציה מורידה את מודל הזיהוי (~1.5GB) — פעם אחת בלבד, אחר כך הכול עובד בלי אינטרנט.

Settings live in `config.json` (created on first run next to the app; edit via the ⚙ panel
or copy `config.example.json`). Headless mode: `python app.py`.

### Check it works without a microphone · בדיקה בלי מיקרופון
```
python transcribe_file.py --cpu path\to\some_hebrew.wav
```
Prints the recognized text + timing.

## Speed expectations (measured) · למה לצפות
Whisper processes audio in fixed 30-second windows, so on CPU **every utterance —
even one word — costs one full window pass**. Measured with this app's exact
settings (`language: "he"`, int8):

| Machine | one sentence (any length ≤ ~25s) | 33s monologue |
|---|---|---|
| Desktop CPU (measured here) | ~15–20 s | ~27 s |
| Typical laptop, CPU only | ~30–45 s | ~1–1.5 min |
| NVIDIA GPU | < 1 s | ~2 s |

CPU-only dictation **works but is slow** — you speak, then wait tens of seconds
for the text. On a GPU it is instant. `language: "auto"` (he/en detection) costs
**2–3× more** per utterance on CPU; keep `"he"` on weak machines.

הכתבה במחשב בלי כרטיס מסך עובדת אבל איטית — עשרות שניות לכל משפט. עם GPU של NVIDIA זה מיידי.

## Optional extras (all OFF by default, the app works fully without them)
- **Brain**: ask Grok (needs the `grok` CLI installed + logged in) or a DictaLM
  server (`dicta_url` in config). If missing, the app says so in Hebrew and dictation is unaffected.
- **Voice corpus** (`collect_corpus`): opt-in saving of your clips for personal fine-tuning.

## Layout
`gui.py` GUI · `app.py` headless · `pipeline.py` capture→VAD→STT→type · `audio.py` `vad.py`
`stt.py` local recognition · `typer.py` keystroke output · `transcribe_file.py` no-mic sanity check.

## License
MIT (see LICENSE). Provided as-is, no warranty.
