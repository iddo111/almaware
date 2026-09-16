"""ask_qwen.py — the pipe to the 480B. Iddo's order 2026-08-20 08:57:
"תן לו לכתוב מההתחלה את המיק ... תן לו לעשות הכל אפילו לתכנן".

The big Qwen (480B AWQ, vLLM pipeline x3 over eran1+2+3, behind the 4D router)
designs and writes KESHEV-QWEN. Fable's job: carry the brief, verify what comes
back, and unblock it when it gets stuck — not to write it.

Usage:  python ask_qwen.py <prompt-file> <out-file> [max_tokens]
Every exchange is appended to LOG so the whole build is auditable.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.request

ROUTER = "http://<lan-ip>:8010/v1/chat/completions"
MODEL = "qwen3-coder-480b"
ROOT = pathlib.Path(__file__).resolve().parent
LOG = ROOT / "qwen-build.log"

SYSTEM = """You are the architect and sole author of KESHEV-QWEN, a Hebrew-first
dictation microphone for Iddo Perez's Windows PC. You plan it, you design it, you
write every line. A human assistant (Fable) only verifies your output runs and
unblocks you when you ask.

Hard constraints, learned from a year of real failures — violating them is a bug:
1. USB microphone ONLY (a Logitech BRIO). NEVER open a Bluetooth headset as a mic
   — it flips the headset to phone-quality audio and ruins his music. If no USB
   mic is present the app stays idle; it never falls back.
2. The app NEVER plays audio. No sound output call sites at all.
3. Speech decoding is an HTTP POST to an existing server (OpenAI-ish contract:
   POST /v1/transcribe, raw PCM s16le 16 kHz mono, header X-Request-Id matching
   ^[0-9a-f]{8}-[0-9]{6,}$, X-Audio-Duration-Ms; reply JSON has text, lang,
   avg_logprob). Two servers exist: 127.0.0.1:8737 (PC GPU) and <lan-ip>:8737.
   No local model, no torch, no worker process.
4. Speech is NEVER lost. Every captured utterance is written to disk BEFORE it is
   decoded, and stays there until it is delivered or explicitly judged.
5. Typing happens with Win32 SendInput into the focused window, and Enter is a
   SEPARATE burst that re-verifies focus. If the user has been idle 2 minutes, type
   but never press Enter; idle 10 minutes, do not type at all — park it.
6. He code-switches Hebrew/English mid-sentence. The decoder's own language guess
   is unreliable on short Hebrew: it returns confident English garbage. Decode
   ambiguous audio twice (auto and forced Hebrew) and let avg_logprob pick.
7. Junk must never reach his window: near-silence hallucinations ("you", "thank
   you", "תודה"), repetition loops, and single tokens with a long run of one
   repeated character (a yawn: "אההההה").
8. One honest append-only JSONL event per fact. Health means TEXT LANDED IN HIS
   WINDOW — not "process alive", not "audio captured".
9. Windows, Python 3.13, standard library plus sounddevice only. No bash.
10. Tests first. Every law above needs a test that fails when the law is broken.

Answer in dense technical English. When asked for code, output complete files,
no ellipses, no "rest unchanged"."""


def ask(prompt: str, max_tokens: int = 4096, temperature: float = 0.2) -> str:
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")
    req = urllib.request.Request(ROUTER, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=3600) as r:
        payload = json.load(r)
    dt = time.monotonic() - t0
    text = payload["choices"][0]["message"]["content"]
    usage = payload.get("usage", {})
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*70}\nPROMPT ({len(prompt)} chars, {dt:.0f}s, "
                f"{usage.get('completion_tokens')} tok, "
                f"{(usage.get('completion_tokens') or 0)/max(dt,1e-9):.1f} tok/s)\n"
                f"{prompt[:2000]}\n{'-'*70}\n{text}\n")
    print(f"[{usage.get('completion_tokens')} tokens in {dt:.0f}s = "
          f"{(usage.get('completion_tokens') or 0)/max(dt,1e-9):.1f} tok/s]",
          file=sys.stderr)
    return text


if __name__ == "__main__":
    prompt_file, out_file = sys.argv[1], sys.argv[2]
    mt = int(sys.argv[3]) if len(sys.argv) > 3 else 4096
    out = ask(pathlib.Path(prompt_file).read_text(encoding="utf-8"), mt)
    pathlib.Path(out_file).write_text(out, encoding="utf-8")
    print(out[:1500])
