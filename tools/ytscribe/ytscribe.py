"""YTSCRIBE — transcribe any online video, with what we already own.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: "תוריד ותפעיל איזה כלי חינמי לתמלול סרטוני יוטוב."

**Nothing new was downloaded to transcribe.** We already run the best free model there is
for his voice: `large-v3-turbo-ct2` plus his own Hebrew LoRA, serving on 127.0.0.1:8737
(mic-rebuild). The only missing piece was the fetcher, and `yt-dlp` was already installed.
So this is ~180 lines of glue, not a new engine.

Two paths, cheapest first:

1. **Captions, if the video has them.** yt-dlp pulls the uploader's own subtitles or
   YouTube's auto-captions. Free, instant, and usually more accurate on proper nouns than
   any local model, because it had the uploader's metadata. Tried first, always.
2. **Our own ear.** Fall back to pulling the audio, cutting it into <=25 s pieces (the
   server refuses a body over 30 s of 16 kHz PCM) and decoding each through
   `/v1/transcribe`.

Sacred Audio Law: the audio is downloaded and read as numbers. **Nothing is ever played.**

    python ytscribe.py <URL> [--lang he|en|auto] [--force-asr] [--out FILE]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave

STT = "http://127.0.0.1:8737/v1/transcribe"
TOKEN_FILE = r"D:/CLAUDE/mic-rebuild/state/stt-token"
CHUNK_S = 25.0                       # server caps the body at 30 s of 16 kHz PCM
YTDLP = os.path.expanduser(
    r"~/AppData/Local/Programs/Python/Python313/Scripts/yt-dlp.exe")


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


# ------------------------------------------------------------------ captions

def strip_vtt(text: str) -> str:
    """WebVTT -> plain lines, de-duplicated. Auto-captions repeat each line as they roll."""
    out, last = [], None
    for raw in text.splitlines():
        s = raw.strip()
        if (not s or s.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
                or "-->" in s or s.isdigit()):
            continue
        s = re.sub(r"<[^>]+>", "", s).strip()          # inline timing tags
        if s and s != last:
            out.append(s)
            last = s
    return "\n".join(out)


def try_captions(url: str, lang: str, work: str) -> str | None:
    langs = "he,en" if lang == "auto" else lang
    r = run([YTDLP, "--skip-download", "--write-subs", "--write-auto-subs",
             "--sub-langs", langs, "--sub-format", "vtt/best",
             "-o", os.path.join(work, "cap.%(ext)s"), url])
    vtts = [f for f in os.listdir(work) if f.endswith(".vtt")]
    if not vtts:
        print("  no captions on this video (%s)" % (r.stderr.strip().splitlines()[-1:] or [""])[0][:90])
        return None
    # prefer the requested language, else whatever came
    vtts.sort(key=lambda f: 0 if (lang != "auto" and ".%s." % lang in f) else 1)
    txt = strip_vtt(io.open(os.path.join(work, vtts[0]), encoding="utf-8").read())
    print("  captions found: %s (%d chars)" % (vtts[0], len(txt)))
    return txt or None


# ---------------------------------------------------------------------- asr

def fetch_audio(url: str, work: str) -> str:
    wav = os.path.join(work, "a.wav")
    r = run([YTDLP, "-f", "bestaudio/best", "-x", "--audio-format", "wav",
             "--postprocessor-args", "-ar 16000 -ac 1",
             "-o", os.path.join(work, "a.%(ext)s"), url])
    if not os.path.exists(wav):
        raise RuntimeError("yt-dlp gave no audio:\n" + r.stderr[-700:])
    return wav


def decode(pcm: bytes, lang: str, timeout: float = 90.0) -> str:
    tok = io.open(TOKEN_FILE, encoding="utf-8").read().strip()
    rid = "%s-%d" % (secrets.token_hex(4), int(time.time() * 1000))
    req = urllib.request.Request(
        STT, data=pcm,
        headers={"Authorization": "Bearer " + tok, "X-Request-Id": rid,
                 "X-Lang-Hint": lang if lang in ("he", "en") else "auto",
                 "Content-Type": "application/octet-stream"})
    try:
        return (json.load(urllib.request.urlopen(req, timeout=timeout))
                .get("text", "") or "").strip()
    except urllib.error.HTTPError as e:
        return "[decode %d: %s]" % (e.code, e.read().decode()[:80])


def transcribe(wav_path: str, lang: str) -> str:
    w = wave.open(wav_path, "rb")
    sr, n = w.getframerate(), w.getnframes()
    if sr != 16000 or w.getnchannels() != 1:
        raise RuntimeError("expected 16 kHz mono, got %d Hz / %d ch" % (sr, w.getnchannels()))
    step = int(CHUNK_S * sr)
    parts, done = [], 0
    print("  %.1f s of audio -> %d chunks" % (n / sr, (n + step - 1) // step))
    while done < n:
        w.setpos(done)
        pcm = w.readframes(min(step, n - done))
        t = decode(pcm, lang)
        if t:
            parts.append(t)
        done += step
        print("    %3d%%" % (100 * done // n), flush=True)
    return "\n".join(parts)


# --------------------------------------------------------------------- main

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Transcribe a video URL with our own ear.")
    p.add_argument("url")
    p.add_argument("--lang", default="auto", choices=("he", "en", "auto"))
    p.add_argument("--force-asr", action="store_true",
                   help="skip captions, always decode the audio ourselves")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)

    if not os.path.exists(YTDLP):
        print("yt-dlp not found at %s" % YTDLP, file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="ytscribe-") as work:
        text, how = None, ""
        if not a.force_asr:
            print("[1] looking for captions...")
            text = try_captions(a.url, a.lang, work)
            how = "captions"
        if not text:
            print("[2] pulling audio and decoding on our own server...")
            text = transcribe(fetch_audio(a.url, work), a.lang)
            how = "our ear (large-v3-turbo + iddo-lora)"

    out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "transcript-%d.txt" % int(time.time()))
    io.open(out, "w", encoding="utf-8").write(
        "# %s\n# source: %s\n# via: %s\n\n%s\n" % (
            time.strftime("%Y-%m-%d %H:%M"), a.url, how, text))
    print("\nvia: %s\nsaved: %s  (%d chars)" % (how, out, len(text)))
    print("-" * 60)
    print(text[:1200] + ("\n... [truncated, full text in the file]" if len(text) > 1200 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
