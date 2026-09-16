#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hebrew narration for THE PERCEPTRON.

edge-tts emits no WordBoundary events for he-IL, so the subtitle timing is
obtained the honest way: every sentence is synthesised as its own file and its
duration is measured with ffprobe. The block audio is then the concatenation of
its sentences, and each subtitle cue gets a real measured in/out point.

Writes  narration/he/NN.mp3            (whole block)
        narration/he/NN_sSS.mp3        (one sentence)
        narration/timing.json          (blocks -> cues with measured times)
"""
import asyncio, io, json, os, re, subprocess, sys

import edge_tts

VOICE = "he-IL-AvriNeural"
RATE = "-4%"
OUT = "narration/he"
SENT_GAP = 0.16          # breath between sentences inside a block

# A subtitle line longer than this gets split at a comma.
MAX_CHARS = 62


def dur(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], text=True)
    return float(out.strip())


def split_sentences(text):
    """Split Hebrew narration into speakable sentences."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # very long sentences get broken at an em dash or a comma so no
        # subtitle line is unreadable
        while len(p) > MAX_CHARS * 2:
            cut = -1
            for sep in (" — ", ", "):
                c = p.rfind(sep, 0, MAX_CHARS * 2)
                if c > MAX_CHARS // 2:
                    cut = c + len(sep)
                    break
            if cut < 0:
                break
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        out.append(p)
    return out


def wrap(text):
    """Two-line wrap for a subtitle cue."""
    if len(text) <= MAX_CHARS:
        return text
    words = text.split()
    half = len(text) // 2
    best, bl = None, 1e9
    acc = 0
    for i, w in enumerate(words[:-1]):
        acc += len(w) + 1
        if abs(acc - half) < bl:
            bl, best = abs(acc - half), i + 1
    return " ".join(words[:best]) + "\n" + " ".join(words[best:])


async def say(text, path):
    if os.path.exists(path) and os.path.getsize(path) > 3000:
        return
    comm = edge_tts.Communicate(text, VOICE, rate=RATE)
    await comm.save(path)


async def main():
    os.makedirs(OUT, exist_ok=True)
    shots = json.load(io.open("shots_he.json", encoding="utf-8"))
    blocks = []
    for s in shots:
        n = s["n"]
        sents = split_sentences(s["he"])
        cues, t = [], 0.0
        files = []
        for i, sent in enumerate(sents, 1):
            p = os.path.join(OUT, "%02d_s%02d.mp3" % (n, i))
            await say(sent, p)
            d = dur(p)
            cues.append({"text": sent, "disp": wrap(sent),
                         "start": round(t, 3), "end": round(t + d, 3)})
            t += d + SENT_GAP
            files.append(p)
        t -= SENT_GAP                       # no trailing gap
        # concatenate the sentences of this block into one audio file
        blockmp3 = os.path.join(OUT, "%02d.mp3" % n)
        lst = os.path.join(OUT, "%02d.txt" % n)
        with open(lst, "w") as f:
            for p in files:
                f.write("file '%s'\n" % os.path.basename(p))
                f.write("outpoint %.4f\n" % dur(p))
        # build with a silence pad between sentences using the concat filter
        inputs = []
        for p in files:
            inputs += ["-i", p]
        fl = []
        for i in range(len(files)):
            fl.append("[%d:a]aresample=48000,apad=pad_dur=%.3f[a%d]" % (i, SENT_GAP, i))
        chain = "".join("[a%d]" % i for i in range(len(files)))
        filt = ";".join(fl) + ";" + chain + "concat=n=%d:v=0:a=1[out]" % len(files)
        subprocess.run(["ffmpeg", "-v", "error", "-y"] + inputs +
                       ["-filter_complex", filt, "-map", "[out]",
                        "-c:a", "libmp3lame", "-b:a", "192k", blockmp3],
                       check=True)
        real = dur(blockmp3)
        blocks.append({"n": n, "chapter": s["ch"], "mp3": blockmp3,
                       "dur": round(real, 3), "cues": cues})
        print("block %2d  %2d sentences  %6.2fs" % (n, len(cues), real), flush=True)

    total = sum(b["dur"] for b in blocks)
    json.dump({"voice": VOICE, "rate": RATE, "total": round(total, 3),
               "blocks": blocks}, io.open("narration/timing.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("TOTAL NARRATION %.2fs = %d:%05.2f" % (total, int(total) // 60, total % 60))


if __name__ == "__main__":
    asyncio.run(main())
